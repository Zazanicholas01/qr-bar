from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, inventory as inventory_svc
from app.database import get_db
from app.api import deps
from app.schemas.inventory import InventoryAdjust, InventoryLevel, InventoryAdjustResponse

router = APIRouter(prefix="/api/inventory", tags=["Inventory"])


@router.get("/levels", response_model=list[InventoryLevel])
def get_inventory_levels(
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(deps.require_admin),
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


@router.post("/adjust", response_model=InventoryAdjustResponse)
def adjust_inventory(
    payload: InventoryAdjust,
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(deps.require_admin),
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
    return InventoryAdjustResponse(ok=True)
