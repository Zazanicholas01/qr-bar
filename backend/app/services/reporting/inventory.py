from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app import models, inventory as inventory_svc
from app.schemas.inventory_view import (
    InventoryOverview,
    InventoryItemView,
    SupplyOrderView,
    SupplierDirectoryEntry,
)


def build_inventory_overview(db: Session) -> InventoryOverview:
    """Gather inventory view plus recent supply orders and supplier directory."""
    restocked = inventory_svc.finalize_processed_supply_orders(db)

    default_loc = db.query(models.InventoryLocation).filter(models.InventoryLocation.name == "Default").first()
    default_loc_id = default_loc.id if default_loc else None
    join_cond = (models.StockLevel.item_id == models.InventoryItem.id)
    if default_loc_id is not None:
        join_cond = join_cond & (models.StockLevel.location_id == default_loc_id)
    rows = (
        db.query(models.InventoryItem, models.StockLevel)
        .outerjoin(models.StockLevel, join_cond)
        .order_by(models.InventoryItem.name)
        .all()
    )
    items = [
        InventoryItemView(
            sku=itm.sku,
            name=itm.name,
            unit=itm.unit,
            qty=float((lvl.qty_on_hand_cached if lvl else 0) or 0),
        )
        for itm, lvl in rows
    ]
    alerts_created = inventory_svc.ensure_replenishment_alerts(db)

    now = datetime.utcnow()
    supply_rows = (
        db.query(models.SupplyOrder, models.InventoryItem, models.Supplier)
        .outerjoin(models.InventoryItem, models.SupplyOrder.inventory_item_id == models.InventoryItem.id)
        .outerjoin(models.Supplier, models.SupplyOrder.supplier_id == models.Supplier.id)
        .order_by(models.SupplyOrder.alert_triggered_at.desc())
        .limit(20)
        .all()
    )

    def fmt_currency(val):
        if val is None:
            return "—"
        return f"€{float(val):,.2f}"

    supply_orders: list[SupplyOrderView] = []
    for order, item, supplier in supply_rows:
        sla_hours = float(inventory_svc.resolve_sla_hours(order.sla_hours, supplier))
        acknowledged_at = order.acknowledged_at
        elapsed_hours = (
            max(0.0, (now - acknowledged_at).total_seconds() / 3600.0) if acknowledged_at else 0.0
        )
        progress_pct = min(100.0, (elapsed_hours / sla_hours) * 100.0) if acknowledged_at and sla_hours else 0.0
        slider_value = min(elapsed_hours, sla_hours) if acknowledged_at else 0.0
        fulfillment_eta = acknowledged_at + timedelta(hours=sla_hours) if acknowledged_at and sla_hours else None
        is_fulfilled = order.state == "fulfilled"
        if sla_hours < 1:
            sla_label = f"{max(1, int(round(sla_hours * 60)))}m"
        else:
            sla_label = f"{sla_hours:.0f}h"
        restock_text = None
        if is_fulfilled:
            if fulfillment_eta:
                restock_text = f"Reintegro automatico alle {fulfillment_eta.strftime('%H:%M')}"
            else:
                restock_text = "Reintegro automatico completato"
        if fulfillment_eta:
            expires_at_text = fulfillment_eta.strftime("%H:%M")
            minutes_left = max(0, int((fulfillment_eta - now).total_seconds() / 60))
            if minutes_left > 0:
                expires_indicator = f"Scadenza tra {minutes_left}m"
            else:
                expires_indicator = "In consegna"
        else:
            expires_at_text = None
            expires_indicator = None
        qty_text = f"{float(order.suggested_qty):g} {order.unit}"
        supplier_name = supplier.name if supplier else "—"
        supplier_quote = supplier_name
        if order.price_per_unit and supplier_name:
            supplier_quote = f"{supplier_name} · {fmt_currency(order.price_per_unit)} / {order.unit}"
        supply_orders.append(
            SupplyOrderView(
                id=order.id,
                product=item.name if item else "—",
                state=order.state,
                qty_text=qty_text,
                supplier_name=supplier_name,
                supplier_quote=supplier_quote,
                total_price=fmt_currency(order.total_price),
                alert_time=order.alert_triggered_at.strftime("%H:%M"),
                ack_text=acknowledged_at.strftime("%H:%M") if acknowledged_at else None,
                sla_hours=sla_hours,
                elapsed_hours=elapsed_hours,
                progress_pct=progress_pct,
                slider_value=slider_value,
                actionable=order.state == "alert",
                restocked=is_fulfilled,
                restock_text=restock_text,
                sla_label=sla_label,
                expires_text=expires_at_text,
                expires_indicator=expires_indicator,
            )
        )

    suppliers = db.query(models.Supplier).order_by(models.Supplier.name).all()
    supplier_directory: list[SupplierDirectoryEntry] = []
    for supplier in suppliers:
        product_labels = []
        for sp in sorted(supplier.products, key=lambda p: (p.inventory_item.name if p.inventory_item else "")):
            label = sp.inventory_item.name if sp.inventory_item else f"Item #{sp.inventory_item_id}"
            if sp.price_per_unit:
                label = f"{label} ({fmt_currency(sp.price_per_unit)} / {sp.unit or (sp.inventory_item.unit if sp.inventory_item else '')})"
            product_labels.append(label)
        supplier_directory.append(
            SupplierDirectoryEntry(
                name=supplier.name,
                lead=supplier.lead_time_hours,
                notes=supplier.notes,
                products=product_labels,
            )
        )

    return InventoryOverview(
        items=items,
        supply_orders=supply_orders,
        supplier_directory=supplier_directory,
    )
