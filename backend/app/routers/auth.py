import os
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.security import hash_password, verify_password, create_user_session, clear_user_session, get_user_from_request
from app.email_utils import send_email

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")

router = APIRouter()


class GoogleLoginPayload(BaseModel):
    credential: str
    table_id: str | None = None


@router.post("/google", response_model=schemas.UserRead)
def google_sign_in(payload: GoogleLoginPayload, response: Response, request: Request, db: Session = Depends(get_db)):
    """Verify Google ID token, upsert user by email, optionally link table.

    Returns a UserRead, following the current pattern where the frontend keeps
    track of user_id client-side.
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google client not configured",
        )

    # Lazy import to avoid hard dependency if the route is unused
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
    except Exception as exc:  # pragma: no cover - import-time safety
        raise HTTPException(status_code=500, detail="Google auth not available") from exc

    try:
        idinfo = google_id_token.verify_oauth2_token(
            payload.credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
        issuer = idinfo.get("iss")
        if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
            raise ValueError("Invalid issuer")
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid Google credential") from exc

    email = idinfo.get("email")
    email_verified = bool(idinfo.get("email_verified"))
    name = idinfo.get("name") or (email or "Utente Google")

    user = None
    if email:
        user = db.query(models.User).filter(models.User.email == email).first()

    # Ensure a Table exists if table_id provided and link user to it
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
        # Update name if missing; update table link if supplied
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

    # Set session cookie
    create_user_session(response, db, user, request)
    return user


class RegisterPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    name: str | None = None
    surname: str | None = None
    table_id: str | None = None


@router.post("/register", response_model=schemas.UserRead)
def register_user(payload: RegisterPayload, response: Response, request: Request, db: Session = Depends(get_db)):
    existing = None
    # Best-effort uniqueness on email at app level
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
        # fallback to email local-part if no name given
        full_name = payload.email.split("@")[0]

    # Ensure table link if provided
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
        # Convert an email-only guest into a registered user
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


@router.post("/login", response_model=schemas.UserRead)
def login_user(payload: LoginPayload, response: Response, request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenziali non valide")

    # Optionally update table association
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


@router.get("/session", response_model=schemas.UserRead | None)
def get_session_user(user: models.User | None = Depends(get_user_from_request)):
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
        # Don't leak existence
        return {"ok": True}
    # Create token
    from secrets import token_urlsafe
    from hashlib import sha256
    raw = token_urlsafe(32)
    token_hash = sha256(raw.encode("utf-8")).hexdigest()
    ttl = int(os.environ.get("PASSWORD_RESET_TTL", str(3600)))
    expires = datetime.utcnow() + timedelta(seconds=ttl)
    db.add(models.EmailToken(user_id=user.id, purpose="reset", token_hash=token_hash, expires_at=expires))
    db.commit()

    base_url = os.environ.get("APP_BASE_URL", request.url.scheme + "://" + request.url.netloc)
    link = f"{base_url}/api/auth/password/reset/confirm?token={raw}"
    subject = "Reset password"
    body = f"Per reimpostare la password, clicca: {link}\nSe non hai richiesto tu, ignora questa email."
    sent = send_email(user.email, subject, body)
    debug = os.environ.get("APP_ENV", "dev") != "prod"
    return {"ok": True, **({"debug_token": raw} if debug and not sent else {})}


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
        # Don't leak
        return {"ok": True}
    # Create token
    from secrets import token_urlsafe
    from hashlib import sha256
    raw = token_urlsafe(32)
    token_hash = sha256(raw.encode("utf-8")).hexdigest()
    ttl = int(os.environ.get("EMAIL_VERIFY_TTL", str(24 * 3600)))
    expires = datetime.utcnow() + timedelta(seconds=ttl)
    db.add(models.EmailToken(user_id=user.id, purpose="verify", token_hash=token_hash, expires_at=expires))
    db.commit()

    base_url = os.environ.get("APP_BASE_URL", request.url.scheme + "://" + request.url.netloc)
    link = f"{base_url}/api/auth/email/verify/confirm?token={raw}"
    subject = "Verifica email"
    body = f"Conferma il tuo indirizzo email cliccando: {link}"
    sent = send_email(user.email, subject, body)
    debug = os.environ.get("APP_ENV", "dev") != "prod"
    return {"ok": True, **({"debug_token": raw} if debug and not sent else {})}


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
    return {"google_client_id": GOOGLE_CLIENT_ID or ""}
