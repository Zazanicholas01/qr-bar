import os
from datetime import datetime
from typing import Optional

import secrets
import hashlib
from datetime import timedelta
from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app import models

_pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
_SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY", "change-me")
_SESSION_TTL = int(os.environ.get("ADMIN_SESSION_TTL", "86400"))
_COOKIE_NAME = os.environ.get("ADMIN_SESSION_COOKIE", "admin_session")
_COOKIE_SECURE = os.environ.get("ADMIN_COOKIE_SECURE", "true").lower() != "false"

_serializer = URLSafeTimedSerializer(_SECRET_KEY, salt="admin-session")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def _make_token(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id, "ts": datetime.utcnow().isoformat()})


def _decode_token(token: str) -> Optional[int]:
    try:
        data = _serializer.loads(token, max_age=_SESSION_TTL)
        return data.get("uid")
    except (BadSignature, SignatureExpired):
        return None


def set_admin_session(response: Response, user: models.StaffUser) -> None:
    token = _make_token(user.id)
    response.set_cookie(
        _COOKIE_NAME,
        token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        max_age=_SESSION_TTL,
    )


def clear_admin_session(response: Response) -> None:
    response.delete_cookie(_COOKIE_NAME)


def get_admin_from_request(
    request: Request, db: Session = Depends(get_db)
) -> Optional[models.StaffUser]:
    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        return None
    user_id = _decode_token(token)
    if not user_id:
        return None
    admin = db.query(models.StaffUser).filter(models.StaffUser.id == user_id).first()
    return admin


def require_admin_api(
    request: Request, db: Session = Depends(get_db)
) -> models.StaffUser:
    admin = get_admin_from_request(request, db)
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return admin

# =====================
# Customer session utils (DB-backed)
# =====================

_USER_COOKIE = os.environ.get("USER_SESSION_COOKIE", "user_session")
_USER_COOKIE_SECURE = os.environ.get("USER_COOKIE_SECURE", "true").lower() != "false"
_USER_SESSION_TTL = int(os.environ.get("USER_SESSION_TTL", str(7 * 24 * 3600)))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.utcnow()


def create_user_session(response: Response, db: Session, user: models.User, request: Request | None = None) -> None:
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    expires = _now() + timedelta(seconds=_USER_SESSION_TTL)
    ua = request.headers.get("user-agent") if request else None
    ip = request.client.host if (request and request.client) else None
    sess = models.AuthSession(user_id=user.id, token_hash=token_hash, expires_at=expires, user_agent=ua, ip=ip)
    db.add(sess)
    db.commit()
    response.set_cookie(
        _USER_COOKIE,
        raw,
        httponly=True,
        secure=_USER_COOKIE_SECURE,
        samesite="lax",
        max_age=_USER_SESSION_TTL,
        path="/",
    )


def clear_user_session(response: Response, request: Request | None = None, db: Session | None = None) -> None:
    token = request.cookies.get(_USER_COOKIE) if request else None
    if token and db is not None:
        token_hash = _hash_token(token)
        sess = db.query(models.AuthSession).filter(models.AuthSession.token_hash == token_hash).first()
        if sess:
            sess.revoked_at = _now()
            db.commit()
    response.delete_cookie(_USER_COOKIE, path="/")


def get_user_from_request(request: Request, db: Session = Depends(get_db)) -> models.User | None:
    token = request.cookies.get(_USER_COOKIE)
    if not token:
        return None
    token_hash = _hash_token(token)
    sess = (
        db.query(models.AuthSession)
        .filter(models.AuthSession.token_hash == token_hash)
        .first()
    )
    if not sess or sess.revoked_at is not None or sess.expires_at <= _now():
        return None
    user = db.query(models.User).filter(models.User.id == sess.user_id).first()
    return user
