from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, PositiveInt


class UserRead(BaseModel):
    id: int
    name: str | None = None
    email: str | None = None
    created_at: datetime

    class Config:
        orm_mode = True


class OrderItemCreate(BaseModel):
    product_id: PositiveInt
    name: str
    unit_price: float = Field(ge=0)
    quantity: PositiveInt = Field(default=1)


class OrderCreate(BaseModel):
    table_id: str | None = None
    user_id: int | None = None
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
    user_id: int | None
    items: list[OrderItemRead]

    class Config:
        orm_mode = True
        json_encoders = {Decimal: float}


class OrderStatusUpdate(BaseModel):
    status: str = Field(pattern="^(pending|processed|closed)$")
