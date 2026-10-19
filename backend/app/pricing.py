"""Medicine price comparison (step 10).

Checks live prices on four Indian online pharmacies in parallel:
  PharmEasy, Netmeds - product JSON embedded in their search pages
  Tata 1mg           - its public search API
  Apollo Pharmacy    - its public search API (with the site's anonymous access token)
Truemeds and MedPlus block automated lookups, so they get direct search links, as does Jan Aushadhi.

For each site the best match for the searched medicine is picked, and prices are compared both as
pack price and as price per tablet/capsule/ml, so different pack sizes compare fairly. Results are
cached for 24 h. Rows from an optional offline price list (storage/medicine_prices.csv, see
scripts/import_prices.py) are added when present.
"""
import csv
import json
import logging
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, quote_plus

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from .config import STORAGE_DIR, get_settings
from .models import PriceCache

log = logging.getLogger("pricing")
OFFLINE_CSV = STORAGE_DIR / "medicine_prices.csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}

# kind: page = read JSON embedded in the search page; onemg / apollo = site search API; link = search link only.
# product_prefix turns a product slug into a link.
SOURCES = [
    {"name": "PharmEasy", "kind": "page", "search": "https://pharmeasy.in/search/all?name={q}",
     "product_prefix": "https://pharmeasy.in/online-medicine-order/"},
    {"name": "Netmeds", "kind": "page", "search": "https://www.netmeds.com/products/?q={q}",
     "product_prefix": "https://www.netmeds.com/product/"},
    {"name": "Tata 1mg", "kind": "onemg", "search": "https://www.1mg.com/search/all?name={q}",
     "product_prefix": "https://www.1mg.com/"},
    {"name": "Apollo Pharmacy", "kind": "apollo", "search": "https://www.apollopharmacy.in/search-medicines/{qp}",
     "product_prefix": "https://www.apollopharmacy.in/medicine/"},
    {"name": "Truemeds", "kind": "link", "search": "https://www.truemeds.in/search/{qp}"},
    {"name": "MedPlus Mart", "kind": "link", "search": "https://www.medplusmart.com/searchProduct/{qp}"},
]
JAN_AUSHADHI = {"name": "Jan Aushadhi (govt. generic)", "url": "https://janaushadhi.gov.in/ProductList.aspx"}

NAME_KEYS = ("name", "productName", "product_name", "title", "display_name", "displayName", "skuName")
PRICE_KEYS = ("salePriceDecimal", "salePrice", "sale_price", "discounted_price", "discountedPrice", "selling_price", "sellingPrice",
              "offer_price", "offerPrice", "specialPrice", "prices", "price", "final_price", "finalPrice")
MRP_KEYS = ("mrpDecimal", "mrp", "MRP", "mrpPrice", "actual_price", "actualPrice", "original_price", "maxPrice")
PACK_KEYS = ("measurementUnit", "pack_size_label", "packSize", "pack_size", "packForm", "uom", "unitSize", "label")
URL_KEYS = ("url", "slug", "productUrl", "product_url", "urlKey", "url_key", "seoUrl")
COMP_KEYS = ("moleculeName", "composition", "compositions", "salt", "saltComposition", "generic_name", "short_description")


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and v > 0:
        return float(v)
    if isinstance(v, str):
        m = re.search(r"\d+(?:\.\d+)?", v.replace(",", ""))
        return float(m.group()) if m else None
    if isinstance(v, dict):
        for k in ("effective", "min", "discounted_price", "value", "amount", "price", "mrp"):
            if (n := _num(v.get(k))) is not None:  # skip empty fields, e.g. no discount -> use MRP
                return n
    return None


def _first(d: dict, keys):
    for k in keys:
        if k in d and d[k] not in (None, "", 0):
            return d[k]
    return None


def _walk(obj, out: list, depth=0):
    """Collect every dict that looks like a product (has a name and a sensible price)."""
    if depth > 14 or len(out) > 80:
        return
    if isinstance(obj, dict):
        name, price = _first(obj, NAME_KEYS), _num(_first(obj, PRICE_KEYS))
        if isinstance(name, str) and price and 1 <= price <= 100000:
            out.append(obj)
        for v in obj.values():
            _walk(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, out, depth + 1)


_STATE = re.compile(r"__[A-Z_]+__\s*=\s*\{")


def _json_blobs(html: str) -> list:
    """Embedded page data: Next.js __NEXT_DATA__, JSON script tags and window.__X_STATE__ = {...} assignments."""
    soup = BeautifulSoup(html, "html.parser")
    blobs, decoder = [], json.JSONDecoder()
    for tag in soup.find_all("script"):
        txt = tag.string or tag.get_text() or ""
        if tag.get("id") == "__NEXT_DATA__" or tag.get("type") in ("application/json", "application/ld+json"):
            try:
                blobs.append(json.loads(txt))
            except ValueError:
                pass
            continue
        for m in _STATE.finditer(txt):
            try:
                blobs.append(decoder.raw_decode(txt, m.end() - 1)[0])
            except ValueError:
                pass
    return blobs


# ---------- pack size -> price per unit ----------

_COUNT_IN_PACK = re.compile(r"(\d+)\s*(?:x\s*)?(tablet|tab|capsule|cap|sachet|lozenge)s?\b", re.I)
_COUNT_IN_NAME = re.compile(r"(\d+)\s*'s\b|(?:strip|pack|box) of (\d+)\s*(tablet|capsule|sachet)", re.I)
_VOLUME = re.compile(r"(\d+(?:\.\d+)?)\s*ml\b", re.I)
_LIQUID = re.compile(r"syrup|suspension|liquid|drops|solution|\bml\b", re.I)
SOLID_UNITS = {"tablet", "capsule", "sachet", "lozenge"}


def pack_units(pack: str, name: str) -> tuple[float | None, str | None]:
    """Number of tablets/capsules/sachets (or ml) in the pack, read from the pack label first, then the name."""
    both = f"{pack} {name}"
    if not _LIQUID.search(both):
        if pack and (m := _COUNT_IN_PACK.search(pack)):
            unit = m.group(2).lower()
            return float(m.group(1)), {"tab": "tablet", "cap": "capsule"}.get(unit, unit)
        if m := _COUNT_IN_NAME.search(both):
            form = next((f for f in ("capsule", "sachet") if f in both.lower()), "tablet")
            return float(m.group(1) or m.group(2)), (m.group(3) or form).lower()
        if re.search(r"\bsachet", both, re.I):
            return 1.0, "sachet"
    if m := _VOLUME.search(both):
        return float(m.group(1)), "ml"
    return None, None


def _has_word(text: str, word: str) -> bool:
    """Whole-word match: "dolo" is not in "Dolofirst", but "650" is in "650Mg"."""
    end = r"(?!\d)" if word.isdigit() else r"(?![a-z])"
    return re.search(rf"(?<![a-z0-9]){re.escape(word)}{end}", text) is not None


# ---------- turning raw product dicts into offers ----------

def _words(query: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1]


def _to_offers(source: dict, raw: list[dict], query: str) -> list[dict]:
    words = _words(query)
    # match on brand name plus salt/composition, so "cetirizine" finds "Cetzine 10mg"
    hay = [(str(_first(d, NAME_KEYS)) + " " + " ".join(str(d.get(k, "")) for k in COMP_KEYS)).lower() for d in raw]
    # prefer products matching every word ("dolo 650" should not return Dolo 500)
    strict = any(all(w in h for w in words) for h in hay)
    offers, seen = [], set()
    for d, h in zip(raw, hay):
        if words and not (all(w in h for w in words) if strict else any(w in h for w in words)):
            continue
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(_first(d, NAME_KEYS)))).strip()
        price_field = _first(d, PRICE_KEYS)
        price = _num(price_field)
        if isinstance(price_field, dict):
            mrp = _num(price_field.get("marked") or price_field.get("mrp"))
        else:
            mrp = _num(_first(d, MRP_KEYS))
            if not mrp and price_field is not d.get("price"):
                mrp = _num(d.get("price"))  # Apollo: price = MRP, specialPrice = selling price
        url = _first(d, URL_KEYS)
        if isinstance(url, str) and url and not url.startswith("http"):
            origin = "/".join(source["search"].split("/")[:3])
            url = origin + url if url.startswith("/") else source["product_prefix"] + url
        pack = _first(d, PACK_KEYS)
        pack = str(pack) if pack and not isinstance(pack, (dict, list)) else ""
        if (name.lower(), price) in seen:
            continue
        seen.add((name.lower(), price))
        units, unit = pack_units(pack, name)
        mrp = mrp if mrp and mrp >= price else None
        offers.append({
            "source": source["name"], "name": name, "pack": pack, "price": round(price, 2), "mrp": mrp,
            "discount_pct": round((mrp - price) / mrp * 100) if mrp and mrp > price else 0,
            "units": units, "unit": unit, "per_unit": round(price / units, 2) if units else None,
            "url": url if isinstance(url, str) and url.startswith("http") else None,
            "match": sum(_has_word(name.lower(), w) for w in words),
            "starts": bool(words) and name.lower().startswith(words[0]),
            "combo": bool(_COMBO.search(name)),
            # words beyond the search and the usual pack words: "Azithral SI 500" has 1, "Azithral 500 Tablet" has 0
            "extras": len({t for t in re.findall(r"[a-z]+", name.lower()) if t not in words and t not in _PACK_WORDS}),
        })
        if len(offers) >= 12:
            break
    return offers


_COMBO = re.compile(r"\bcombo\b|\bkit\b|\bpack of \d+\s*x|\+", re.I)
_PACK_WORDS = {"mg", "mcg", "gm", "g", "ml", "tablet", "tablets", "tab", "tabs", "capsule", "capsules", "cap", "caps", "strip",
               "of", "s", "syrup", "sachet", "sachets", "bottle", "pack", "in", "oral", "powder", "suspension", "liquid", "drops", "x"}


# ---------- site fetchers ----------

def _search_url(source: dict, query: str) -> str:
    return source["search"].format(q=quote_plus(query), qp=quote(query))


def _raw_page(query: str, source: dict) -> list[dict]:
    r = httpx.get(_search_url(source, query), headers=HEADERS, timeout=12, follow_redirects=True)
    r.raise_for_status()
    raw = []
    for blob in _json_blobs(r.text):
        _walk(blob, raw)
    return raw


def _raw_onemg(query: str, source: dict) -> list[dict]:
    url = ("https://www.1mg.com/pwa-dweb-api/api/v4/search/all?q=" + quote(query) +
           "&city=New%20Delhi&filter=&page_number=0&scroll_id=&per_page=12&types=sku,allopathy&sort=relevance")
    r = httpx.get(url, headers={**HEADERS, "Accept": "application/json", "Referer": _search_url(source, query)}, timeout=12)
    r.raise_for_status()
    raw = []
    _walk(r.json().get("data", {}).get("search_results", []), raw)
    return raw


_apollo = {"token": None, "at": 0.0, "device": str(uuid.uuid4())}
_apollo_lock = threading.Lock()


def _apollo_headers(fresh: bool = False) -> dict:
    base = {**HEADERS, "Accept": "application/json, text/plain, */*", "Origin": "https://www.apollopharmacy.in",
            "Referer": "https://www.apollopharmacy.in/", "x-device-id": _apollo["device"], "x-app-os": "web",
            "x-source-service": "PHARMA_AP_IN"}
    with _apollo_lock:
        if fresh or not _apollo["token"] or time.time() - _apollo["at"] > 6 * 3600:
            r = httpx.get(f"https://apigateway.apollo247.in/auth-service/accessToken?_nonce={uuid.uuid4()}", headers=base, timeout=12)
            r.raise_for_status()
            _apollo["token"], _apollo["at"] = r.json()["accessToken"], time.time()
    return {**base, "authorization": _apollo["token"], "content-type": "application/json",
            "x-unique-session-id": str(uuid.uuid4()), "x-token": ""}


def _raw_apollo(query: str, source: dict) -> list[dict]:
    body = {"query": query, "page": 1, "productsPerPage": 12, "selSortBy": "relevance", "filters": [], "pincode": ""}
    url = "https://apigateway.apollo247.in/search-service/v5/fullSearch"
    r = httpx.post(url, headers=_apollo_headers(), json=body, timeout=12)
    if r.status_code in (401, 403):  # token expired: get a new one once
        r = httpx.post(url, headers=_apollo_headers(fresh=True), json=body, timeout=12)
    r.raise_for_status()
    raw = []
    _walk(r.json(), raw)
    return raw


FETCHERS = {"page": _raw_page, "onemg": _raw_onemg, "apollo": _raw_apollo}


def _fetch_source(source: dict, query: str) -> dict:
    url = _search_url(source, query)
    if source["kind"] == "link":
        return {"source": source["name"], "url": url, "status": "open site to check", "live": False, "offers": []}
    try:
        offers = _to_offers(source, FETCHERS[source["kind"]](query, source), query)
        return {"source": source["name"], "url": url, "status": "ok" if offers else "not found", "live": True, "offers": offers}
    except httpx.HTTPStatusError as e:
        return {"source": source["name"], "url": url, "status": f"blocked ({e.response.status_code})", "live": True, "offers": []}
    except Exception as e:
        log.info("%s lookup failed: %s", source["name"], e)
        return {"source": source["name"], "url": url, "status": "unreachable", "live": True, "offers": []}


def _offline_rows(query: str) -> list[dict]:
    if not OFFLINE_CSV.exists():
        return []
    words = [w for w in _words(query) if len(w) > 2]
    rows = []
    with OFFLINE_CSV.open(encoding="utf-8", errors="ignore") as f:
        for row in csv.DictReader(f):
            hay = (row.get("name", "") + " " + row.get("composition", "")).lower()
            if words and all(w in hay for w in words):
                price = _num(row.get("price"))
                if price:
                    units, unit = pack_units(row.get("pack", ""), row.get("name", ""))
                    rows.append({"source": f"Offline list ({row.get('as_of', 'dataset')})", "name": row.get("name", ""),
                                 "pack": row.get("pack", ""), "price": price, "mrp": None, "discount_pct": 0,
                                 "units": units, "unit": unit, "per_unit": round(price / units, 2) if units else None,
                                 "url": None, "match": 0})
            if len(rows) >= 200:
                break
    rows.sort(key=lambda r: r["price"])
    return rows[:8]


def _wants_liquid(query: str) -> bool:
    return bool(_LIQUID.search(query))


def _best_match(offers: list[dict], liquid: bool = False) -> dict | None:
    """The offer on one site that best matches the search: most query words in its name, not a combo
    pack, name starting with the searched brand, the wanted form (tablets/sachets unless a syrup was
    searched), then the cheapest."""
    if not offers:
        return None

    def form_rank(o):
        if o["unit"] is None:
            return 1
        return 0 if (o["unit"] == "ml") == liquid else 2

    return min(offers, key=lambda o: (-o["match"], o["combo"], form_rank(o), o["extras"], not o["starts"], o["per_unit"] or o["price"]))


def _cheapest(best: list[dict]) -> tuple[dict | None, str]:
    """Compare like with like: only offers in the most common form (e.g. tablets) are ranked, by price
    per tablet/ml when every pack size is known, otherwise by pack price. Others are marked not comparable."""
    if not best:
        return None, "price"
    groups: dict = {}
    for o in best:
        groups.setdefault(o["unit"], []).append(o)
    unit = max(groups, key=lambda u: (len(groups[u]), u in SOLID_UNITS, u is not None))
    same = groups[unit]
    for o in best:
        o["comparable"] = o["unit"] == unit
    if unit is not None and all(o["per_unit"] for o in same):
        return min(same, key=lambda o: o["per_unit"]), "per_unit"
    return min(same, key=lambda o: o["price"]), "price"


def compare(db: Session, query: str, refresh: bool = False) -> dict:
    query = query.strip()[:80]
    key = query.lower()
    hours = get_settings().price_cache_hours
    cached = db.query(PriceCache).filter_by(query=key).first()
    if cached and not refresh:
        age = datetime.now(timezone.utc) - cached.fetched_at.replace(tzinfo=cached.fetched_at.tzinfo or timezone.utc)
        data = json.loads(cached.data)
        if age < timedelta(hours=hours) and "by_site" in data:
            data["cached"] = True
            return data

    if get_settings().live_prices:
        with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
            sources = list(pool.map(lambda s: _fetch_source(s, query), SOURCES))
    else:
        sources = [{"source": s["name"], "url": _search_url(s, query), "status": "live lookup disabled", "live": False, "offers": []}
                   for s in SOURCES]

    liquid = _wants_liquid(query)
    by_site = [{"source": s["source"], "url": s["url"], "status": s["status"], "live": s["live"], "best": _best_match(s["offers"], liquid)}
               for s in sources]
    best = [b["best"] for b in by_site if b["best"]]
    cheapest, basis = _cheapest(best)
    if cheapest:
        for b in by_site:
            o = b["best"]
            if o and o["comparable"]:
                o["vs_cheapest_pct"] = round(((o["per_unit"] if basis == "per_unit" else o["price"]) /
                                              (cheapest["per_unit"] if basis == "per_unit" else cheapest["price"]) - 1) * 100)
    offers = sorted([o for s in sources for o in s["offers"]] + _offline_rows(query), key=lambda o: o["price"])
    comparable = [b for b in best if b.get("comparable")]
    prices = [(b["per_unit"] * (cheapest["units"] or 1)) if basis == "per_unit" else b["price"] for b in comparable]
    data = {
        "query": query, "checked_at": datetime.now(timezone.utc).isoformat(), "cached": False,
        "by_site": by_site, "cheapest": cheapest, "compare_basis": basis,
        "sites_checked": sum(1 for s in sources if s["live"]), "sites_with_price": len(best),
        "saving": round(max(prices) - min(prices), 2) if len(prices) > 1 else 0,
        "offers": offers, "sources": [{k: s[k] for k in ("source", "url", "status")} for s in sources],
        "jan_aushadhi": JAN_AUSHADHI,
        "note": "Prices change often and can differ by city, pack size, coupons and delivery charges. "
                "Buy prescription medicines only with a valid prescription.",
    }
    if cached:
        cached.data, cached.fetched_at = json.dumps(data), datetime.now(timezone.utc)
    else:
        db.add(PriceCache(query=key, data=json.dumps(data)))
    db.commit()
    return data
