"""Medical report processing: text extraction (PDF text layer -> Tesseract OCR -> Gemini vision)
and lab-value parsing. Flags (low/high/critical) are always computed in code, never by the LLM."""
import io
import logging
import re

import fitz  # PyMuPDF
from PIL import Image

from . import llm
from .config import get_settings
from .knowledge import lab_data, lab_map
from .schemas import LabExtraction

log = logging.getLogger("labs")

ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp"}
MAX_BYTES = 10 * 1024 * 1024

_NUM = re.compile(r"(?<![a-z0-9.])(\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)(?![a-z0-9])")
_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)")
_UPPER = re.compile(r"(?:<|less than|upto|up to)\s*(\d+(?:\.\d+)?)")
_LOWER = re.compile(r"(?:>|more than|above)\s*(\d+(?:\.\d+)?)")


# ---------- text extraction ----------

def _ocr_image(img: Image.Image) -> str:
    cmd = get_settings().tesseract_cmd
    if not cmd:
        return ""
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        return pytesseract.image_to_string(img.convert("L"), config="--psm 6")
    except Exception as e:
        log.warning("tesseract failed: %s", e)
        return ""


def _vision_text(data: bytes, mime: str) -> str:
    class _Text(LabExtraction):
        raw_text: str = ""
    out = llm.generate(_Text, "Read this medical report image. Put the full readable text in raw_text and every lab result in values.",
                       "(image attached)", images=[(data, mime)])
    return out.raw_text if out else ""


def extract_text(data: bytes, mime: str) -> tuple[str, str]:
    """Returns (text, method)."""
    if mime == "application/pdf":
        doc = fitz.open(stream=data, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        if len(text.strip()) >= 40:
            return text, "pdf-text"
        # scanned PDF: render pages and OCR them
        pages = []
        for page in doc:
            pix = page.get_pixmap(dpi=250)
            pages.append(_ocr_image(Image.open(io.BytesIO(pix.tobytes("png")))))
        text = "\n".join(pages)
        if len(text.strip()) >= 40:
            return text, "ocr-tesseract"
        first = doc[0].get_pixmap(dpi=200).tobytes("png") if len(doc) else b""
        return (_vision_text(first, "image/png"), "ocr-gemini") if first else ("", "none")

    img = Image.open(io.BytesIO(data))
    text = _ocr_image(img)
    if len(text.strip()) >= 40:
        return text, "ocr-tesseract"
    return _vision_text(data, mime), "ocr-gemini"


# ---------- parsing ----------

def _alias_index():
    pairs = [(a.lower(), t) for t in lab_data()["tests"] for a in t["aliases"]]
    return sorted(pairs, key=lambda p: -len(p[0]))


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def _range_for(test: dict, sex: str) -> tuple[float | None, float | None]:
    r = test.get(sex) or test.get("range") or test.get("male")
    return (r[0], r[1]) if r else (None, None)


def flag_value(test: dict, value: float, sex: str, lab_low=None, lab_high=None) -> dict:
    """Compare a value with the lab's printed range if present, else our reference range."""
    scaled = value
    if test.get("scale_if_below") and value < test["scale_if_below"]:
        scaled = value * 1000
    if lab_low is not None or lab_high is not None:
        low, high, v = lab_low, lab_high, value
    else:
        (low, high), v = _range_for(test, sex), scaled
    flag = "normal"
    if low is not None and v < low:
        flag = "low"
    elif high is not None and v > high:
        flag = "high"
    crit = test.get("critical")
    if crit:
        if scaled < crit[0]:
            flag = "critical_low"
        elif scaled > crit[1]:
            flag = "critical_high"
    meaning = ""
    if flag in ("low", "critical_low"):
        meaning = test.get("low_means", "")
    elif flag in ("high", "critical_high"):
        meaning = test.get("high_means", "")
    return {
        "test_id": test["id"], "name": test["name"], "value": value, "unit": test["unit"],
        "ref_low": low, "ref_high": high, "flag": flag, "meaning": meaning,
    }


def _printed_range(rest: str) -> tuple[float | None, float | None]:
    if m := _RANGE.search(rest):
        return float(m.group(1)), float(m.group(2))
    if m := _UPPER.search(rest):
        return None, float(m.group(1))
    if m := _LOWER.search(rest):
        return float(m.group(1)), None
    return None, None


def parse_labs(text: str, sex: str) -> list[dict]:
    excludes = lab_data().get("exclude", {})
    found: dict[str, dict] = {}
    index = _alias_index()
    for line in text.splitlines():
        low = line.lower()
        for alias, test in index:
            m = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", low)
            if not m:
                continue
            if any(x in low for x in excludes.get(test["id"], [])):
                continue
            if test["id"] in found:
                break
            rest = re.sub(r"\([^)]*\)", " ", low[m.end():])
            num = _NUM.search(rest)
            if not num:
                break
            value = _to_float(num.group(1))
            after = rest[num.end():]
            if "lakh" in after[:12]:
                value *= 100000
            lab_low, lab_high = _printed_range(after)
            # ignore printed ranges that are clearly in different units from the value
            if lab_high and (value > lab_high * 50 or value < (lab_low or 0) / 50):
                lab_low = lab_high = None
            found[test["id"]] = flag_value(test, value, sex, lab_low, lab_high)
            break
    return list(found.values())


def _match_test(name: str) -> dict | None:
    low = name.lower()
    for alias, test in _alias_index():
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", low):
            if not any(x in low for x in lab_data().get("exclude", {}).get(test["id"], [])):
                return test
    return None


def llm_parse(text: str, sex: str, already: list[dict]) -> list[dict]:
    """Ask the LLM to pull values the regex parser missed; flagging still happens in code."""
    out = llm.generate(LabExtraction, "Extract every lab test result (name, numeric value, unit, printed reference range) from this report text.", text[:12000])
    if not out:
        return []
    have = {l["test_id"] for l in already}
    extra = []
    for v in out.values:
        test = _match_test(v.name)
        if test and test["id"] not in have:
            lo, hi = _printed_range(v.reference_range.lower())
            extra.append(flag_value(test, v.value, sex, lo, hi))
            have.add(test["id"])
        elif not test:
            lo, hi = _printed_range(v.reference_range.lower())
            flag = "unknown"
            if lo is not None and v.value < lo:
                flag = "low"
            elif hi is not None and v.value > hi:
                flag = "high"
            elif lo is not None or hi is not None:
                flag = "normal"
            extra.append({"test_id": None, "name": v.name, "value": v.value, "unit": v.unit,
                          "ref_low": lo, "ref_high": hi, "flag": flag, "meaning": ""})
    return extra


def analyze_report(data: bytes, mime: str, sex: str) -> dict:
    text, method = extract_text(data, mime)
    labs = parse_labs(text, sex)
    if text.strip() and len(labs) < 3 and llm.providers():
        labs += llm_parse(text, sex, labs)
    return {"text": text, "method": method, "labs": labs}


def lab_by_id(test_id: str) -> dict | None:
    return lab_map().get(test_id)
