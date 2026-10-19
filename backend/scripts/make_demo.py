"""Create a complete demo patient in the running app (http://127.0.0.1:8000 by default).

Usage (from backend/, with the server running):
    .venv\\Scripts\\python scripts\\make_demo.py [base_url]

Creates the account demo.patient@healthassist.com / demo1234 (or reuses it), fills a profile, starts a
health check, answers the AI's follow-up questions, uploads demo/sample_cbc_report.pdf, runs the
multi-agent analysis and saves price comparisons, so the full report is ready to show.
"""
import sys
from pathlib import Path

import httpx
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/") + "/api"
EMAIL, PASSWORD = "demo.patient@healthassist.com", "demo1234"
REPORT = Path(__file__).resolve().parent.parent / "demo" / "sample_cbc_report.pdf"

PROFILE = {
    "name": "Rahul Sharma", "age": 28, "sex": "male", "weight_kg": 72, "height_cm": 175,
    "conditions": [], "allergies": ["Penicillin"], "medications": [],
    "smoker": False, "alcohol": False, "diet_preference": "veg", "region": "north",
    "wake_time": "07:00", "breakfast_time": "08:30", "lunch_time": "13:30", "snack_time": "17:30",
    "dinner_time": "20:30", "sleep_time": "22:30",
    "emergency_contact_name": "Sunita Sharma (mother)", "emergency_contact_phone": "9876500000",
}
CASE = {
    "complaint": "High fever for 3 days with severe body ache, headache and pain behind the eyes",
    "duration": "3 days", "severity": 7, "other_symptoms": "Loss of appetite, mild nausea, joint pain",
}
# answers a patient with early dengue would give, matched by keywords in the AI's question
ANSWERS = [
    (("temperature", "how high", "measured"), "Up to 102.5 F, comes down with Dolo for a few hours"),
    (("bleed", "rash", "spots", "gums", "nose"), "No"),
    (("mosquito", "dengue in your area", "neighbo", "colony", "outbreak"), "Yes, two neighbours had dengue last week"),
    (("vomit",), "Nausea but no vomiting"),
    (("urine", "urinat"), "Passing urine normally"),
    (("abdominal", "stomach", "belly"), "No stomach pain"),
    (("chill", "shiver", "sweat"), "Mild chills, no shivering at fixed times"),
    (("medicine", "medication", "taken", "taking"), "Dolo 650 twice a day for 2 days"),
    (("travel",), "No travel"),
    (("breath", "cough", "chest"), "No"),
    (("smell", "taste"), "No"),
    (("drowsy", "confus", "dizz", "faint"), "Feeling weak but not dizzy"),
    (("eat", "drink", "fluid", "water", "appetite"), "Drinking about 2 litres, eating less than usual"),
]


def answer_for(q: dict) -> str:
    text = q["question"].lower()
    for keys, ans in ANSWERS:
        if any(k in text for k in keys):
            return ans
    if q.get("type") == "choice" and q.get("options"):
        return q["options"][0]
    return "No" if q.get("type") == "yes_no" else "Nothing else to add"


def make_report_pdf(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    ss = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm)
    rows = [["Test", "Result", "Unit", "Reference range"],
            ["Haemoglobin", "14.6", "g/dL", "13.0 - 17.0"],
            ["Total Leucocyte Count", "3200", "/cumm", "4000 - 11000"],
            ["Neutrophils", "38", "%", "40 - 75"],
            ["Lymphocytes", "52", "%", "20 - 45"],
            ["Platelet Count", "98000", "/cumm", "150000 - 410000"],
            ["PCV", "47", "%", "40 - 50"],
            ["SGOT", "68", "U/L", "0 - 40"],
            ["SGPT", "55", "U/L", "0 - 40"],
            ["Dengue NS1 Antigen", "POSITIVE", "", "Negative"]]
    t = Table(rows, colWidths=[60 * mm, 30 * mm, 25 * mm, 50 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .4, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3f1f3")),
                           ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]))
    doc.build([Paragraph("SUNRISE DIAGNOSTICS &amp; PATHOLOGY LAB (DEMO)", ss["Title"]),
               Paragraph("Patient: Rahul Sharma &nbsp; Age/Sex: 28 / M &nbsp; Sample: Blood &nbsp; Report: Complete Blood Count, LFT, Dengue NS1", ss["Normal"]),
               Spacer(1, 8), t, Spacer(1, 8),
               Paragraph("This is a sample report created for demonstration only.", ss["Italic"])])


def main():
    make_report_pdf(REPORT)
    c = httpx.Client(timeout=180)
    r = c.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        r = c.post(f"{BASE}/auth/register", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    c.headers["Authorization"] = f"Bearer {r.json()['token']}"
    c.put(f"{BASE}/profile", json=PROFILE).raise_for_status()
    print("profile saved:", PROFILE["name"])

    case = c.post(f"{BASE}/cases", json=CASE).json()
    cid = case["id"]
    print(f"case #{cid} started")
    for _ in range(5):
        plan = case["plan"]
        if plan["enough_info"] or not plan["questions"]:
            break
        answers = [{"question": q["question"], "answer": answer_for(q)} for q in plan["questions"]]
        for a in answers:
            print(f"  Q: {a['question']}\n  A: {a['answer']}")
        case = c.post(f"{BASE}/cases/{cid}/answers", json={"answers": answers}).json()
    print("suggested tests:", case["plan"].get("suggested_tests"))

    with REPORT.open("rb") as f:
        up = c.post(f"{BASE}/cases/{cid}/reports", files={"file": (REPORT.name, f, "application/pdf")}).json()
    print("report read:", up["upload"], "| abnormal:", [l["name"] for l in up["labs"] if l["flag"] != "normal"])

    res = c.post(f"{BASE}/cases/{cid}/analyze").json()["result"]
    print("risk:", res["risk"]["level"], "| engine:", res["engine"])
    for cond in res["analysis"]["conditions"]:
        print(f"  {cond['name']} [{cond['confidence']}]")
    for med in ("Dolo 650", "Electral"):
        p = c.post(f"{BASE}/cases/{cid}/prices", json={"medicine": med}).json()
        ch = p.get("cheapest")
        print(f"prices {med}: {p['sites_with_price']} sites, cheapest {ch and (ch['source'], ch['price'])}")
    print(f"\nDone. Log in as {EMAIL} / {PASSWORD} and open health check #{cid}.")


if __name__ == "__main__":
    main()
