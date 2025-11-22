from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.schemas.tables import TableCreate, TableRead

router = APIRouter()


@router.get("/", response_model=list[TableRead])
async def list_tables(db: Session = Depends(get_db)):
    tables = db.query(models.Table).order_by(models.Table.code.asc()).all()
    return tables


@router.post("/", response_model=TableRead, status_code=status.HTTP_201_CREATED)
async def create_table(payload: TableCreate, db: Session = Depends(get_db)):
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
