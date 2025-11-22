from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.security import hash_password, verify_password, create_user_session, clear_user_session
from app.email_utils import send_email
from app.schemas.users import UserRead
from app.api import deps
from app.core import config

GOOGLE_CLIENT_ID = config.GOOGLE_CLIENT_ID
GOOGLE_AUDIENCES = config.GOOGLE_AUDIENCES
APP_ENV = config.APP_ENV

router = APIRouter()


class GoogleLoginPayload(BaseModel):
    credential: str
    table_id: str | None = None


@router.post("/google", response_model=UserRead)
def google_sign_in(payload: GoogleLoginPayload, response: Response, request: Request, db: Session = Depends(get_db)):
    """Verify Google ID token, upsert user by email, optionally link table."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google client not configured",
        )
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
    except Exception as exc:  # pragma: no cover - import-time safety
        raise HTTPException(status_code=500, detail="Google auth not available") from exc

    try:
        idinfo = google_id_token.verify_oauth2_token(
            payload.credential,
            google_requests.Request(),
        )
        issuer = idinfo.get("iss")
        if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
            raise ValueError("Invalid issuer")
        aud = idinfo.get("aud")
        if GOOGLE_AUDIENCES and aud not in GOOGLE_AUDIENCES:
            raise ValueError("Invalid audience")
    except Exception as exc:
        detail = "Invalid Google credential"
        if APP_ENV != "prod":
            detail = f"Invalid Google credential: {exc}"
        raise HTTPException(status_code=401, detail=detail)

    email = idinfo.get("email")
    email_verified = bool(idinfo.get("email_verified"))
    name = idinfo.get("name") or (email or "Utente Google")

    user = db.query(models.User).filter(models.User.email == email).first() if email else None

    table = None
    if payload.table_id:
        table = db.query(models.Table).filter(models.Table.code == payload.table_id).first()
        if table is None:
            table = models.Table(code=payload.table_id)
            db.add(table)
            db.flush()

    if user is None:
        user = models.User(name=name, email=email)
        if email_verified:
            user.email_verified_at = datetime.utcnow()
        if table is not None:
            user.table = table
            user.table_code = table.code
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        changed = False
        if not user.name and name:
            user.name = name
            changed = True
        if table is not None and (user.table is None or user.table.id != table.id):
            user.table = table
            user.table_code = table.code
            changed = True
        if email_verified and not user.email_verified_at:
            user.email_verified_at = datetime.utcnow()
            changed = True
        if changed:
            db.commit()
            db.refresh(user)

    create_user_session(response, db, user, request)
    return user


class RegisterPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    name: str | None = None
    surname: str | None = None
    table_id: str | None = None


@router.post("/register", response_model=UserRead)
def register_user(payload: RegisterPayload, response: Response, request: Request, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing and existing.password_hash:
        raise HTTPException(status_code=400, detail="Email già registrata")

    full_name = None
    if payload.name and payload.surname:
        full_name = f"{payload.name.strip()} {payload.surname.strip()}".strip()
    elif payload.name:
        full_name = payload.name.strip()
    elif payload.surname:
        full_name = payload.surname.strip()
    else:
        full_name = payload.email.split("@")[0]

    table = None
    if payload.table_id:
        table = db.query(models.Table).filter(models.Table.code == payload.table_id).first()
        if table is None:
            table = models.Table(code=payload.table_id)
            db.add(table)
            db.flush()

    if existing is None:
        user = models.User(
            name=full_name or "Utente",
            email=payload.email,
            password_hash=hash_password(payload.password),
        )
        if table is not None:
            user.table = table
            user.table_code = table.code
        db.add(user)
        db.commit()
        db.refresh(user)
        create_user_session(response, db, user, request)
        return user
    else:
        existing.name = existing.name or full_name or existing.email.split("@")[0]
        existing.password_hash = hash_password(payload.password)
        if table is not None:
            existing.table = table
            existing.table_code = table.code
        db.commit()
        db.refresh(existing)
        create_user_session(response, db, existing, request)
        return existing


class LoginPayload(BaseModel):
    email: EmailStr
    password: str
    table_id: str | None = None


@router.post("/login", response_model=UserRead)
def login_user(payload: LoginPayload, response: Response, request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenziali non valide")

    if payload.table_id:
        table = db.query(models.Table).filter(models.Table.code == payload.table_id).first()
        if table is None:
            table = models.Table(code=payload.table_id)
            db.add(table)
            db.flush()
        if user.table is None or user.table.id != table.id:
            user.table = table
            user.table_code = table.code
            db.commit()
            db.refresh(user)
    create_user_session(response, db, user, request)
    return user


@router.get("/session", response_model=UserRead | None)
def get_session_user(user: models.User | None = Depends(deps.current_user_optional)):
    return user


@router.post("/logout")
def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    clear_user_session(response, request, db)
    return {"ok": True}


class EmailActionStart(BaseModel):
    email: EmailStr


class ResetConfirmPayload(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=256)


@router.post("/password/reset/start")
def password_reset_start(payload: EmailActionStart, request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user:
        return {"ok": True}
    from secrets import token_urlsafe
    from hashlib import sha256
    raw = token_urlsafe(32)
    token_hash = sha256(raw.encode("utf-8")).hexdigest()
    ttl = config.PASSWORD_RESET_TTL
    expires = datetime.utcnow() + timedelta(seconds=ttl)
    db.add(models.EmailToken(user_id=user.id, purpose="reset", token_hash=token_hash, expires_at=expires))
    db.commit()

    base_url = config.APP_BASE_URL or (request.url.scheme + "://" + request.url.netloc)
    link = f"{base_url}/api/auth/password/reset/confirm?token={raw}"
    subject = "Reset password"
    body = f"Per reimpostare la password, clicca: {link}\nSe non hai richiesto tu, ignora questa email."
    sent = send_email(user.email, subject, body)
    if not sent or config.EMAIL_DEBUG_LINKS:
        return {"ok": True, "link": link, "debug_token": raw}
    return {"ok": True}


@router.post("/password/reset/confirm")
def password_reset_confirm(payload: ResetConfirmPayload, db: Session = Depends(get_db)):
    from hashlib import sha256
    token_hash = sha256(payload.token.encode("utf-8")).hexdigest()
    et = (
        db.query(models.EmailToken)
        .filter(models.EmailToken.purpose == "reset", models.EmailToken.token_hash == token_hash)
        .first()
    )
    if not et or et.consumed_at is not None or et.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="Token non valido o scaduto")
    user = db.query(models.User).filter(models.User.id == et.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Utente non trovato")
    user.password_hash = hash_password(payload.password)
    et.consumed_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/email/verify/start")
def email_verify_start(payload: EmailActionStart, request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user:
        return {"ok": True}
    from secrets import token_urlsafe
    from hashlib import sha256
    raw = token_urlsafe(32)
    token_hash = sha256(raw.encode("utf-8")).hexdigest()
    ttl = config.EMAIL_VERIFY_TTL
    expires = datetime.utcnow() + timedelta(seconds=ttl)
    db.add(models.EmailToken(user_id=user.id, purpose="verify", token_hash=token_hash, expires_at=expires))
    db.commit()

    base_url = config.APP_BASE_URL or (request.url.scheme + "://" + request.url.netloc)
    link = f"{base_url}/api/auth/email/verify/confirm?token={raw}"
    subject = "Verifica email"
    body = f"Conferma il tuo indirizzo email cliccando: {link}"
    sent = send_email(user.email, subject, body)
    if not sent or config.EMAIL_DEBUG_LINKS:
        return {"ok": True, "link": link, "debug_token": raw}
    return {"ok": True}


@router.get("/email/verify/confirm")
def email_verify_confirm(token: str, db: Session = Depends(get_db)):
    from hashlib import sha256
    token_hash = sha256(token.encode("utf-8")).hexdigest()
    et = (
        db.query(models.EmailToken)
        .filter(models.EmailToken.purpose == "verify", models.EmailToken.token_hash == token_hash)
        .first()
    )
    if not et or et.consumed_at is not None or et.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="Token non valido o scaduto")
    user = db.query(models.User).filter(models.User.id == et.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Utente non trovato")
    et.consumed_at = datetime.utcnow()
    if not user.email_verified_at:
        user.email_verified_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.get("/config")
def auth_config():
    return {
        "google_client_id": GOOGLE_CLIENT_ID or "",
    }
