from pydantic import BaseModel
from typing import Any


class DashboardPayment(BaseModel):
    method: str
    count: int


class DashboardItem(BaseModel):
    name: str
    total: float


class HeatmapBucket(BaseModel):
    order_count: int
    total_amount: float


class DashboardHeatmaps(BaseModel):
    hourly: dict[str, Any]
    day_of_week: dict[str, Any]


class DashboardSummary(BaseModel):
    total_amount: float
    closed_count: int
    items: list[DashboardItem]
    payments: list[DashboardPayment]
    heatmaps: DashboardHeatmaps
    generated_at: str
