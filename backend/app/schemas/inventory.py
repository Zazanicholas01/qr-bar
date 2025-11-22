from pydantic import BaseModel


class InventoryAdjust(BaseModel):
    item_sku: str
    qty_delta: float
    unit: str = "pcs"
    reason: str = "adjust"


class InventoryLevel(BaseModel):
    sku: str
    name: str
    qty_on_hand: float
    unit: str


class InventoryAdjustResponse(BaseModel):
    ok: bool = True
