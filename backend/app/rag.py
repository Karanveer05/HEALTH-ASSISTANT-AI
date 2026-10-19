"""Retrieval-Augmented Generation store.

Documents come from the curated JSON (conditions, medicines, lab tests, remedies) plus any .md/.txt
files in backend/knowledge_base/. They are embedded with ChromaDB's built-in all-MiniLM-L6-v2 model
and stored in storage/chroma. If the vector store can't load, a keyword search over the same
documents is used, so the app keeps working.
"""
import hashlib
import logging
import math
import re
import threading
from collections import Counter
from functools import lru_cache

from .config import DATA_DIR, KB_DIR, STORAGE_DIR
from .knowledge import conditions_data, drugs_data, lab_data, remedies_data

log = logging.getLogger("rag")
logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)  # telemetry is off; silence its noise
COLLECTION = "medical_kb"
_lock = threading.Lock()
_collection = None
_vector_failed = False


def _kb_files():
    if not KB_DIR.exists():
        return []
    return sorted(p for p in KB_DIR.rglob("*") if p.suffix.lower() in (".md", ".txt") and p.stem.lower() != "readme")


def _chunks(text: str, size: int = 900):
    paras, buf = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()], ""
    for p in paras:
        if len(buf) + len(p) > size and buf:
            yield buf
            buf = ""
        buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        yield buf


@lru_cache
def documents() -> list[dict]:
    docs = []
    for c in conditions_data()["conditions"]:
        text = (f"{c['name']}. {c['overview']} Common symptoms: {', '.join(c['symptoms'])}. "
                f"Self-care: {'; '.join(c['self_care'])}. See a doctor if: {'; '.join(c['see_doctor_if'])}.")
        if c["suggested_tests"]:
            text += f" Useful tests: {', '.join(c['suggested_tests'])}."
        docs.append({"id": f"cond:{c['id']}", "title": c["name"], "text": text, "source": c["source"]})
    for d in drugs_data()["drugs"]:
        text = (f"{d['name']} ({', '.join(d['brands'])}): {d['purpose']}. Usual adult dose: {d['dose']}. {d['max_text']}. "
                f"{'Prescription only.' if not d['otc'] else 'Available over the counter.'} "
                f"Avoid if: {', '.join(d['avoid_if']) or 'no common restrictions'}. Warnings: {'; '.join(d['warnings'])}.")
        docs.append({"id": f"drug:{d['id']}", "title": d["name"], "text": text, "source": d["source"]})
    for t in lab_data()["tests"]:
        rng = t.get("range") or [t.get("male"), t.get("female")]
        text = f"{t['name']} ({t['unit']}), reference {rng}. Low: {t['low_means']} High: {t['high_means']}"
        docs.append({"id": f"lab:{t['id']}", "title": f"Lab test: {t['name']}", "text": text, "source": "https://medlineplus.gov/lab-tests/"})
    for r in remedies_data()["remedies"]:
        docs.append({"id": f"rem:{r['id']}", "title": r["name"], "text": f"{r['name']}: {r['how']}", "source": r["source"]})
    for path in _kb_files():
        raw = path.read_text(encoding="utf-8", errors="ignore")
        title = next((l.lstrip("# ").strip() for l in raw.splitlines() if l.strip()), path.stem)
        src = next((l.split(":", 1)[1].strip() for l in raw.splitlines() if l.lower().startswith("source:")), path.name)
        for i, chunk in enumerate(_chunks(raw)):
            docs.append({"id": f"kb:{path.stem}#{i}", "title": title, "text": chunk, "source": src})
    return docs


def _version() -> str:
    h = hashlib.sha256()
    for p in sorted(DATA_DIR.glob("*.json")) + _kb_files():
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _get_collection():
    global _collection, _vector_failed
    if _collection is not None or _vector_failed:
        return _collection
    with _lock:
        if _collection is not None or _vector_failed:
            return _collection
        try:
            import chromadb
            from chromadb.config import Settings
            client = chromadb.PersistentClient(path=str(STORAGE_DIR / "chroma"), settings=Settings(anonymized_telemetry=False))
            version = _version()
            col = client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
            if (col.metadata or {}).get("version") != version or col.count() == 0:
                client.delete_collection(COLLECTION)
                col = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine", "version": version})
                docs = documents()
                col.add(ids=[d["id"] for d in docs], documents=[d["text"] for d in docs],
                        metadatas=[{"title": d["title"], "source": d["source"]} for d in docs])
                log.info("RAG index built: %d documents", len(docs))
            _collection = col
        except Exception as e:
            log.warning("Vector store unavailable, using keyword search: %s", e)
            _vector_failed = True
    return _collection


def warm_up():
    _get_collection()


def mode() -> str:
    return "vector" if _get_collection() is not None else "keyword"


_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("the a an and or of to in on for with is are be by as at it this that your you from not has have can".split())


def _tokens(text: str):
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1]


def _keyword_search(query: str, k: int) -> list[dict]:
    docs = documents()
    df = Counter(w for d in docs for w in set(_tokens(d["text"] + " " + d["title"])))
    q = set(_tokens(query))
    scored = []
    for d in docs:
        words = Counter(_tokens(d["text"] + " " + d["title"]))
        score = sum((1 + math.log(words[w])) * math.log(len(docs) / df[w]) for w in q if words[w])
        if score > 0:
            scored.append((score, d))
    scored.sort(key=lambda x: -x[0])
    return [{**d, "score": round(s, 3)} for s, d in scored[:k]]


def retrieve(query: str, k: int = 6, prefix: str | None = None) -> list[dict]:
    col = _get_collection()
    if col is None:
        hits = _keyword_search(query, k * 3 if prefix else k)
        return [h for h in hits if not prefix or h["id"].startswith(prefix)][:k]
    res = col.query(query_texts=[query], n_results=min(k * 3 if prefix else k, col.count()))
    out = []
    for i, doc_id in enumerate(res["ids"][0]):
        if prefix and not doc_id.startswith(prefix):
            continue
        meta = res["metadatas"][0][i]
        out.append({"id": doc_id, "title": meta["title"], "text": res["documents"][0][i],
                    "source": meta["source"], "score": round(1 - res["distances"][0][i], 3)})
    return out[:k]
