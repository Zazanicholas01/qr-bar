from fastapi import APIRouter, Query

router = APIRouter()

@router.get("")
async def get_menu(table_id: str | None = Query(default=None)):
    """Returns the menu items available for a given table."""
    sample_menu = [
        {"id": 1, "name": "Espresso", "price": 1.2},
        {"id": 2, "name": "Cappuccino", "price": 1.5},
        {"id": 3, "name": "Cornetto", "price": 1.0},
    ]

    return {
        "table_id": table_id or "general",
        "items": sample_menu,
    }
