from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.security import create_user_session

router = APIRouter()


@router.post("/auto", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED)
async def auto_login(table_id: str | None = None, response: Response = None, request: Request = None, db: Session = Depends(get_db)):
    """Create a lightweight user row when a guest scans the QR code."""
    try:
        guest_label = table_id or "guest"
        user = models.User(name=f"Guest {guest_label} {datetime.utcnow().strftime('%H%M%S')}")

        if table_id:
            table = (
                db.query(models.Table)
                .filter(models.Table.code == table_id)
                .first()
            )
            if table is None:
                table = models.Table(code=table_id)
                db.add(table)
                db.flush()
            user.table = table
            user.table_code = table.code

        db.add(user)
        db.commit()
        db.refresh(user)
    except Exception as exc:  # pragma: no cover - defensive
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to create user") from exc

    # Set a customer session cookie as well (opaque, DB-backed)
    if response is not None:
        try:
            create_user_session(response, db, user, request)
        except Exception:
            # don't fail guest creation if cookie cannot be set
            pass
    return user


@router.get("/", response_model=list[schemas.UserRead])
async def list_users(db: Session = Depends(get_db)):
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    return users


@router.put("/{user_id}", response_model=schemas.UserRead)
async def update_user(
    user_id: int,
    payload: schemas.UserUpdate,
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user
