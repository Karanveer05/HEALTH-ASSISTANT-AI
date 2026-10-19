"""Final structured healthcare report as a PDF (step 11)."""
import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_ss["Title"], fontSize=17, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=_ss["Heading2"], fontSize=12.5, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#0b5d6b"))
BODY = ParagraphStyle("b", parent=_ss["BodyText"], fontSize=9.2, leading=12.5)
SMALL = ParagraphStyle("s", parent=BODY, fontSize=8, leading=10.5, textColor=colors.HexColor("#555555"))
CELL = ParagraphStyle("c", parent=BODY, fontSize=8.3, leading=10.5)
RISK_COLOR = {"low": "#2e7d32", "moderate": "#b26a00", "high": "#c62828", "emergency": "#b71c1c"}


def P(text, style=BODY):
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), style)


def _table(rows, widths, header=True):
    data = [[P(c, CELL) if not isinstance(c, Paragraph) else c for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d3d6")),
             ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3f1f3")))
    t.setStyle(TableStyle(style))
    return t


def _n(v):
    return "" if v is None else (int(v) if float(v).is_integer() else v)


def _bullets(items):
    return [P(f"• {i}") for i in items]


def _chart(story, chart, title):
    story.append(P(title, H2))
    for day in chart["days"]:
        rows = [[day["day"], "Time", "What to have"]]
        for s in day["slots"]:
            lines = []
            for i in s["items"]:
                prefix = {"medicine": "[Medicine] ", "remedy": "[Natural] "}.get(i["kind"], "")
                note = f" - {i['note']}" if i.get("note") and i["kind"] == "medicine" else ""
                lines.append(prefix + i["text"] + note)
            rows.append([s["label"], s["time"], "\n".join(lines)])
        story.append(_table(rows, [30 * mm, 18 * mm, 127 * mm]))
        story.append(Spacer(1, 4))
    if chart.get("keep_taking"):
        story.append(P(chart["keep_taking"]))
    if chart.get("through_day"):
        story += _bullets(chart["through_day"])
    if chart.get("tips"):
        story.append(P("Tips", BODY))
        story += _bullets(chart["tips"])


def build_pdf(result: dict, case_id: int) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"Healthcare report #{case_id}")
    s, pt = [], result["patient"]
    s.append(P("AI Healthcare Assistance Report", H1))
    s.append(P(f"Report #{case_id} · generated {datetime.fromisoformat(result['generated_at']).strftime('%d %b %Y, %H:%M')} UTC "
               f"· engine: {result['engine']['llm']} + {result['engine']['rag']} retrieval", SMALL))
    s.append(P(result["disclaimer"], SMALL))

    s.append(P("1. Patient information", H2))
    s.append(_table([["Name", pt.get("name"), "Age / Sex", f"{pt.get('age')} / {pt.get('sex')}"],
                     ["Conditions", ", ".join(pt.get("conditions") or []) or "None", "Allergies", ", ".join(pt.get("allergies") or []) or "None"],
                     ["Current medicines", ", ".join(pt.get("medications") or []) or "None"]
                     + (["Pregnant", "Yes" if pt.get("pregnant") else "No"] if pt.get("sex") == "female"
                        else ["Diet", {"veg": "Vegetarian", "egg": "Eggetarian", "nonveg": "Non-vegetarian"}.get(pt.get("diet_preference"), "-")])],
                    [32 * mm, 56 * mm, 30 * mm, 57 * mm], header=False))

    sy = result["symptoms"]
    s.append(P("2. Reported symptoms", H2))
    s.append(P(f"Main problem: {sy['complaint']}  ·  Duration: {sy.get('duration') or '-'}  ·  Severity: {sy.get('severity')}/10"))
    if sy.get("other"):
        s.append(P(f"Other symptoms: {sy['other']}"))
    if sy.get("key_symptoms"):
        s.append(P("Key symptoms: " + ", ".join(sy["key_symptoms"])))

    if result["follow_up"]:
        s.append(P("3. Follow-up answers", H2))
        s.append(_table([["Question", "Answer"]] + [[q["question"], q["answer"]] for q in result["follow_up"]], [110 * mm, 65 * mm]))

    s.append(P("4. Laboratory findings", H2))
    if result["labs"]:
        rows = [["Test", "Value", "Reference", "Status"]]
        for l in result["labs"]:
            rows.append([l["name"], f"{_n(l['value'])} {l['unit']}", f"{_n(l['ref_low'])} - {_n(l['ref_high'])}", l["flag"].replace("_", " ").upper()])
        s.append(_table(rows, [60 * mm, 40 * mm, 40 * mm, 35 * mm]))
        if result["lab_summary"]:
            s.append(P("5. Abnormal values", H2))
            s += _bullets(result["lab_summary"])
    else:
        s.append(P("No lab report was uploaded."))

    a = result["analysis"]
    s.append(P("6. Possible conditions / causes", H2))
    s.append(P(a["summary"]))
    rows = [["Possible condition", "Confidence", "Reasoning and findings"]]
    for c in a["conditions"]:
        detail = c["reasoning"]
        if c["supporting_findings"]:
            detail += "\nFor: " + "; ".join(c["supporting_findings"])
        if c["against_findings"]:
            detail += "\nAgainst: " + "; ".join(c["against_findings"])
        rows.append([c["name"], c["confidence"].upper(), detail])
    s.append(_table(rows, [48 * mm, 22 * mm, 105 * mm]))
    s.append(P("Uncertainty: " + a["uncertainty_note"], SMALL))
    if a.get("contributing_factors"):
        s.append(P("Contributing factors: " + ", ".join(a["contributing_factors"])))

    r = result["risk"]
    s.append(P("7. Risk level", H2))
    s.append(Paragraph(f'<font color="{RISK_COLOR[r["level"]]}"><b>{r["level"].upper()}</b></font> - {escape(r["advice"])}', BODY))
    s += _bullets(r["reasons"])
    if result.get("emergency"):
        for g in result["emergency"]["guides"]:
            s.append(P(f"Emergency: {g['title']}", BODY))
            s += _bullets(g["steps"])

    med = result.get("medication")
    if med:
        s.append(P("8. Medication information for clinician review", H2))
        s.append(P(med["disclaimer"], SMALL))
        if med["items"]:
            rows = [["Medicine", "Purpose", "Dose / frequency", "Notes"]]
            for m in med["items"]:
                notes = "; ".join(m["warnings"] + [f"{i['severity']} interaction with {i['with']}: {i['note']}" for i in m["interactions"]])
                rows.append([m["name"] + (" (Rx)" if m["prescription_only"] else ""), m["purpose"], f"{m['dose']}. {m['frequency']}", notes])
            s.append(_table(rows, [38 * mm, 45 * mm, 45 * mm, 47 * mm]))
        for m in med["excluded"]:
            s.append(P(f"Not suggested - {m['name']}: {'; '.join(m['reasons'])}"))
        for v in med["avoid"]:
            s.append(P(f"Avoid {v['name']}: {v['reason']}"))
        if med.get("timetable"):
            s.append(P("9. Medication schedule", H2))
            s.append(_table([["Time", "Medicine", "Dose", "How"]] + [[t["time"], t["medicine"], t["dose"], t["instruction"]] for t in med["timetable"]],
                            [22 * mm, 55 * mm, 45 * mm, 53 * mm]))

    prices = result.get("prices") or {}
    if prices:
        s.append(P("10. Medicine price comparison", H2))
        rows = [["Medicine", "Website", "Product / pack", "Price (Rs)", "Per unit"]]
        for med_name, data in prices.items():
            cheapest = data.get("cheapest") or {}
            for site in data.get("by_site", []):
                o = site.get("best")
                if not o:
                    continue
                tag = " (cheapest)" if o["source"] == cheapest.get("source") and o["name"] == cheapest.get("name") else ""
                rows.append([med_name, o["source"] + tag, f"{o['name']} {o.get('pack') or ''}", f"{o['price']:.2f}",
                             f"{o['per_unit']:.2f}/{o['unit']}" if o.get("per_unit") else "-"])
        if len(rows) > 1:
            s.append(_table(rows, [28 * mm, 34 * mm, 68 * mm, 22 * mm, 23 * mm]))
        s.append(P("Live prices from PharmEasy, Netmeds, Tata 1mg and Apollo Pharmacy at the time of checking; they change often.", SMALL))

    d = result.get("diet")
    if d:
        s.append(PageBreak())
        _chart(s, d["with_medicines"], "11. 7-day diet chart with medicines")
        if d.get("natural"):
            s.append(PageBreak())
            _chart(s, d["natural"], "12. 7-day natural plan (no medicines)")
        else:
            s.append(P("Natural (no-medicine) plan: " + d["natural_reason"], SMALL))

    s.append(P("References / evidence", H2))
    s += [P(f"• {ref['title']} - {ref['source']}", SMALL) for ref in result["references"]]
    s.append(P("Recommendation", H2))
    s.append(P("Please consult a qualified healthcare professional to confirm any condition and before taking any medicine. "
               "In an emergency call 112 or 108."))
    doc.build(s)
    return buf.getvalue()
