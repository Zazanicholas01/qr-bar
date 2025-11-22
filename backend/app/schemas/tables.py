from datetime import datetime
from pydantic import BaseModel, ConfigDict


class TableCreate(BaseModel):
    code: str
    name: str | None = None


class TableRead(BaseModel):
    id: int
    code: str
    name: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
