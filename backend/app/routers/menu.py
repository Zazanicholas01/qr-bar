from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import models
from app.database import get_db


CATEGORIES = [
    {
        "name": "Coffee",
        "items": [
            {"id": 1, "name": "Espresso", "price": 1.2},
            {"id": 2, "name": "Espresso Macchiato", "price": 1.3},
            {"id": 3, "name": "Cappuccino", "price": 1.5},
            {"id": 4, "name": "Latte Macchiato", "price": 1.7},
            {"id": 5, "name": "Caffè Americano", "price": 1.4},
        ],
    },
    {
        "name": "Drinks",
        "items": [
            {"id": 20, "name": "Succo d'arancia", "price": 2.5},
            {"id": 21, "name": "Acqua naturale", "price": 1.0},
            {"id": 22, "name": "Acqua frizzante", "price": 1.0},
            {"id": 23, "name": "Tè freddo", "price": 2.2},
        ],
    },
    {
        "name": "Beer & Wine",
        "items": [
            {"id": 40, "name": "Birra artigianale", "price": 4.5},
            {"id": 41, "name": "Vino bianco", "price": 5.0},
            {"id": 42, "name": "Vino rosso", "price": 5.0},
        ],
    },
    {
        "name": "Aperitivi",
        "items": [
            {"id": 60, "name": "Spritz", "price": 4.0},
            {"id": 61, "name": "Negroni", "price": 5.5},
        ],
    },
    {
        "name": "Cocktails",
        "items": [
            {"id": 80, "name": "Mojito", "price": 6.0},
            {"id": 81, "name": "Espresso Martini", "price": 7.0},
        ],
    },
]


router = APIRouter()


@router.get("")
async def get_menu(
    table_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Returns the menu items available for a given table."""

    table_code = table_id or "general"

    table = None
    if table_id:
        table = (
            db.query(models.Table)
            .filter(models.Table.code == table_id)
            .first()
        )
        if table is None:
            table = models.Table(code=table_id)
            db.add(table)
            db.commit()
    return {
        "table_id": table_code,
        "table_name": table.name if table else None,
        "categories": CATEGORIES,
    }
