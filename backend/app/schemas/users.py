from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .tables import TableRead


class UserRead(BaseModel):
    id: int
    name: str | None = None
    email: str | None = None
    email_verified_at: datetime | None = None
    phone: str | None = None
    age: int | None = None
    created_at: datetime
    table_code: str | None = None
    table: TableRead | None = None

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    age: int | None = Field(default=None, ge=0, le=120)
