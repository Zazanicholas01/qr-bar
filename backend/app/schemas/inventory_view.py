from pydantic import BaseModel
from typing import Any


class InventoryItemView(BaseModel):
    sku: str
    name: str
    unit: str
    qty: float


class SupplyOrderView(BaseModel):
    id: int
    product: str
    state: str
    qty_text: str
    supplier_name: str
    supplier_quote: str
    total_price: str
    alert_time: str
    ack_text: str | None = None
    sla_hours: float
    elapsed_hours: float
    progress_pct: float
    slider_value: float
    actionable: bool
    restocked: bool
    restock_text: str | None = None
    sla_label: str
    expires_text: str | None = None
    expires_indicator: str | None = None


class SupplierDirectoryEntry(BaseModel):
    name: str
    lead: int | None = None
    notes: str | None = None
    products: list[str]


class InventoryOverview(BaseModel):
    items: list[InventoryItemView]
    supply_orders: list[SupplyOrderView]
    supplier_directory: list[SupplierDirectoryEntry]
