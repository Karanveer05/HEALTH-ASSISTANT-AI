"""Loads the curated JSON knowledge in backend/data and holds the shared text-matching helpers."""
import difflib
import json
import re
from functools import lru_cache

from .config import DATA_DIR


def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@lru_cache
def conditions_data() -> dict:
    return _load("conditions.json")


@lru_cache
def condition_map() -> dict:
    return {c["id"]: c for c in conditions_data()["conditions"]}


@lru_cache
def drugs_data() -> dict:
    return _load("drugs.json")


@lru_cache
def drug_map() -> dict:
    return {d["id"]: d for d in drugs_data()["drugs"]}


@lru_cache
def lab_data() -> dict:
    return _load("lab_ranges.json")


@lru_cache
def lab_map() -> dict:
    return {t["id"]: t for t in lab_data()["tests"]}


@lru_cache
def foods() -> list:
    return _load("foods.json")["foods"]


@lru_cache
def remedies_data() -> dict:
    return _load("remedies.json")


@lru_cache
def remedy_map() -> dict:
    return {r["id"]: r for r in remedies_data()["remedies"]}


@lru_cache
def emergency_data() -> dict:
    return _load("emergency.json")


# ---------- text matching ----------

NEGATIONS = {"no", "not", "without", "denies", "deny", "never", "nahi", "nahin", "na", "none"}
AFFIRMATIVE = re.compile(r"^\s*(yes|y|yeah|yep|haan|han|ha|sometimes|often|always|a little|little|slightly|true)\b", re.I)
_CLAUSE_BREAK = re.compile(r"[.,;!?\n]| but | and | though | however ")


def normalize(text: str) -> str:
    """Lowercase and append canonical English terms for Hinglish/synonym phrases."""
    low = " " + (text or "").lower().replace("’", "'") + " "
    extra = [canon for phrase, canon in conditions_data()["synonyms"].items() if re.search(rf"\b{re.escape(phrase)}\b", low)]
    return (low + " " + " ".join(extra)).strip()


def has_phrase(text: str, phrase: str) -> bool:
    """True if phrase occurs in text and is not negated in its own clause ("no fever" -> False)."""
    for m in re.finditer(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text):
        clause = _CLAUSE_BREAK.split(text[: m.start()])[-1]
        if not any(w.strip("'\"()") in NEGATIONS for w in clause.split()[-3:]):
            return True
    return False


def case_text(case: dict, include_negative_questions: bool = False) -> str:
    """All patient-reported text for a case: complaint, symptoms and follow-up answers.
    A question's own words count only when the answer was yes ("Do you have rash?" -> "yes")."""
    parts = [case.get("complaint", ""), case.get("other_symptoms", ""), f"duration {case.get('duration', '')}"]
    for qa in case.get("qa", []):
        ans = qa.get("answer", "")
        parts.append(ans)
        if AFFIRMATIVE.match(ans) or include_negative_questions:
            parts.append(qa.get("question", ""))
    return normalize(". ".join(p for p in parts if p))


def matches_any(text: str, terms: list[str]) -> list[str]:
    low = (text or "").lower()
    return [t for t in terms if t and t.lower() in low]


def fuzzy_matches(text: str, terms: list[str]) -> list[str]:
    """Like matches_any, but also catches small typos in what the patient typed
    ("penuts" -> peanut, "paracetmol" -> paracetamol). Used for allergy checks, where a miss is unsafe."""
    hits = matches_any(text, terms)
    words = re.findall(r"[a-z]+", (text or "").lower())
    for t in terms:
        if t in hits or len(t) < 4 or " " in t:
            continue
        if any(len(w) >= 4 and (difflib.SequenceMatcher(None, w, t).ratio() >= 0.8
                                or (len(w) > len(t) and difflib.SequenceMatcher(None, w[:len(t) + 1], t).ratio() >= 0.85))
               for w in words):
            hits.append(t)
    return hits


def patient_facts(profile: dict, keys: tuple) -> dict:
    """Profile fields for the LLM/report; pregnancy only applies to female patients."""
    out = {k: profile.get(k) for k in keys}
    if profile.get("sex") != "female":
        out.pop("pregnant", None)
    return out
