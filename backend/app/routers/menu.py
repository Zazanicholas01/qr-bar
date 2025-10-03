from fastapi import APIRouter

router = APIRouter()

# Esempio: lista di prodotti del menu
@router.get("/")
async def get_menu():
    return {
        "menu": [
            {"id": 1, "name": "Espresso", "price": 1.2},
            {"id": 2, "name": "Cappuccino", "price": 1.5},
            {"id": 3, "name": "Cornetto", "price": 1.0},
        ]
    }
