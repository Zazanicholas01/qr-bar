"""Common FastAPI dependencies."""
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, security


def get_db_session(db: Session = Depends(get_db)) -> Session:
    return db


def require_admin(request: Request, db: Session = Depends(get_db)) -> models.StaffUser:
    admin = security.get_admin_from_request(request, db)
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return admin


def require_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    user = security.get_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> models.User | None:
    """Return the current user or None without raising."""
    return security.get_user_from_request(request, db)
