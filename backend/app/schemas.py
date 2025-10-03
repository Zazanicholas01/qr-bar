from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, PositiveInt


class OrderItemCreate(BaseModel):
    product_id: PositiveInt
    name: str
    unit_price: float = Field(ge=0)
    quantity: PositiveInt = Field(default=1)


class OrderCreate(BaseModel):
    table_id: str | None = None
    items: list[OrderItemCreate]


class OrderItemRead(BaseModel):
    id: int
    product_id: int
    name: str
    unit_price: Decimal
    quantity: int

    class Config:
        orm_mode = True
        json_encoders = {Decimal: float}


class OrderRead(BaseModel):
    id: int
    table_id: str | None
    status: str
    total_quantity: int
    total_amount: Decimal
    created_at: datetime
    items: list[OrderItemRead]

    class Config:
        orm_mode = True
        json_encoders = {Decimal: float}
