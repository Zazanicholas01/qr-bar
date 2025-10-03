from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter()


@router.post("/auto", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED)
async def auto_login(table_id: str | None = None, db: Session = Depends(get_db)):
    """Create a lightweight user row when a guest scans the QR code."""
    try:
        guest_label = table_id or "guest"
        user = models.User(name=f"Guest {guest_label} {datetime.utcnow().strftime('%H%M%S')}")
        db.add(user)
        db.commit()
        db.refresh(user)
    except Exception as exc:  # pragma: no cover - defensive
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to create user") from exc

    return user


@router.get("/", response_model=list[schemas.UserRead])
async def list_users(db: Session = Depends(get_db)):
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    return users
