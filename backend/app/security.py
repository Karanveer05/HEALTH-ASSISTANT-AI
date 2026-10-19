"""Passwords (bcrypt), login tokens (JWT), field encryption (Fernet) and the audit log."""
import json
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import AuditLog, User

_settings = get_settings()
_fernet = Fernet(_settings.fernet_key.encode())
_bearer = HTTPBearer(auto_error=False)

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet.encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    return _fernet.decrypt(data)


def enc(obj) -> str:
    return _fernet.encrypt(json.dumps(obj).encode()).decode()


def dec(token: str | None, default=None):
    if not token:
        return default
    return json.loads(_fernet.decrypt(token.encode()))


def create_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=_settings.token_minutes)
    return jwt.encode({"sub": str(user_id), "exp": exp}, _settings.secret_key, algorithm="HS256")


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> User:
    if creds is None:
        raise HTTPException(401, "Not logged in")
    try:
        payload = jwt.decode(creds.credentials, _settings.secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid session")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(401, "Account not found")
    return user


def audit(db: Session, user_id: int | None, action: str, target: str = "", request: Request | None = None):
    ip = request.client.host if request and request.client else ""
    db.add(AuditLog(user_id=user_id, action=action, target=target, ip=ip))
    db.commit()
