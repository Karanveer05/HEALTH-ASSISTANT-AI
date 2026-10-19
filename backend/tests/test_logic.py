from app import diet, emergency, labs, medication, triage
from app.agents import run_analysis
from app.knowledge import case_text

PROFILE = {"name": "Test", "age": 30, "sex": "male", "conditions": [], "allergies": [], "medications": [],
           "pregnant": False, "diet_preference": "veg", "region": "north", "wake_time": "07:00", "breakfast_time": "08:30",
           "lunch_time": "13:30", "snack_time": "17:30", "dinner_time": "20:30", "sleep_time": "22:30"}

LAB_TEXT = """
CITY DIAGNOSTICS - COMPLETE BLOOD COUNT
Haemoglobin 11.2 g/dL 13.0 - 17.0
Mean Corpuscular Hemoglobin (MCH) 29.5 pg 27 - 32
Total Leucocyte Count 3200 /cumm 4000 - 11000
Platelet Count 85000 /cumm 150000 - 410000
PCV 47 % 40 - 50
TSH (3rd generation) 2.1 mIU/L 0.4 - 4.5
HbA1c 5.4 %
Vitamin D (25-OH) 14.2 ng/mL 30 - 100
"""


def test_emergency_detected_and_negation():
    assert [g["id"] for g in emergency.detect("I have severe chest pain since 20 minutes")] == ["chest_pain"]
    assert emergency.detect("no chest pain, just a cough") == []
    assert emergency.detect("cough but no chest pain") == []
    assert "suicidal" in [g["id"] for g in emergency.detect("I want to die")]
    assert emergency.detect("mild headache and sneezing") == []


def test_lab_parsing_and_flags():
    found = {l["test_id"]: l for l in labs.parse_labs(LAB_TEXT, "male")}
    assert found["hemoglobin"]["value"] == 11.2 and found["hemoglobin"]["flag"] == "low"
    assert found["wbc"]["flag"] == "low"
    assert found["platelets"]["flag"] == "low"
    assert found["tsh"]["value"] == 2.1 and found["tsh"]["flag"] == "normal"  # "3rd" must not be read as the value
    assert found["hba1c"]["value"] == 5.4  # HbA1c must not be read as hemoglobin
    assert found["vitamin_d"]["value"] == 14.2 and found["vitamin_d"]["flag"] == "low"
    assert "mcv" not in found


def test_platelets_in_thousands_and_critical():
    l = labs.parse_labs("Platelets 18 x10^3/uL", "female")[0]
    assert l["flag"] == "critical_low"
    assert emergency.from_labs([l])[0]["id"] == "critical_lab"


def test_scoring_prefers_dengue_with_labs():
    case = {"complaint": "high fever for 3 days with pain behind eyes and joint pain", "qa": []}
    lab_list = labs.parse_labs(LAB_TEXT, "male")
    top = triage.score_conditions(case_text(case), lab_list)[0]
    assert top["id"] == "dengue"


def test_yes_answer_counts_question_words():
    case = {"complaint": "fever", "qa": [{"question": "Do you have a rash or bleeding gums?", "answer": "yes"},
                                         {"question": "Any loss of smell?", "answer": "no"}]}
    text = case_text(case)
    assert "bleeding gums" in text and "loss of smell" not in text


def test_followups_offline_then_enough():
    case = {"complaint": "sneezing and runny nose", "duration": "2 days", "severity": 3, "qa": []}
    plan = triage.next_questions(PROFILE, case)
    assert not plan["enough_info"] and 1 <= len(plan["questions"]) <= 3
    for _ in range(4):
        case["qa"] += [{"question": q["question"], "answer": "no"} for q in plan["questions"]]
        plan = triage.next_questions(PROFILE, case)
        if plan["enough_info"]:
            break
    assert plan["enough_info"]
    asked = [qa["question"] for qa in case["qa"]]
    assert len(asked) == len(set(asked)), "no question asked twice"


def test_dengue_blocks_ibuprofen_and_allergy_blocks_paracetamol():
    conds = [{"name": "Dengue", "matched_id": "dengue", "confidence": "medium"}]
    plan = medication.plan(PROFILE, conds)
    assert "paracetamol" in [m["id"] for m in plan["items"]]
    assert any("Ibuprofen" in a["name"] for a in plan["avoid"])
    allergic = {**PROFILE, "allergies": ["Paracetamol (rash)"]}
    plan = medication.plan(allergic, conds)
    assert "paracetamol" in [m["id"] for m in plan["excluded"]]


def test_interaction_excludes_ibuprofen_with_warfarin():
    p = {**PROFILE, "medications": ["Warfarin 5mg"]}
    plan = medication.plan(p, [{"name": "Migraine", "matched_id": "migraine", "confidence": "medium"}])
    ex = {m["id"]: m for m in plan["excluded"]}
    assert "ibuprofen" in ex and "warfarin" in " ".join(ex["ibuprofen"]["reasons"]).lower()


def test_timetable_and_charts_respect_diet_and_allergies():
    p = {**PROFILE, "allergies": ["peanuts", "milk"], "diet_preference": "veg"}
    conds = [{"name": "Common cold", "matched_id": "common_cold", "confidence": "medium"}]
    plan = medication.plan(p, conds)
    tt = diet.medicine_timetable(p, plan)
    assert any(r["medicine"].startswith("Cetirizine") and r["time"] == "22:15" for r in tt)
    chart = diet.build_chart(p, ["common_cold"], "with_medicines", tt)
    assert len(chart["days"]) == 7
    from app.knowledge import foods
    by_name = {f["name"]: f for f in foods()}
    for day in chart["days"]:
        for s in day["slots"]:
            for i in s["items"]:
                if i["kind"] == "food" and i["text"] in by_name:
                    f = by_name[i["text"]]
                    assert f["diet"] == "veg"
                    assert not {"peanut", "milk"} & set(f["allergens"]), f["name"]
    assert any(i["kind"] == "medicine" for d in chart["days"] for s in d["slots"] for i in s["items"])
    natural = diet.build_chart(p, ["common_cold"], "natural", [])
    items = [i for d in natural["days"] for s in d["slots"] for i in s["items"]]
    assert not any(i["kind"] == "medicine" for i in items)
    assert any(i["kind"] == "remedy" for i in items)


def test_allergy_typos_still_caught():
    from app.knowledge import fuzzy_matches
    assert diet._blocked_allergens({"allergies": ["penuts"]}) == {"peanut"}
    assert diet._blocked_allergens({"allergies": ["dust", "pollen"]}) == set()
    assert diet._blocked_allergens({"allergies": ["nuts"]}) == {"nuts"}
    assert diet._blocked_allergens({"allergies": ["lactose intolerant"]}) == {"milk"}
    assert fuzzy_matches("paracetmol", ["paracetamol"]) == ["paracetamol"]
    plan = medication.plan({**PROFILE, "allergies": ["paracetmol"]}, [{"name": "Dengue", "matched_id": "dengue", "confidence": "medium"}])
    assert "paracetamol" in [m["id"] for m in plan["excluded"]]


def test_pregnancy_never_applies_to_male():
    from app.knowledge import patient_facts
    from app.schemas import ProfileIn
    p = ProfileIn(name="A", age=21, sex="male", pregnant=True)
    assert p.pregnant is False
    assert "pregnant" not in patient_facts({"sex": "male", "pregnant": True}, ("sex", "pregnant"))
    assert patient_facts({"sex": "female", "pregnant": True}, ("sex", "pregnant"))["pregnant"] is True


def test_pdf_hides_pregnancy_for_male():
    import fitz
    from app.pdf_report import build_pdf
    case = {"complaint": "sneezing and runny nose", "duration": "2 days", "severity": 3, "qa": []}
    result = run_analysis({**PROFILE, "sex": "male"}, case, [])
    text = "".join(page.get_text() for page in fitz.open(stream=build_pdf(result, 1), filetype="pdf"))
    assert "Pregnant" not in text and "Vegetarian" in text
    result = run_analysis({**PROFILE, "sex": "female"}, case, [])
    text = "".join(page.get_text() for page in fitz.open(stream=build_pdf(result, 1), filetype="pdf"))
    assert "Pregnant" in text


def test_natural_plan_has_no_remedy_food_duplicates():
    chart = diet.build_chart(PROFILE, ["common_cold"], "natural", [])
    for day in chart["days"]:
        for s in day["slots"]:
            texts = [i["text"] for i in s["items"]]
            assert not ("Haldi (turmeric) milk" in texts and "Warm haldi milk (no sugar)" in texts)


def test_high_fever_not_double_counted():
    flu = next(c for c in triage.score_conditions(case_text({"complaint": "high fever", "qa": []})) if c["id"] == "influenza")
    assert flu["matched"] == ["high fever"]


def test_natural_plan_rules():
    mild = [{"name": "Common cold", "matched_id": "common_cold", "confidence": "medium"}]
    assert diet.natural_allowed("low", mild, [])[0]
    assert not diet.natural_allowed("high", mild, [])[0]
    serious = [{"name": "Dengue", "matched_id": "dengue", "confidence": "medium"}]
    assert not diet.natural_allowed("moderate", serious, [])[0]


def test_full_graph_offline():
    case = {"complaint": "high fever for 3 days with pain behind eyes and joint pain", "duration": "3 days", "severity": 7,
            "other_symptoms": "", "qa": [{"question": "Any red spots on skin, bleeding gums or nose bleeds?", "answer": "no"}]}
    result = run_analysis(PROFILE, case, labs.parse_labs(LAB_TEXT, "male"))
    assert result["analysis"]["conditions"][0]["matched_id"] == "dengue"
    assert result["risk"]["level"] == "high"
    assert result["diet"]["natural"] is None
    meds = [m["id"] for m in result["medication"]["items"]]
    assert "paracetamol" in meds and "ibuprofen" not in meds
    assert [a["agent"] for a in result["agents"]][:2] == ["Symptom Analysis Agent", "Medical Report Agent"]


def test_graph_emergency_short_circuits():
    case = {"complaint": "crushing chest pain and sweating", "duration": "30 minutes", "severity": 9, "qa": []}
    result = run_analysis(PROFILE, case, [])
    assert result["risk"]["level"] == "emergency"
    assert result["medication"] is None and result["emergency"]["guides"][0]["id"] == "chest_pain"
