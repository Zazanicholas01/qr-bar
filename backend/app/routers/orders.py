from fastapi import APIRouter
from pydantic import BaseModel, Field, PositiveInt

router = APIRouter()


class OrderItem(BaseModel):
    product_id: PositiveInt
    quantity: PositiveInt = Field(default=1, description="Number of units requested")


class OrderPayload(BaseModel):
    table_id: str | None = Field(default=None, description="Table submitting the order")
    items: list[OrderItem]


# Extremely naive in-memory store just for demonstration
orders: list[dict] = []


@router.post("/", status_code=201)
async def create_order(payload: OrderPayload):
    new_order = {
        "id": len(orders) + 1,
        "table_id": payload.table_id,
        "items": [item.model_dump() for item in payload.items],
    }
    orders.append(new_order)
    return {"message": "Order received", "order": new_order}


@router.get("/")
async def get_orders():
    return {"orders": orders}
