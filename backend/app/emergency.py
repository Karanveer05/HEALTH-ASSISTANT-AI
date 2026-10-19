"""Rule-based red-flag detection. Runs before any AI step, so an emergency is never missed because of the LLM."""
from .knowledge import emergency_data, has_phrase, normalize


def guides() -> list[dict]:
    return emergency_data()["guides"]


def numbers() -> list[dict]:
    return emergency_data()["numbers"]


def guide(guide_id: str) -> dict | None:
    return next((g for g in guides() if g["id"] == guide_id), None)


def detect(text: str) -> list[dict]:
    low = normalize(text)
    return [g for g in guides() if any(has_phrase(low, k) for k in g["keywords"])]


def from_labs(labs: list[dict]) -> list[dict]:
    critical = [l for l in labs if l.get("flag", "").startswith("critical")]
    if not critical:
        return []
    g = dict(guide("critical_lab"))
    g["details"] = [f"{l['name']}: {l['value']} {l.get('unit', '')}" for l in critical]
    return [g]


def payload(found: list[dict]) -> dict | None:
    """Shape sent to the frontend's emergency screen."""
    if not found:
        return None
    return {"guides": found, "numbers": numbers()}
