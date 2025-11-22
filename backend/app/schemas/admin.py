from pydantic import BaseModel


class SupplyOrderAck(BaseModel):
    status: str
    order: dict
