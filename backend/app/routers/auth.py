from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditLog, Profile, User
from ..schemas import LoginIn, ProfileIn, RegisterIn
from ..security import (LOCK_MINUTES, MAX_FAILED_LOGINS, audit, check_password, create_token, current_user, dec, enc,
                        hash_password)

router = APIRouter(prefix="/api", tags=["auth"])


def _token_out(user: User, db: Session) -> dict:
    return {"token": create_token(user.id), "email": user.email, "has_profile": db.get(Profile, user.id) is not None}


@router.post("/auth/register")
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    audit(db, user.id, "register", request=request)
    return _token_out(user, db)


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=body.email.strip().lower()).first()
    now = datetime.now(timezone.utc)
    if user and user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now:
        raise HTTPException(429, f"Too many failed attempts. Try again after {LOCK_MINUTES} minutes.")
    if not user or not check_password(body.password, user.password_hash):
        if user:
            user.failed_logins += 1
            if user.failed_logins >= MAX_FAILED_LOGINS:
                user.locked_until, user.failed_logins = now + timedelta(minutes=LOCK_MINUTES), 0
            db.commit()
        audit(db, user.id if user else None, "login_failed", body.email[:120], request)
        raise HTTPException(401, "Wrong email or password")
    user.failed_logins, user.locked_until = 0, None
    db.commit()
    audit(db, user.id, "login", request=request)
    return _token_out(user, db)


@router.get("/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"email": user.email, "has_profile": db.get(Profile, user.id) is not None}


@router.get("/profile")
def get_profile(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(Profile, user.id)
    if not p:
        return None
    audit(db, user.id, "profile_view", request=request)
    return dec(p.data_enc)


@router.put("/profile")
def put_profile(body: ProfileIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(Profile, user.id)
    if p:
        p.data_enc = enc(body.model_dump())
    else:
        db.add(Profile(user_id=user.id, data_enc=enc(body.model_dump())))
    db.commit()
    audit(db, user.id, "profile_update", request=request)
    return body.model_dump()


@router.get("/audit")
def my_audit(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(AuditLog).filter_by(user_id=user.id).order_by(AuditLog.id.desc()).limit(100).all()
    return [{"action": r.action, "target": r.target, "ip": r.ip, "at": r.at.isoformat()} for r in rows]


@router.delete("/account")
def delete_account(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .cases import delete_case_files
    delete_case_files(db, user.id)
    audit(db, user.id, "account_deleted", "", request)
    if p := db.get(Profile, user.id):
        db.delete(p)
    db.delete(user)
    db.commit()
    return {"ok": True}
