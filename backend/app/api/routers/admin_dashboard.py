from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import models, security, inventory as inventory_svc
from app.database import get_db
from app.services.reporting import dashboard as reporting_dashboard
from app.services.reporting import inventory as reporting_inventory
from app.schemas.dashboard import DashboardSummary
from app.schemas.inventory_view import InventoryOverview
from app.schemas.admin import SupplyOrderAck
from app.api import deps

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db), admin: models.StaffUser = Depends(deps.require_admin)):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/api/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(deps.require_admin),
):
    return reporting_dashboard.get_dashboard_summary(db)


@router.get("/admin/orders/closed", response_class=HTMLResponse)
def list_closed_orders(
    request: Request,
    day: str | None = Query(default=None, description="Date in YYYY-MM-DD format"),
    hour: int | None = Query(default=None, ge=0, le=23, description="Optional hour filter 0-23"),
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(deps.require_admin),
):

    try:
        if day:
            target_date = datetime.strptime(day, "%Y-%m-%d")
        else:
            target_date = datetime.utcnow()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    if hour is not None:
        start = start_of_day + timedelta(hours=hour)
        end = start + timedelta(hours=1)
    else:
        start = start_of_day
        end = start + timedelta(days=1)

    orders = reporting.list_closed_orders(db, start=start, end=end)
    selected_day = start.strftime("%Y-%m-%d")

    return templates.TemplateResponse(
        "orders_closed.html",
        {
            "request": request,
            "orders": orders,
            "selected_day": selected_day,
        },
    )


@router.get("/admin/inventory", response_class=HTMLResponse)
def admin_inventory(request: Request, db: Session = Depends(get_db), admin: models.StaffUser = Depends(deps.require_admin)):

    overview = reporting_inventory.build_inventory_overview(db)
    if overview.get("changed"):
        db.commit()

    return templates.TemplateResponse(
        "inventory.html",
        {
            "request": request,
            "items": overview.items,
            "supply_orders": overview.supply_orders,
            "supplier_directory": overview.supplier_directory,
        },
    )


@router.post("/admin/inventory/adjust")
def admin_inventory_adjust(
    request: Request,
    sku: str = Form(...),
    delta: float = Form(...),
    unit: str = Form("pcs"),
    reason: str = Form("adjust"),
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(deps.require_admin),
):
    item = db.query(models.InventoryItem).filter(models.InventoryItem.sku == sku).first()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    inventory_svc._record_movement(
        db,
        item_id=item.id,
        qty_delta=delta,
        unit=unit or item.unit,
        reason=reason,
        ref_type="admin-adjust",
        ref_id=None,
        created_by="admin",
    )
    db.commit()
    return RedirectResponse(url="/admin/inventory", status_code=303)


@router.post("/admin/inventory/supply-orders/{order_id}/ack", response_model=SupplyOrderAck)
def admin_supply_order_ack(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(deps.require_admin),
):
    order = inventory_svc.acknowledge_supply_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Supply order not found")
    db.commit()
    return {
        "status": "ok",
        "order": {
            "id": order.id,
            "state": order.state,
            "acknowledged_at": order.acknowledged_at.isoformat() if order.acknowledged_at else None,
        },
    }
