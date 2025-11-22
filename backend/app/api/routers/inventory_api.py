from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models, inventory as inventory_svc, security
from app.database import get_db

router = APIRouter(prefix="/api/inventory", tags=["Inventory"])


class InventoryAdjust(BaseModel):
    item_sku: str
    qty_delta: float
    unit: str = "pcs"
    reason: str = "adjust"


@router.get("/levels")
def get_inventory_levels(
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(security.require_admin_api),
):
    rows = (
        db.query(models.StockLevel, models.InventoryItem)
        .join(models.InventoryItem, models.InventoryItem.id == models.StockLevel.item_id)
        .all()
    )
    return [
        {
            "sku": item.sku,
            "name": item.name,
            "qty_on_hand": float(level.qty_on_hand_cached or 0),
            "unit": item.unit,
        }
        for level, item in rows
    ]


@router.post("/adjust")
def adjust_inventory(
    payload: InventoryAdjust,
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(security.require_admin_api),
):
    item = db.query(models.InventoryItem).filter(models.InventoryItem.sku == payload.item_sku).first()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    inventory_svc._record_movement(
        db,
        item_id=item.id,
        qty_delta=payload.qty_delta,
        unit=payload.unit,
        reason=payload.reason,
        ref_type="adjust",
        ref_id=None,
        created_by="api",
    )
    db.commit()
    return {"ok": True}
