import io

import fitz
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from app import pricing
from app.config import get_settings
from app.main import app

client = TestClient(app)

PROFILE = {"name": "Test Patient", "age": 22, "sex": "male", "allergies": ["peanuts"], "medications": [],
           "diet_preference": "veg", "region": "north", "emergency_contact_name": "Papa", "emergency_contact_phone": "9876543210"}
REPORT_LINES = ["CBC REPORT", "Haemoglobin 14.1 g/dL 13.0 - 17.0", "Total Leucocyte Count 3100 /cumm 4000 - 11000",
                "Platelet Count 92000 /cumm 150000 - 410000", "PCV 46 % 40 - 50"]


def _register(email):
    r = client.post("/api/auth/register", json={"email": email, "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _pdf_bytes():
    doc = fitz.open()
    page = doc.new_page()
    for i, line in enumerate(REPORT_LINES):
        page.insert_text((50, 72 + i * 20), line, fontsize=12)
    return doc.tobytes()


def _png_bytes():
    img = Image.new("RGB", (1400, 420), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except OSError:
        font = ImageFont.load_default()
    for i, line in enumerate(REPORT_LINES):
        d.text((40, 30 + i * 70), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_auth_required_and_profile_first():
    assert client.get("/api/cases").status_code == 401
    h = _register("first@test.com")
    r = client.post("/api/cases", json={"complaint": "fever"}, headers=h)
    assert r.status_code == 400 and "profile" in r.json()["detail"].lower()


def test_full_flow():
    h = _register("flow@test.com")
    assert client.put("/api/profile", json=PROFILE, headers=h).status_code == 200

    r = client.post("/api/cases", json={"complaint": "High fever for 3 days with pain behind eyes and joint pain",
                                        "duration": "3 days", "severity": 7}, headers=h)
    assert r.status_code == 200, r.text
    case = r.json()
    assert case["new_emergency"] is None and case["plan"]["questions"]
    cid = case["id"]

    for _ in range(5):
        if case["plan"]["enough_info"]:
            break
        answers = [{"question": q["question"], "answer": "no"} for q in case["plan"]["questions"]]
        case = client.post(f"/api/cases/{cid}/answers", json={"answers": answers}, headers=h).json()
    assert case["plan"]["enough_info"]
    assert case["status"] == "report" and case["plan"]["suggested_tests"]

    r = client.post(f"/api/cases/{cid}/reports", files={"file": ("cbc.pdf", _pdf_bytes(), "application/pdf")}, headers=h)
    assert r.status_code == 200, r.text
    up = r.json()
    assert up["upload"]["method"] == "pdf-text" and up["upload"]["found"] == 4
    assert up["status"] == "ready"

    r = client.post(f"/api/cases/{cid}/analyze", headers=h)
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    assert res["analysis"]["conditions"][0]["matched_id"] == "dengue"
    assert res["risk"]["level"] == "high"
    assert len(res["diet"]["with_medicines"]["days"]) == 7

    r = client.post(f"/api/cases/{cid}/prices", json={"medicine": "paracetamol 650"}, headers=h)
    assert r.status_code == 200 and len(r.json()["by_site"]) == len(pricing.SOURCES)

    pdf = client.get(f"/api/cases/{cid}/report.pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and len(pdf.content) > 5000

    actions = [a["action"] for a in client.get("/api/audit", headers=h).json()]
    for needed in ("register", "case_create", "report_upload", "case_analyze", "report_export"):
        assert needed in actions

    # another user cannot see this case
    other = _register("other@test.com")
    assert client.get(f"/api/cases/{cid}", headers=other).status_code == 404
    assert client.get(f"/api/cases/{cid}/report.pdf", headers=other).status_code == 404

    assert client.delete(f"/api/cases/{cid}", headers=h).json()["ok"]


@pytest.mark.skipif(not get_settings().tesseract_cmd, reason="Tesseract not installed")
def test_image_report_ocr():
    h = _register("ocr@test.com")
    client.put("/api/profile", json=PROFILE, headers=h)
    cid = client.post("/api/cases", json={"complaint": "fever and body ache"}, headers=h).json()["id"]
    r = client.post(f"/api/cases/{cid}/reports", files={"file": ("cbc.png", _png_bytes(), "image/png")}, headers=h)
    assert r.status_code == 200, r.text
    up = r.json()
    assert up["upload"]["method"] == "ocr-tesseract"
    labs = {l["test_id"]: l for l in up["labs"]}
    assert labs["platelets"]["flag"] == "low" and labs["hemoglobin"]["value"] == 14.1
    client.delete(f"/api/cases/{cid}", headers=h)


def test_emergency_on_start_and_bad_upload():
    h = _register("emerg@test.com")
    client.put("/api/profile", json=PROFILE, headers=h)
    r = client.post("/api/cases", json={"complaint": "my father has crushing chest pain and is sweating"}, headers=h).json()
    assert r["new_emergency"]["guides"][0]["id"] == "chest_pain"
    assert any(n["number"] == "108" for n in r["new_emergency"]["numbers"])
    bad = client.post(f"/api/cases/{r['id']}/reports", files={"file": ("x.pdf", b"MZ not really a pdf", "application/pdf")}, headers=h)
    assert bad.status_code == 415


def test_login_lockout():
    client.post("/api/auth/register", json={"email": "lock@test.com", "password": "secret123"})
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": "lock@test.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "lock@test.com", "password": "secret123"}).status_code == 429
