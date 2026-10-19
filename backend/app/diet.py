"""Diet Agent logic: daily medicine timetable + 7-day diet charts in two modes.

with_medicines: meals + suggested medicines + the patient's current medicines, at the right times.
natural:        meals + home remedies + lifestyle steps, no medicines. Offered only for mild cases.
"""
import re
from datetime import datetime, timedelta

from .knowledge import condition_map, drug_map, foods, fuzzy_matches, matches_any, remedies_data, remedy_map
from .medication import current_medicines

SLOTS = ["early_morning", "breakfast", "mid_morning", "lunch", "evening", "dinner", "bedtime"]
SLOT_LABEL = {"early_morning": "Early morning", "breakfast": "Breakfast", "mid_morning": "Mid-morning",
              "lunch": "Lunch", "evening": "Evening snack", "dinner": "Dinner", "bedtime": "Bedtime"}
FOOD_LABEL = {"after": "after food", "before": "before food", "empty_stomach": "on an empty stomach",
              "any": "with or without food"}
ALLERGEN_WORDS = {"milk": ["milk", "dairy", "lactose"], "gluten": ["gluten", "wheat", "celiac", "coeliac"],
                  "nuts": ["nut", "almond", "walnut", "cashew"], "peanut": ["peanut", "groundnut"], "egg": ["egg"],
                  "fish": ["fish", "seafood"], "soy": ["soy"], "sesame": ["sesame", "til"]}
DIET_ALLOWED = {"veg": {"veg"}, "egg": {"veg", "egg"}, "nonveg": {"veg", "egg", "nonveg"}}
WEEKDAYS = ["Day 1", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6", "Day 7"]


def _t(hhmm: str, minutes: int = 0) -> str:
    return (datetime.strptime(hhmm, "%H:%M") + timedelta(minutes=minutes)).strftime("%H:%M")


def slot_times(p: dict) -> dict:
    b, l = datetime.strptime(p.get("breakfast_time", "08:30"), "%H:%M"), datetime.strptime(p.get("lunch_time", "13:30"), "%H:%M")
    return {
        "early_morning": _t(p.get("wake_time", "07:00"), 15), "breakfast": p.get("breakfast_time", "08:30"),
        "mid_morning": (b + (l - b) / 2).strftime("%H:%M"), "lunch": p.get("lunch_time", "13:30"),
        "evening": p.get("snack_time", "17:30"), "dinner": p.get("dinner_time", "20:30"),
        "bedtime": _t(p.get("sleep_time", "22:30"), -30),
    }


def _dose_slot_time(p: dict, slot: str) -> tuple[str, str]:
    """Returns (time, nearest chart slot) for a medicine timing slot."""
    table = {
        "on_waking": (_t(p.get("wake_time", "07:00")), "early_morning"),
        "before_breakfast": (_t(p.get("breakfast_time", "08:30"), -30), "early_morning"),
        "after_breakfast": (_t(p.get("breakfast_time", "08:30"), 15), "breakfast"),
        "before_lunch": (_t(p.get("lunch_time", "13:30"), -60), "mid_morning"),
        "after_lunch": (_t(p.get("lunch_time", "13:30"), 15), "lunch"),
        "after_dinner": (_t(p.get("dinner_time", "20:30"), 15), "dinner"),
        "bedtime": (_t(p.get("sleep_time", "22:30"), -15), "bedtime"),
    }
    return table[slot]


def _doses(p: dict, d: dict) -> list[dict]:
    """Expand a drug's pattern into timed doses for one day."""
    pattern, food = d["pattern"], FOOD_LABEL[d["food"]]
    if pattern == "as_needed":
        if not d.get("gap_hours"):
            return [{"time": "Through the day", "slot": "mid_morning", "note": "as needed"}]
        start = datetime.strptime(_t(p.get("breakfast_time", "08:30"), 15), "%H:%M")
        end = datetime.strptime(p.get("sleep_time", "22:30"), "%H:%M")
        out, t = [], start
        while t <= end and len(out) < d["max_per_day"]:
            slot = min(SLOTS, key=lambda s: abs((datetime.strptime(slot_times(p)[s], "%H:%M") - t).total_seconds()))
            out.append({"time": t.strftime("%H:%M"), "slot": slot,
                        "note": f"only if needed, {food}, at least {d['gap_hours']} h apart"})
            t += timedelta(hours=d["gap_hours"])
        return out
    slots = {"once": [d.get("slot", "after_breakfast")], "weekly": [d.get("slot", "after_lunch")],
             "twice": ["after_breakfast", "after_dinner"], "thrice": ["after_breakfast", "after_lunch", "after_dinner"]}[pattern]
    out = []
    for s in slots:
        time, chart_slot = _dose_slot_time(p, s)
        note = food + (" (once a week)" if pattern == "weekly" else "")
        out.append({"time": time, "slot": chart_slot, "note": note})
    return out


def medicine_timetable(profile: dict, med_plan: dict) -> list[dict]:
    rows = []
    for item in med_plan["items"]:
        d = drug_map()[item["id"]]
        for dose in _doses(profile, d):
            rows.append({"time": dose["time"], "slot": dose["slot"], "medicine": d["name"],
                         "dose": item["dose"], "instruction": dose["note"], "source": "suggested for review",
                         "weekly": d["pattern"] == "weekly", "prescription_only": not d["otc"]})
    for d in current_medicines(profile):
        if d["id"] in {i["id"] for i in med_plan["items"]} or d["pattern"] == "as_needed":
            continue
        for dose in _doses(profile, d):
            rows.append({"time": dose["time"], "slot": dose["slot"], "medicine": d["patient_label"],
                         "dose": "as prescribed", "instruction": dose["note"], "source": "your current medicine",
                         "weekly": d["pattern"] == "weekly", "prescription_only": not d["otc"]})
    rows.sort(key=lambda r: (r["time"] == "Through the day", r["time"]))
    return rows


# ---------- diet ----------

def _diet_rules(profile: dict, condition_ids: list[str]) -> tuple[set, set, list[str]]:
    include, avoid, tips = set(), set(), []
    for cid in condition_ids:
        c = condition_map()[cid]
        include |= set(c["diet"]["include"])
        avoid |= set(c["diet"]["avoid"])
    ptxt = " ".join(profile.get("conditions", [])).lower()
    if any(w in ptxt for w in ("diabet", "sugar")):
        include |= {"low_gi", "high_fiber"}
        avoid |= {"high_sugar", "sweet_fruit"}
        tips.append("Diabetes: no sugar, sweets or fruit juice; prefer whole grains and millets.")
    if any(w in ptxt for w in ("hypertension", "blood pressure", " bp", "bp ")) or ptxt.startswith("bp"):
        include.add("low_salt")
        avoid.add("high_salt")
        tips.append("High BP: under 5 g salt a day; avoid pickles, papad, chips and packaged food.")
    if "kidney" in ptxt:
        avoid.add("potassium")
        tips.append("Kidney disease: follow your doctor's fluid, potassium and protein limits.")
    if "caffeine_with_meals" in avoid:
        tips.append("Avoid tea/coffee within 1 hour of meals; they reduce iron absorption.")
    avoid.discard("caffeine_with_meals")
    return include, avoid, tips


def _blocked_allergens(profile: dict) -> set:
    text = " ".join(profile.get("allergies", []))
    blocked = {a for a, words in ALLERGEN_WORDS.items() if a != "nuts" and fuzzy_matches(text, words)}
    # tree nuts: whole words only, so "peanuts" doesn't also block almonds and walnuts
    if re.search(r"\b(tree ?)?nuts?\b|almond|walnut|cashew|pista|badam|kaju", text.lower()):
        blocked.add("nuts")
    return blocked


def _food_ok(f: dict, profile: dict, avoid: set, blocked: set, strict_region: bool) -> bool:
    if f["diet"] not in DIET_ALLOWED[profile.get("diet_preference", "veg")]:
        return False
    if blocked & set(f["allergens"]):
        return False
    tags = set(f["tags"])
    if "dairy_heavy" in avoid and "dairy" in tags and "probiotic" not in tags:
        return False
    if tags & (avoid - {"dairy_heavy"}):
        return False
    region = profile.get("region", "any")
    return not strict_region or region == "any" or f["region"] in ("any", region)


# foods that are the same thing as a home remedy; skipped in the natural plan so they don't appear twice
REMEDY_AS_FOOD = {"turmeric_milk": "turmeric_milk_f", "tulsi_tea": "tulsi_ginger_tea", "chamomile_tea": "chamomile_f",
                  "coconut_water": "coconut_water_f", "jeera_water": "jeera_water_f", "methi_water": "methi_water_f",
                  "nimbu_pani": "nimbu_pani_f", "amla": "amla_fresh"}


def _pick_meals(profile: dict, include: set, avoid: set, skip: set = frozenset()) -> dict:
    """For each slot, a ranked list of suitable foods (best include-tag match first)."""
    blocked = _blocked_allergens(profile)
    ranked = {}
    for slot in SLOTS:
        options = [f for f in foods() if slot in f["slots"] and f["id"] not in skip]
        pool = [f for f in options if _food_ok(f, profile, avoid, blocked, True)]
        if not pool:
            pool = [f for f in options if _food_ok(f, profile, avoid, blocked, False)]
        pool.sort(key=lambda f: (-len(include & set(f["tags"])), f["id"]))
        ranked[slot] = pool[:5]
    return ranked


def _remedies(profile: dict, condition_ids: list[str]) -> list[dict]:
    pregnant = profile.get("pregnant") and profile.get("sex") == "female"
    ptxt = " ".join(profile.get("conditions", []) + (["pregnant"] if pregnant else [])).lower()
    blocked = _blocked_allergens(profile)
    out, seen = [], set()
    for cid in condition_ids:
        for rid in condition_map()[cid]["remedies"]:
            r = remedy_map()[rid]
            if rid in seen or matches_any(ptxt, r["avoid_if"]) or blocked & set(r["allergens"]):
                continue
            seen.add(rid)
            out.append(r)
    return out


def build_chart(profile: dict, condition_ids: list[str], mode: str, timetable: list[dict]) -> dict:
    include, avoid, tips = _diet_rules(profile, condition_ids)
    remedies = _remedies(profile, condition_ids) if mode == "natural" else []
    ranked = _pick_meals(profile, include, avoid, {REMEDY_AS_FOOD[r["id"]] for r in remedies if r["id"] in REMEDY_AS_FOOD})
    times = slot_times(profile)
    days = []
    for di, day in enumerate(WEEKDAYS):
        slots = []
        for si, slot in enumerate(SLOTS):
            items = []
            pool = ranked[slot]
            if pool:
                f = pool[(di + si) % len(pool)]
                items.append({"kind": "food", "text": f["name"], "kcal": f["kcal"]})
            elif slot in ("breakfast", "lunch", "dinner"):
                items.append({"kind": "food", "text": "Light home-cooked meal", "kcal": None})
            if mode == "with_medicines":
                for row in timetable:
                    if row["slot"] == slot and (not row["weekly"] or di == 0):
                        items.append({"kind": "medicine", "text": f"{row['medicine']} ({row['dose']})",
                                      "time": row["time"], "note": row["instruction"]})
            else:
                for r in remedies:
                    rs = r["slot"]
                    if rs == slot or (rs == "after_meals" and slot in ("lunch", "dinner")):
                        items.append({"kind": "remedy", "text": r["name"], "note": r["how"]})
            if items:
                slots.append({"slot": slot, "label": SLOT_LABEL[slot], "time": times[slot], "items": items})
        days.append({"day": day, "slots": slots, "kcal": sum(i.get("kcal") or 0 for s in slots for i in s["items"])})

    self_care = []
    for cid in condition_ids:
        self_care += [s for s in condition_map()[cid]["self_care"] if s not in self_care]
    lifestyle = remedies_data()["lifestyle"]["default"] + remedies_data()["lifestyle"]["sick"]
    chart = {
        "mode": mode, "days": days, "focus_tags": sorted(include), "avoid_tags": sorted(avoid),
        "tips": tips + self_care, "lifestyle": lifestyle,
        "through_day": [r["name"] + ": " + r["how"] for r in remedies if r["slot"] in ("through_day", "as_needed")],
    }
    if mode == "natural" and profile.get("medications"):
        chart["keep_taking"] = ("This plan adds no new medicines. Keep taking the medicines your doctor prescribed: "
                                + ", ".join(profile["medications"]) + ".")
    return chart


def natural_allowed(risk_level: str, conditions: list[dict], labs: list[dict]) -> tuple[bool, str]:
    if risk_level in ("high", "emergency"):
        return False, "Not offered: the risk level is high, so medical treatment may be needed."
    if any(l.get("flag", "").startswith("critical") for l in labs):
        return False, "Not offered: a lab value is in a critical range."
    relevant = [c for c in conditions if c.get("matched_id") and c["confidence"] in ("medium", "high")] or \
               [c for c in conditions if c.get("matched_id")][:1]
    if not relevant:
        return False, "Not offered: the cause is unclear, so please see a doctor first."
    not_mild = [c["name"] for c in relevant if not condition_map()[c["matched_id"]]["mild"]]
    if not_mild:
        return False, f"Not offered for {', '.join(not_mild)}: this usually needs a doctor's treatment. The diet can still support recovery alongside medicines."
    return True, "Offered because the likely cause is mild. Switch to medicines or see a doctor if you are not better in 3 days."
