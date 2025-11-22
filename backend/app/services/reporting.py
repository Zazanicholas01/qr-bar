from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models, inventory as inventory_svc


def get_dashboard_summary(db: Session) -> dict[str, Any]:
    total_amount = (
        db.query(models.Order)
        .filter(models.Order.status == "closed")
        .with_entities(text("COALESCE(SUM(total_amount), 0)"))
        .scalar()
    )
    closed_count = (
        db.query(models.Order)
        .filter(models.Order.status == "closed")
        .count()
    )

    item_rows = (
        db.query(
            models.OrderItem.name,
            text("SUM(order_items.quantity * order_items.unit_price) AS total"),
        )
        .join(models.Order, models.OrderItem.order_id == models.Order.id)
        .filter(models.Order.status == "closed")
        .group_by(models.OrderItem.name)
        .order_by(text("total DESC"))
        .all()
    )
    items = [{"name": name, "total": float(total)} for name, total in item_rows]

    payment_rows = (
        db.query(
            models.Transaction.method,
            text("COUNT(*) AS count"),
        )
        .join(models.Order, models.Transaction.order_id == models.Order.id)
        .group_by(models.Transaction.method)
        .order_by(text("count DESC"))
        .all()
    )
    payments = [{"method": method.capitalize(), "count": count} for method, count in payment_rows]

    now = datetime.utcnow()

    hourly_rows = db.execute(
        text(
            """
            SELECT DATE(created_at) AS day,
                   EXTRACT(HOUR FROM created_at)::INT AS hour,
                   COUNT(*) AS order_count,
                   COALESCE(SUM(total_amount), 0) AS total_amount
            FROM orders
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY day, hour
            ORDER BY day, hour
            """
        )
    ).mappings().all()

    hourly_dates = [(now - timedelta(days=offset)).date() for offset in reversed(range(7))]
    hourly_values: dict[str, dict[str, float | int]] = {}
    for row in hourly_rows:
        day = row["day"]
        hour = int(row["hour"])
        key = f"{day.isoformat()}|{hour}"
        hourly_values[key] = {
            "order_count": int(row["order_count"]),
            "total_amount": float(row["total_amount"] or 0),
        }

    current_week_start = (now - timedelta(days=now.weekday())).date()
    week_windows = [current_week_start - timedelta(weeks=offset) for offset in reversed(range(8))]

    dow_rows = db.execute(
        text(
            """
            SELECT DATE_TRUNC('week', created_at)::date AS week_start,
                   EXTRACT(DOW FROM created_at)::INT AS dow,
                   COUNT(*) AS order_count,
                   COALESCE(SUM(total_amount), 0) AS total_amount
            FROM orders
            WHERE created_at >= NOW() - INTERVAL '8 weeks'
            GROUP BY week_start, dow
            ORDER BY week_start, dow
            """
        )
    ).mappings().all()

    dow_labels = {0: "Dom", 1: "Lun", 2: "Mar", 3: "Mer", 4: "Gio", 5: "Ven", 6: "Sab"}
    dow_order = [1, 2, 3, 4, 5, 6, 0]
    dow_days = [{"index": idx, "label": dow_labels[idx]} for idx in dow_order]
    dow_values: dict[str, dict[str, float | int]] = {}
    for row in dow_rows:
        week_start = row["week_start"]
        dow = int(row["dow"])
        key = f"{week_start.isoformat()}|{dow}"
        dow_values[key] = {
            "order_count": int(row["order_count"]),
            "total_amount": float(row["total_amount"] or 0),
        }

    heatmaps = {
        "hourly": {
            "dates": [day.isoformat() for day in hourly_dates],
            "hours": list(range(24)),
            "values": hourly_values,
        },
        "day_of_week": {
            "weeks": [week.isoformat() for week in week_windows],
            "days": dow_days,
            "values": dow_values,
        },
    }

    return {
        "total_amount": float(total_amount or 0),
        "closed_count": closed_count,
        "items": items,
        "payments": payments,
        "heatmaps": heatmaps,
        "generated_at": datetime.utcnow().isoformat(),
    }


def list_closed_orders(db: Session, start: datetime, end: datetime) -> list[models.Order]:
    return (
        db.query(models.Order)
        .filter(
            models.Order.status == "closed",
            models.Order.created_at >= start,
            models.Order.created_at < end,
        )
        .order_by(models.Order.created_at.desc())
        .all()
    )


def build_inventory_overview(db: Session) -> dict[str, Any]:
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
        {
            "sku": itm.sku,
            "name": itm.name,
            "unit": itm.unit,
            "qty": float((lvl.qty_on_hand_cached if lvl else 0) or 0),
        }
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

    supply_orders = []
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
            {
                "id": order.id,
                "product": item.name if item else "—",
                "state": order.state,
                "qty_text": qty_text,
                "supplier_name": supplier_name,
                "supplier_quote": supplier_quote,
                "total_price": fmt_currency(order.total_price),
                "alert_time": order.alert_triggered_at.strftime("%H:%M"),
                "ack_text": acknowledged_at.strftime("%H:%M") if acknowledged_at else None,
                "sla_hours": sla_hours,
                "elapsed_hours": elapsed_hours,
                "progress_pct": progress_pct,
                "slider_value": slider_value,
                "actionable": order.state == "alert",
                "restocked": is_fulfilled,
                "restock_text": restock_text,
                "sla_label": sla_label,
                "expires_text": expires_at_text,
                "expires_indicator": expires_indicator,
            }
        )

    suppliers = db.query(models.Supplier).order_by(models.Supplier.name).all()
    supplier_directory = []
    for supplier in suppliers:
        product_labels = []
        for sp in sorted(supplier.products, key=lambda p: (p.inventory_item.name if p.inventory_item else "")):
            label = sp.inventory_item.name if sp.inventory_item else f"Item #{sp.inventory_item_id}"
            if sp.price_per_unit:
                label = f"{label} ({fmt_currency(sp.price_per_unit)} / {sp.unit or (sp.inventory_item.unit if sp.inventory_item else '')})"
            product_labels.append(label)
        supplier_directory.append(
            {
                "name": supplier.name,
                "lead": supplier.lead_time_hours,
                "notes": supplier.notes,
                "products": product_labels,
            }
        )

    return {
        "items": items,
        "supply_orders": supply_orders,
        "supplier_directory": supplier_directory,
        "changed": bool(restocked or alerts_created),
    }
