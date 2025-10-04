from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter()


@router.get("/", response_model=list[schemas.TableRead])
async def list_tables(db: Session = Depends(get_db)):
    tables = db.query(models.Table).order_by(models.Table.code.asc()).all()
    return tables


@router.post("/", response_model=schemas.TableRead, status_code=status.HTTP_201_CREATED)
async def create_table(payload: schemas.TableCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(models.Table)
        .filter(models.Table.code == payload.code)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Table code already exists")

    table = models.Table(code=payload.code, name=payload.name)
    db.add(table)
    db.commit()
    db.refresh(table)
    return table
