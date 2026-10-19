"""Medication Agent logic: clinician-reviewable medicine information with allergy, condition and
interaction checks. Medicines are chosen from the curated list only, never by the LLM."""
import re

from .knowledge import condition_map, drug_map, drugs_data, fuzzy_matches, matches_any

DISCLAIMER = ("Information for review by a doctor or pharmacist. This is not a prescription. "
              "Do not start, stop or change any medicine without professional advice.")


def _patient_context(profile: dict, condition_ids: list[str]) -> str:
    parts = list(profile.get("conditions", []))
    if profile.get("pregnant") and profile.get("sex") == "female":
        parts.append("pregnant")
    if profile.get("alcohol"):
        parts.append("alcohol")
    parts += condition_ids
    return " ".join(parts).lower()


def current_medicines(profile: dict) -> list[dict]:
    """Map the patient's own medicine list onto known drugs (by name or brand) for timing guidance."""
    out = []
    for med in profile.get("medications", []):
        low = med.lower()
        for d in drugs_data()["drugs"]:
            names = [d["id"].replace("_", " "), d["name"].split(" (")[0].lower()] + [b.lower() for b in d["brands"]]
            names += [b.lower().split()[0] for b in d["brands"] if len(b.split()[0]) >= 5]
            if any(re.search(rf"\b{re.escape(n)}\b", low) for n in names if n):
                out.append({**d, "patient_label": med})
                break
    return out


def plan(profile: dict, conditions: list[dict]) -> dict:
    """conditions: possible conditions with matched_id + confidence."""
    strong = [c for c in conditions if c.get("matched_id") and c["confidence"] in ("medium", "high")]
    chosen = strong or [c for c in conditions if c.get("matched_id")][:1]
    cond_ids = [c["matched_id"] for c in chosen]
    allergy_text = " ".join(profile.get("allergies", []))
    meds_text = " ".join(profile.get("medications", [])).lower()
    context = _patient_context(profile, cond_ids)

    avoid_ids = {}
    for cid in cond_ids:
        for drug_id in condition_map()[cid]["avoid_meds"]:
            avoid_ids.setdefault(drug_id, []).append(condition_map()[cid]["name"])

    items, excluded, seen = [], [], set()
    for cid in cond_ids:
        for drug_id in condition_map()[cid]["meds"]:
            if drug_id in seen:
                continue
            seen.add(drug_id)
            d = drug_map()[drug_id]
            reasons, warnings = [], list(d["warnings"])
            if hit := fuzzy_matches(allergy_text, d["allergy_terms"]):
                reasons.append(f"You reported an allergy that matches this medicine ({', '.join(hit)})")
            if hit := matches_any(context, d["avoid_if"]):
                reasons.append(f"Not advised with: {', '.join(hit)}")
            if drug_id in avoid_ids:
                reasons.append(f"Should be avoided in suspected {', '.join(avoid_ids[drug_id])}")
            interactions = []
            for ix in d["interactions"]:
                hit = ["your other medicines"] if ix["terms"] == ["*"] and meds_text else matches_any(meds_text, ix["terms"])
                if not hit:
                    continue
                interactions.append({"with": ", ".join(hit), "severity": ix["severity"], "note": ix["note"]})
                if ix["severity"] == "major":
                    reasons.append(f"Major interaction with {', '.join(hit)}: {ix['note']}")
            entry = {
                "id": drug_id, "name": d["name"], "brands": d["brands"], "purpose": d["purpose"],
                "for_condition": condition_map()[cid]["name"],
                "dose": d["dose"] if d["otc"] else "Only as prescribed by your doctor",
                "frequency": d["max_text"], "food": d["food"], "prescription_only": not d["otc"],
                "interactions": interactions, "warnings": warnings, "source": d["source"],
            }
            if reasons:
                excluded.append({**entry, "reasons": reasons})
            else:
                items.append(entry)

    avoid = [{"name": drugs_data()["avoid_names"].get(k, drug_map().get(k, {}).get("name", k)),
              "reason": f"Avoid in suspected {', '.join(v)}"} for k, v in avoid_ids.items()]
    return {"items": items, "excluded": excluded, "avoid": avoid,
            "current": [{"name": m["patient_label"], "matched": m["name"], "food": m["food"]} for m in current_medicines(profile)],
            "disclaimer": DISCLAIMER}
