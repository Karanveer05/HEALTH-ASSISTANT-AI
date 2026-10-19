"""Multi-agent analysis (step 7-11), orchestrated as a LangGraph state graph:

  symptom_agent -> report_agent -> knowledge_agent -> condition_agent -> risk_agent
        --(emergency)--> finalize
        --(otherwise)--> medication_agent -> diet_agent -> finalize

LLM agents (symptom, condition) always have a rule-based fallback. Safety-critical agents
(report flags, risk, medication, diet) are deterministic.
"""
from datetime import datetime, timezone
from typing import TypedDict

from langgraph.graph import END, StateGraph

from . import diet, emergency, llm, medication, rag
from .knowledge import case_text, condition_map, patient_facts
from .schemas import ConditionAnalysis, SymptomSummary
from .triage import score_conditions

LEVELS = ["low", "moderate", "high", "emergency"]
ADVICE = {
    "emergency": "Call 112 / 108 or go to the nearest emergency department now.",
    "high": "See a doctor today. Do not wait for symptoms to get worse.",
    "moderate": "See a doctor within 1-2 days, or sooner if you get worse.",
    "low": "Home care is usually enough. See a doctor if you are not better in 3 days or if new symptoms appear.",
}
DISCLAIMER = ("This report is AI-generated decision support, not a medical diagnosis or prescription. "
              "Please consult a qualified doctor before acting on it.")


class State(TypedDict, total=False):
    profile: dict
    case: dict
    labs: list
    emergencies: list
    symptoms: dict
    report: dict
    evidence: list
    analysis: dict
    risk: dict
    medication: dict
    diet: dict
    trace: list
    result: dict


def _log(state: State, agent: str, note: str):
    state.setdefault("trace", []).append({"agent": agent, "note": note})


def symptom_agent(state: State) -> State:
    case, labs = state["case"], state.get("labs", [])
    text = case_text(case)
    candidates = score_conditions(text, labs)
    summary = llm.generate(SymptomSummary, "Summarise the patient's key symptoms, timeline and important negatives (symptoms they said they do NOT have).",
                           {"complaint": case.get("complaint"), "duration": case.get("duration"), "severity": case.get("severity"),
                            "other_symptoms": case.get("other_symptoms"), "answers": case.get("qa", [])})
    key = summary.key_symptoms if summary else sorted({m for c in candidates for m in c["matched"]})
    state["symptoms"] = {"key_symptoms": key, "timeline": summary.timeline if summary else case.get("duration", ""),
                         "negatives": summary.notable_negatives if summary else [], "candidates": candidates[:6]}
    state["emergencies"] = emergency.detect(text)
    _log(state, "Symptom Analysis Agent", f"{len(candidates)} rule-based candidates; LLM summary {'used' if summary else 'unavailable'}")
    return state


def report_agent(state: State) -> State:
    labs = state.get("labs", [])
    abnormal = [l for l in labs if l["flag"] not in ("normal", "unknown")]
    state["report"] = {"labs": labs, "abnormal": abnormal,
                       "summary": [f"{l['name']} {l['value']:g} {l['unit']} is {l['flag'].replace('_', ' ')}. {l['meaning']}" for l in abnormal]}
    state["emergencies"] = state.get("emergencies", []) + emergency.from_labs(labs)
    _log(state, "Medical Report Agent", f"{len(labs)} lab values, {len(abnormal)} abnormal")
    return state


def knowledge_agent(state: State) -> State:
    s, case = state["symptoms"], state["case"]
    query = " ".join([case.get("complaint", ""), " ".join(s["key_symptoms"]),
                      " ".join(c["name"] for c in s["candidates"][:3]),
                      " ".join(f"{l['name']} {l['flag']}" for l in state["report"]["abnormal"])])
    hits = rag.retrieve(query, k=6)
    ids = {h["id"] for h in hits}
    for c in s["candidates"][:3]:  # make sure the top candidates' own pages are available as evidence
        if f"cond:{c['id']}" not in ids:
            hits += [h for h in rag.retrieve(c["name"], k=3) if h["id"] == f"cond:{c['id']}"][:1]
            ids.add(f"cond:{c['id']}")
    state["evidence"] = hits
    _log(state, "Medical Knowledge Agent", f"{len(hits)} passages retrieved ({rag.mode()} search)")
    return state


def _confidence(score: int, lab_hits: list) -> str:
    if score >= 8 and lab_hits:
        return "high"
    if score >= 5 or lab_hits:
        return "medium"
    return "low"


def _offline_analysis(state: State) -> dict:
    cands = state["symptoms"]["candidates"][:3]
    conds = []
    for c in cands:
        support = [f"Reported: {m}" for m in c["matched"]] + [f"Lab: {h}" for h in c["lab_hits"]]
        conds.append({"name": c["name"], "matched_id": c["id"], "confidence": _confidence(c["score"], c["lab_hits"]),
                      "reasoning": f"Your symptoms match the typical pattern of {c['name'].lower()} (match score {c['score']}).",
                      "supporting_findings": support, "against_findings": [], "reference_ids": [f"cond:{c['id']}"]})
    if not conds:
        conds = [{"name": "Unclear from the information given", "matched_id": None, "confidence": "low",
                  "reasoning": "The symptoms did not clearly match any condition in the knowledge base.",
                  "supporting_findings": [], "against_findings": [], "reference_ids": []}]
    return {"summary": "Rule-based analysis (AI model not available). Matches are based on reported symptoms and lab flags.",
            "conditions": conds, "contributing_factors": [],
            "uncertainty_note": "This is pattern matching, not a diagnosis. Several conditions can cause the same symptoms; a doctor's examination and tests are needed to confirm."}


def _match_id(name: str) -> str | None:
    low = name.lower()
    for cid, c in condition_map().items():
        short = c["name"].split(" (")[0].lower()
        if short in low or low in short or cid.replace("_", " ") in low:
            return cid
    return None


def condition_agent(state: State) -> State:
    evidence = state["evidence"]
    data = {
        "patient": patient_facts(state["profile"], ("age", "sex", "conditions", "allergies", "medications", "pregnant", "smoker", "alcohol")),
        "complaint": state["case"].get("complaint"), "duration": state["case"].get("duration"),
        "severity_1_to_10": state["case"].get("severity"), "answers": state["case"].get("qa", []),
        "symptom_summary": state["symptoms"], "abnormal_labs": state["report"]["abnormal"],
        "all_labs": state["report"]["labs"],
        "reference_passages": [{"id": e["id"], "title": e["title"], "text": e["text"]} for e in evidence],
        "known_condition_ids": {cid: c["name"] for cid, c in condition_map().items()},
    }
    out = llm.generate(
        ConditionAnalysis,
        "Act as the central orchestrator. Combine the symptom analysis, lab findings and reference passages into a list of "
        "up to 5 possible conditions or causes, most likely first. For each give confidence (low/medium/high; use high only "
        "when symptoms AND labs strongly agree), reasoning in plain language, supporting and against findings, and the ids of "
        "reference passages you relied on. Set matched_id to the matching key from known_condition_ids, or null. "
        "Also list contributing factors (lifestyle, age, existing conditions) and an honest uncertainty_note.",
        data,
    )
    if out:
        valid_ids = {e["id"] for e in evidence}
        analysis = out.model_dump()
        for c in analysis["conditions"]:
            c["reference_ids"] = [r for r in c["reference_ids"] if r in valid_ids]
            if c["matched_id"] not in condition_map():
                c["matched_id"] = _match_id(c["name"])
        analysis["source"] = llm.active_provider()
    else:
        analysis = _offline_analysis(state)
        analysis["source"] = "rules"
    state["analysis"] = analysis
    _log(state, "Orchestrator (condition synthesis)", f"{len(analysis['conditions'])} possible conditions via {analysis['source']}")
    return state


def risk_agent(state: State) -> State:
    profile, case = state["profile"], state["case"]
    level, reasons = "low", []

    def bump(to: str, why: str):
        nonlocal level
        if LEVELS.index(to) > LEVELS.index(level):
            level = to
        reasons.append(why)

    if state.get("emergencies"):
        bump("emergency", "Emergency warning signs: " + ", ".join(g["title"] for g in state["emergencies"]))
    if any(l["flag"].startswith("critical") for l in state.get("labs", [])):
        bump("high", "A lab value is in the critical range")
    elif state["report"]["abnormal"]:
        bump("moderate", f"{len(state['report']['abnormal'])} lab value(s) outside the normal range")
    for c in state["analysis"]["conditions"]:
        if not c.get("matched_id"):
            continue
        urgency = condition_map()[c["matched_id"]]["urgency"]
        if c["confidence"] == "low" and urgency == "high":
            urgency = "moderate"
        if urgency != "low":
            bump(urgency, f"Possible {c['name']} ({c['confidence']} confidence)")
    if (case.get("severity") or 0) >= 8:
        bump("moderate", f"You rated the severity {case['severity']}/10")
    age = profile.get("age") or 30
    pregnant = profile.get("pregnant") and profile.get("sex") == "female"
    if level == "low" and (age >= 65 or age < 5 or pregnant):
        bump("moderate", "Higher-risk group (age or pregnancy)")
    if not reasons:
        reasons.append("No warning signs found in your answers")
    state["risk"] = {"level": level, "reasons": reasons, "advice": ADVICE[level]}
    _log(state, "Risk Assessment Agent", f"risk = {level}")
    return state


def medication_agent(state: State) -> State:
    plan = medication.plan(state["profile"], state["analysis"]["conditions"])
    plan["timetable"] = diet.medicine_timetable(state["profile"], plan)
    state["medication"] = plan
    _log(state, "Medication Agent", f"{len(plan['items'])} suggested, {len(plan['excluded'])} excluded by safety checks")
    return state


def diet_agent(state: State) -> State:
    conds = state["analysis"]["conditions"]
    strong = [c["matched_id"] for c in conds if c.get("matched_id") and c["confidence"] in ("medium", "high")]
    ids = strong or [c["matched_id"] for c in conds if c.get("matched_id")][:1]
    allowed, why = diet.natural_allowed(state["risk"]["level"], conds, state.get("labs", []))
    state["diet"] = {
        "with_medicines": diet.build_chart(state["profile"], ids, "with_medicines", state["medication"]["timetable"]),
        "natural": diet.build_chart(state["profile"], ids, "natural", []) if allowed else None,
        "natural_allowed": allowed, "natural_reason": why,
    }
    _log(state, "Diet Agent", f"7-day chart built; natural plan {'offered' if allowed else 'not offered'}")
    return state


def finalize(state: State) -> State:
    profile, case = state["profile"], state["case"]
    used = {r for c in state["analysis"]["conditions"] for r in c.get("reference_ids", [])}
    refs = [{"id": e["id"], "title": e["title"], "source": e["source"]} for e in state["evidence"] if e["id"] in used or not used]
    state["result"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": {"llm": llm.active_provider(), "rag": rag.mode()},
        "patient": patient_facts(profile, ("name", "age", "sex", "conditions", "allergies", "medications", "pregnant", "diet_preference")),
        "symptoms": {"complaint": case.get("complaint"), "duration": case.get("duration"), "severity": case.get("severity"),
                     "other": case.get("other_symptoms"), "key_symptoms": state["symptoms"]["key_symptoms"],
                     "negatives": state["symptoms"]["negatives"]},
        "follow_up": case.get("qa", []),
        "labs": state["report"]["labs"], "abnormal_labs": state["report"]["abnormal"], "lab_summary": state["report"]["summary"],
        "analysis": state["analysis"], "risk": state["risk"],
        "emergency": emergency.payload(state.get("emergencies", [])),
        "medication": state.get("medication"), "diet": state.get("diet"),
        "references": refs, "agents": state.get("trace", []), "disclaimer": DISCLAIMER,
    }
    return state


def _route_after_risk(state: State) -> str:
    return "finalize" if state["risk"]["level"] == "emergency" else "medication_agent"


def _build_graph():
    g = StateGraph(State)
    for name, fn in [("symptom_agent", symptom_agent), ("report_agent", report_agent), ("knowledge_agent", knowledge_agent),
                     ("condition_agent", condition_agent), ("risk_agent", risk_agent), ("medication_agent", medication_agent),
                     ("diet_agent", diet_agent), ("finalize", finalize)]:
        g.add_node(name, fn)
    g.set_entry_point("symptom_agent")
    g.add_edge("symptom_agent", "report_agent")
    g.add_edge("report_agent", "knowledge_agent")
    g.add_edge("knowledge_agent", "condition_agent")
    g.add_edge("condition_agent", "risk_agent")
    g.add_conditional_edges("risk_agent", _route_after_risk, {"finalize": "finalize", "medication_agent": "medication_agent"})
    g.add_edge("medication_agent", "diet_agent")
    g.add_edge("diet_agent", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


GRAPH = _build_graph()


def run_analysis(profile: dict, case: dict, labs: list[dict]) -> dict:
    final = GRAPH.invoke({"profile": profile, "case": case, "labs": labs, "trace": []})
    return final["result"]
