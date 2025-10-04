from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, PositiveInt, ConfigDict

DECIMAL_ENCODERS = {Decimal: float}


class TableCreate(BaseModel):
    code: str
    name: str | None = None


class TableRead(BaseModel):
    id: int
    code: str
    name: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserRead(BaseModel):
    id: int
    name: str | None = None
    email: str | None = None
    created_at: datetime
    table_code: str | None = None
    table: TableRead | None = None

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True, json_encoders=DECIMAL_ENCODERS)


class TransactionRead(BaseModel):
    id: int
    amount: Decimal
    method: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, json_encoders=DECIMAL_ENCODERS)


class OrderRead(BaseModel):
    id: int
    table_code: str | None = Field(default=None, alias="table_id")
    status: str
    total_quantity: int
    total_amount: Decimal
    created_at: datetime
    user_id: int | None
    table: TableRead | None = None
    items: list[OrderItemRead]
    transaction: TransactionRead | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders=DECIMAL_ENCODERS,
        populate_by_name=True,
    )


class OrderStatusUpdate(BaseModel):
    status: str = Field(pattern="^(pending|processed|closed)$")
