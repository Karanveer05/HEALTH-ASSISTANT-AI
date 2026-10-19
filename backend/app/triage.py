"""Symptom scoring and the dynamic follow-up question engine (steps 2-4 of the workflow)."""
from . import llm
from .knowledge import case_text, condition_map, conditions_data, has_phrase, patient_facts
from .schemas import FollowUpPlan, FollowUpQuestion

MAX_QUESTIONS = 10
MIN_QUESTIONS = 3
LAB_FLAG_DIR = {"low": "low", "critical_low": "low", "high": "high", "critical_high": "high"}


def score_conditions(text: str, labs: list[dict] | None = None) -> list[dict]:
    """Rule-based candidate conditions: weighted symptom phrases + lab signals."""
    lab_dirs = {l["test_id"]: LAB_FLAG_DIR.get(l["flag"]) for l in labs or [] if l.get("test_id")}
    out = []
    for c in conditions_data()["conditions"]:
        matched = [p for p in c["symptoms"] if has_phrase(text, p)]
        # "high fever" already covers "fever": don't count both
        matched = [p for p in matched if not any(p != q and p in q for q in matched)]
        score = sum(c["symptoms"][p] for p in matched)
        lab_hits = [f"{t} {d}" for t, d, w in c["lab_signals"] if lab_dirs.get(t) == d]
        score += sum(w for t, d, w in c["lab_signals"] if lab_dirs.get(t) == d)
        if score > 0:
            out.append({"id": c["id"], "name": c["name"], "score": score, "matched": matched, "lab_hits": lab_hits})
    out.sort(key=lambda x: -x["score"])
    return out


def _profile_brief(profile: dict) -> dict:
    return patient_facts(profile, ("age", "sex", "conditions", "allergies", "medications", "pregnant", "smoker", "alcohol"))


def _rule_lab_need(candidates: list[dict]) -> tuple[bool, list[str]]:
    tests: list[str] = []
    for cand in candidates[:2]:
        c = condition_map()[cand["id"]]
        if c["needs_lab"] and cand["score"] >= 3:
            tests += [t for t in c["suggested_tests"] if t not in tests]
    return bool(tests), tests


def _offline_plan(case: dict, candidates: list[dict]) -> FollowUpPlan:
    asked = {qa["question"].strip().lower() for qa in case.get("qa", [])}
    pool = []
    for cand in candidates[:3]:
        pool += condition_map()[cand["id"]]["follow_up"]
    pool += conditions_data()["generic_questions"]
    fresh, seen = [], set()
    for q in pool:
        key = q["q"].strip().lower()
        if key not in asked and key not in seen:
            seen.add(key)
            fresh.append(FollowUpQuestion(question=q["q"], type=q.get("type", "text"), options=q.get("options", [])))
    n = len(case.get("qa", []))
    need, tests = _rule_lab_need(candidates)
    enough = not fresh or n >= 6
    return FollowUpPlan(enough_info=enough, questions=[] if enough else fresh[:3], need_report=need,
                        suggested_tests=tests, reason="Rule-based question bank")


def next_questions(profile: dict, case: dict) -> dict:
    labs = case.get("labs", [])
    candidates = score_conditions(case_text(case), labs)
    n = len(case.get("qa", []))
    plan = None
    if n < MAX_QUESTIONS:
        plan = llm.generate(
            FollowUpPlan,
            "You are doing patient intake like a careful doctor. Based on the patient profile, complaint and answers so far, "
            "decide if you have enough information to suggest possible conditions. If not, ask 1-3 short, simple follow-up "
            "questions (one idea each, plain English, no medical jargon) that best narrow down the cause. Never repeat a question "
            "that was already asked. Usually 4-8 questions in total are enough. Set need_report=true only when a lab test would "
            "clearly change the assessment (e.g. fever > 2 days, suspected anemia, thyroid, diabetes, infection), and list "
            "common Indian lab test names in suggested_tests. Use type yes_no / choice (with options) / number / text.",
            {"profile": _profile_brief(profile), "complaint": case.get("complaint"), "duration": case.get("duration"),
             "severity_1_to_10": case.get("severity"), "other_symptoms": case.get("other_symptoms"),
             "answers_so_far": case.get("qa", []), "questions_asked": n,
             "rule_based_candidates": [c["name"] for c in candidates[:5]], "labs_uploaded": labs},
        )
    if plan is not None:
        asked = {qa["question"].strip().lower() for qa in case.get("qa", [])}
        plan.questions = [q for q in plan.questions if q.question.strip().lower() not in asked][:3]
        if not plan.questions and not plan.enough_info:
            plan = None
        elif n < MIN_QUESTIONS and plan.enough_info and plan.questions:
            plan.enough_info = False
    if plan is None:
        plan = _offline_plan(case, candidates)
    if n >= MAX_QUESTIONS:
        plan.enough_info, plan.questions = True, []
    # labs are essential for some conditions even if the LLM didn't ask
    need, tests = _rule_lab_need(candidates)
    if need and not labs:
        plan.need_report = True
        if not plan.suggested_tests:  # keep the LLM's own list when it gave one, to avoid near-duplicates
            plan.suggested_tests = tests
    if labs:
        plan.need_report = False
    return plan.model_dump()
