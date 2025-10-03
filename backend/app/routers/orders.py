from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class Order(BaseModel):
    product_id: int
    quantity: int

# Esempio: lista di ordini in memoria
orders = []

@router.post("/")
async def create_order(order: Order):
    new_order = {"product_id": order.product_id, "quantity": order.quantity}
    orders.append(new_order)
    return {"message": "Order created", "order": new_order}

@router.get("/")
async def get_orders():
    return {"orders": orders}
