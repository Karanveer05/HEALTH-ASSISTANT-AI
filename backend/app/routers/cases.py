import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import agents, emergency, labs, pricing, triage
from ..config import UPLOAD_DIR
from ..db import get_db
from ..knowledge import AFFIRMATIVE
from ..models import Case, Profile, ReportFile, User
from ..pdf_report import build_pdf
from ..schemas import AnswersIn, CaseStart
from ..security import audit, current_user, dec, enc, encrypt_bytes

router = APIRouter(prefix="/api/cases", tags=["cases"])

MAGIC = {b"%PDF": "application/pdf", b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg", b"RIFF": "image/webp"}


def _profile(db: Session, user: User) -> dict:
    p = db.get(Profile, user.id)
    if not p:
        raise HTTPException(400, "Please complete your profile first")
    return dec(p.data_enc)


def _case(db: Session, user: User, case_id: int) -> Case:
    c = db.get(Case, case_id)
    if not c or c.user_id != user.id:  # owners only
        raise HTTPException(404, "Case not found")
    return c


def _out(db: Session, c: Case) -> dict:
    data = dec(c.data_enc)
    reports = db.query(ReportFile).filter_by(case_id=c.id).order_by(ReportFile.id).all()
    flags = [emergency.guide(g) for g in data.get("emergency_ids", [])]
    return {
        "id": c.id, "status": c.status, "created_at": c.created_at.isoformat(),
        "complaint": data["complaint"], "duration": data.get("duration"), "severity": data.get("severity"),
        "other_symptoms": data.get("other_symptoms"), "qa": data.get("qa", []), "plan": data.get("plan"),
        "labs": data.get("labs", []),
        "reports": [{"id": r.id, "filename": r.filename, "method": dec(r.labs_enc, {}).get("method"),
                     "count": len(dec(r.labs_enc, {}).get("labs", []))} for r in reports],
        "emergency": emergency.payload([g for g in flags if g]) if flags else None,
        "result": dec(c.result_enc),
    }


def _flag_emergencies(data: dict, found: list[dict]) -> list[dict]:
    known = data.setdefault("emergency_ids", [])
    new = [g for g in found if g["id"] not in known]
    known += [g["id"] for g in new]
    return new


def _status_from_plan(plan: dict) -> str:
    if not plan["enough_info"]:
        return "questions"
    return "report" if plan["need_report"] else "ready"


@router.post("")
def start_case(body: CaseStart, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = _profile(db, user)
    data = {**body.model_dump(), "qa": [], "labs": []}
    new = _flag_emergencies(data, emergency.detect(f"{body.complaint}. {body.other_symptoms}"))
    data["plan"] = triage.next_questions(profile, data)
    c = Case(user_id=user.id, status=_status_from_plan(data["plan"]), data_enc=enc(data))
    db.add(c)
    db.commit()
    audit(db, user.id, "case_create", f"case:{c.id}", request)
    out = _out(db, c)
    out["new_emergency"] = emergency.payload(new)
    return out


@router.get("")
def list_cases(user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = []
    for c in db.query(Case).filter_by(user_id=user.id).order_by(Case.id.desc()).all():
        data, result = dec(c.data_enc), dec(c.result_enc)
        out.append({"id": c.id, "status": c.status, "created_at": c.created_at.isoformat(), "complaint": data["complaint"][:90],
                    "risk": result["risk"]["level"] if result else None,
                    "top_condition": result["analysis"]["conditions"][0]["name"] if result else None})
    return out


@router.get("/{case_id}")
def get_case(case_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _case(db, user, case_id)
    audit(db, user.id, "case_view", f"case:{c.id}", request)
    return _out(db, c)


@router.post("/{case_id}/answers")
def answer(case_id: int, body: AnswersIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c, profile = _case(db, user, case_id), _profile(db, user)
    data = dec(c.data_enc)
    data["qa"] += [a.model_dump() for a in body.answers]
    text = " . ".join(a.answer + (f" {a.question}" if AFFIRMATIVE.match(a.answer) else "") for a in body.answers)
    new = _flag_emergencies(data, emergency.detect(text))
    data["plan"] = triage.next_questions(profile, data)
    c.data_enc, c.status = enc(data), _status_from_plan(data["plan"])
    db.commit()
    audit(db, user.id, "case_answer", f"case:{c.id}", request)
    out = _out(db, c)
    out["new_emergency"] = emergency.payload(new)
    return out


@router.post("/{case_id}/reports")
async def upload_report(case_id: int, request: Request, file: UploadFile = File(...),
                        user: User = Depends(current_user), db: Session = Depends(get_db)):
    c, profile = _case(db, user, case_id), _profile(db, user)
    raw = await file.read(labs.MAX_BYTES + 1)
    if len(raw) > labs.MAX_BYTES:
        raise HTTPException(413, "File is larger than 10 MB")
    mime = next((m for sig, m in MAGIC.items() if raw.startswith(sig)), None)
    if mime not in labs.ALLOWED_TYPES:
        raise HTTPException(415, "Upload a PDF, PNG, JPG or WEBP file")
    stored = f"{uuid.uuid4().hex}.bin"
    (UPLOAD_DIR / stored).write_bytes(encrypt_bytes(raw))  # encrypted at rest

    from starlette.concurrency import run_in_threadpool
    result = await run_in_threadpool(labs.analyze_report, raw, mime, profile["sex"])
    db.add(ReportFile(case_id=c.id, filename=(file.filename or "report")[:255], mime=mime, stored_name=stored,
                      text_enc=enc(result["text"][:50000]), labs_enc=enc({"method": result["method"], "labs": result["labs"]})))
    data = dec(c.data_enc)
    merged = {l["test_id"] or l["name"]: l for l in data.get("labs", [])}
    merged.update({l["test_id"] or l["name"]: l for l in result["labs"]})
    data["labs"] = list(merged.values())
    new = _flag_emergencies(data, emergency.from_labs(result["labs"]))
    if c.status == "report":
        c.status = "ready"
    c.data_enc = enc(data)
    db.commit()
    audit(db, user.id, "report_upload", f"case:{c.id}", request)
    out = _out(db, c)
    out["upload"] = {"method": result["method"], "found": len(result["labs"]), "chars": len(result["text"])}
    out["new_emergency"] = emergency.payload(new)
    return out


@router.post("/{case_id}/analyze")
def analyze(case_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c, profile = _case(db, user, case_id), _profile(db, user)
    data = dec(c.data_enc)
    old = dec(c.result_enc)
    result = agents.run_analysis(profile, data, data.get("labs", []))
    if old and old.get("prices"):
        result["prices"] = old["prices"]
    c.result_enc, c.status = enc(result), "analyzed"
    db.commit()
    audit(db, user.id, "case_analyze", f"case:{c.id}", request)
    return _out(db, c)


class PriceIn(BaseModel):
    medicine: str = Field(min_length=2, max_length=80)
    refresh: bool = False


@router.post("/{case_id}/prices")
def prices(case_id: int, body: PriceIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _case(db, user, case_id)
    data = pricing.compare(db, body.medicine, body.refresh)
    result = dec(c.result_enc)
    if result:
        result.setdefault("prices", {})[body.medicine] = data
        c.result_enc = enc(result)
        db.commit()
    audit(db, user.id, "price_compare", body.medicine, request)
    return data


@router.get("/{case_id}/report.pdf")
def report_pdf(case_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _case(db, user, case_id)
    result = dec(c.result_enc)
    if not result:
        raise HTTPException(400, "Run the analysis first")
    audit(db, user.id, "report_export", f"case:{c.id}", request)
    return Response(build_pdf(result, c.id), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="health-report-{c.id}.pdf"'})


def delete_case_files(db: Session, user_id: int, case_id: int | None = None):
    q = db.query(Case).filter_by(user_id=user_id)
    if case_id:
        q = q.filter_by(id=case_id)
    for c in q.all():
        for r in db.query(ReportFile).filter_by(case_id=c.id).all():
            (UPLOAD_DIR / r.stored_name).unlink(missing_ok=True)
            db.delete(r)
        db.delete(c)
    db.commit()


@router.delete("/{case_id}")
def delete_case(case_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _case(db, user, case_id)
    delete_case_files(db, user.id, case_id)
    audit(db, user.id, "case_delete", f"case:{case_id}", request)
    return {"ok": True}
