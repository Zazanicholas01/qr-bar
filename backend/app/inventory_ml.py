from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models


def _safe_float(value: Decimal | float | None) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _sum_sales_between(
    db: Session, item_id: int, *, start: datetime | None, end: datetime | None = None
) -> float:
    query = db.query(func.coalesce(func.sum(models.StockMovement.qty_delta), 0)).filter(
        models.StockMovement.item_id == item_id,
        models.StockMovement.reason == "sale",
    )
    if start is not None:
        query = query.filter(models.StockMovement.occurred_at >= start)
    if end is not None:
        query = query.filter(models.StockMovement.occurred_at < end)
    total = query.scalar() or Decimal("0")
    return abs(_safe_float(total))


def _qty_on_hand(db: Session, item_id: int) -> float:
    level = (
        db.query(models.StockLevel)
        .filter(models.StockLevel.item_id == item_id)
        .order_by(models.StockLevel.updated_at.desc())
        .first()
    )
    return _safe_float(level.qty_on_hand_cached if level else 0)


def _supplier_product(db: Session, item_id: int) -> models.SupplierProduct | None:
    return (
        db.query(models.SupplierProduct)
        .filter(models.SupplierProduct.inventory_item_id == item_id)
        .order_by(models.SupplierProduct.price_per_unit.asc())
        .first()
    )


def _preference_score(db: Session, item_id: int, *, window_days: int = 30) -> float:
    now = datetime.utcnow()
    window_start = now - timedelta(days=window_days)
    product_rows = (
        db.query(models.RecipeComponent.recipe_item_id)
        .filter(models.RecipeComponent.component_item_id == item_id)
        .distinct()
        .all()
    )
    product_ids = [pid for (pid,) in product_rows if pid]
    if not product_ids:
        return 0.0

    total_orders = (
        db.query(func.count(models.OrderItem.id))
        .join(models.Order, models.OrderItem.order_id == models.Order.id)
        .filter(models.Order.created_at >= window_start)
        .scalar()
    ) or 0
    if total_orders == 0:
        return 0.0

    item_orders = (
        db.query(func.count(models.OrderItem.id))
        .join(models.Order, models.OrderItem.order_id == models.Order.id)
        .filter(
            models.Order.created_at >= window_start,
            models.OrderItem.product_id.in_(product_ids),
        )
        .scalar()
    ) or 0

    return float(item_orders) / float(total_orders)


def _payment_mix(db: Session, window_days: int = 30) -> dict[str, float]:
    now = datetime.utcnow()
    window_start = now - timedelta(days=window_days)
    rows = (
        db.query(models.Transaction.method, func.count(models.Transaction.id))
        .join(models.Order, models.Transaction.order_id == models.Order.id)
        .filter(models.Order.created_at >= window_start)
        .group_by(models.Transaction.method)
        .all()
    )
    total = sum(count for _, count in rows)
    if total == 0:
        return {}
    return {method: count / total for method, count in rows}


def _lead_time_stats(db: Session, item_id: int) -> tuple[float, float, float, float]:
    duration_seconds = func.extract(
        "epoch",
        models.SupplyOrder.fulfilled_at - models.SupplyOrder.acknowledged_at,
    )
    rows = (
        db.query(
            func.coalesce(func.avg(duration_seconds), 0).label("avg_seconds"),
            func.coalesce(func.stddev_pop(duration_seconds), 0).label("std_seconds"),
        )
        .filter(
            models.SupplyOrder.inventory_item_id == item_id,
            models.SupplyOrder.fulfilled_at.isnot(None),
            models.SupplyOrder.acknowledged_at.isnot(None),
        )
        .first()
    )
    avg_seconds = rows.avg_seconds if rows else 0
    std_seconds = rows.std_seconds if rows else 0
    total_orders = (
        db.query(func.count(models.SupplyOrder.id))
        .filter(models.SupplyOrder.inventory_item_id == item_id)
        .scalar()
    ) or 0
    fulfilled_orders = (
        db.query(func.count(models.SupplyOrder.id))
        .filter(
            models.SupplyOrder.inventory_item_id == item_id,
            models.SupplyOrder.state == "fulfilled",
        )
        .scalar()
    ) or 0
    fill_rate = (fulfilled_orders / total_orders) if total_orders else 0.0

    late_expr = func.extract(
        "epoch", models.SupplyOrder.fulfilled_at - models.SupplyOrder.acknowledged_at
    )
    late_count = (
        db.query(func.count(models.SupplyOrder.id))
        .filter(
            models.SupplyOrder.inventory_item_id == item_id,
            models.SupplyOrder.fulfilled_at.isnot(None),
            models.SupplyOrder.acknowledged_at.isnot(None),
            models.SupplyOrder.sla_hours.isnot(None),
            late_expr > (models.SupplyOrder.sla_hours * 3600),
        )
        .scalar()
    ) or 0
    reliability = 1.0 - ((late_count / fulfilled_orders) if fulfilled_orders else 0.0)

    return (
        _safe_float(avg_seconds) / 3600.0,
        _safe_float(std_seconds) / 3600.0,
        reliability,
        fill_rate,
    )


def build_feature_snapshot(
    db: Session,
    item: models.InventoryItem,
    *,
    qty_on_hand: float | None = None,
) -> dict[str, Any]:
    now = datetime.utcnow()
    qoh = qty_on_hand if qty_on_hand is not None else _qty_on_hand(db, item.id)
    sales_7d = _sum_sales_between(db, item.id, start=now - timedelta(days=7))
    sales_30d = _sum_sales_between(db, item.id, start=now - timedelta(days=30))
    sales_90d = _sum_sales_between(db, item.id, start=now - timedelta(days=90))
    prev_week = _sum_sales_between(
        db,
        item.id,
        start=now - timedelta(days=14),
        end=now - timedelta(days=7),
    )
    trend = 0.0
    if prev_week > 0:
        trend = (sales_7d - prev_week) / prev_week

    total_sales_all = (
        db.query(func.coalesce(func.sum(models.StockMovement.qty_delta), 0))
        .filter(
            models.StockMovement.reason == "sale",
            models.StockMovement.occurred_at >= now - timedelta(days=30),
        )
        .scalar()
    ) or Decimal("0")
    popularity = 0.0
    if total_sales_all:
        denominator = abs(_safe_float(total_sales_all))
        popularity = (abs(sales_30d) / denominator) if denominator else 0.0

    supplier_product = _supplier_product(db, item.id)
    supplier = supplier_product.supplier if supplier_product else None
    supplier_lead = supplier.lead_time_hours if supplier and supplier.lead_time_hours else None
    avg_lead_hours, std_lead_hours, reliability, fill_rate = _lead_time_stats(db, item.id)

    preference = _preference_score(db, item.id)
    payment_mix = _payment_mix()

    on_order_qty = (
        db.query(func.coalesce(func.sum(models.SupplyOrder.suggested_qty), 0))
        .filter(
            models.SupplyOrder.inventory_item_id == item.id,
            models.SupplyOrder.state.in_(["alert", "processed"]),
        )
        .scalar()
    ) or Decimal("0")

    avg_checkout_seconds = (
        db.query(
            func.coalesce(
                func.avg(
                    func.extract(
                        "epoch",
                        models.Transaction.created_at - models.Order.created_at,
                    )
                ),
                0,
            )
        )
        .join(models.Order, models.Transaction.order_id == models.Order.id)
        .filter(models.Order.created_at >= now - timedelta(days=30))
        .scalar()
    ) or 0

    demand_features = {
        "sales_last_7d": sales_7d,
        "sales_last_30d": sales_30d,
        "sales_last_90d": sales_90d,
        "avg_daily_consumption": (sales_30d / 30.0) if sales_30d else 0.0,
        "trend_vs_prev_week_pct": trend,
        "seasonality_day_of_week": now.weekday(),
        "seasonality_hour": now.hour,
        "seasonality_is_weekend": now.weekday() >= 5,
        "popularity_score": popularity,
    }

    supplier_features = {
        "lead_time_hours": _safe_float(supplier_lead),
        "lead_time_avg_hours": avg_lead_hours,
        "lead_time_std_hours": std_lead_hours,
        "fill_rate": fill_rate,
        "price_per_unit": _safe_float(supplier_product.price_per_unit) if supplier_product else 0.0,
        "discount_pct": _safe_float(supplier_product.discount_pct) if supplier_product else 0.0,
        "on_order_qty": _safe_float(on_order_qty),
        "delivery_reliability": reliability,
    }

    customer_features = {
        "preference_score": preference,
        "payment_mix": payment_mix,
        "avg_checkout_time_minutes": (_safe_float(avg_checkout_seconds) / 60.0),
    }

    operations_features = {
        "qty_on_hand": qoh,
        "par_level": _safe_float(item.par_level),
        "reorder_point": _safe_float(item.reorder_point),
        "storage_capacity_qty": _safe_float(item.storage_capacity_qty or item.par_level),
        "holding_cost_per_unit": _safe_float(item.holding_cost_per_unit),
        "stockout_cost_per_unit": _safe_float(item.stockout_cost_per_unit),
        "alert_threshold_qty": _safe_float(item.alert_threshold_qty),
        "starting_stock_qty": _safe_float(item.starting_stock_qty),
    }

    temporal_features = {
        "timestamp": now.isoformat(),
        "day_of_week": now.weekday(),
        "hour": now.hour,
    }

    return {
        "generated_at": now.isoformat(),
        "item": {
            "id": item.id,
            "sku": item.sku,
            "name": item.name,
        },
        "demand": demand_features,
        "supplier": supplier_features,
        "customer": customer_features,
        "operations": operations_features,
        "temporal": temporal_features,
    }


def record_training_snapshot(
    db: Session,
    *,
    item: models.InventoryItem,
    supply_order: models.SupplyOrder,
    qty_on_hand: float,
    suggested_qty: float,
    simulation_run_id: int | None,
) -> None:
    context = build_feature_snapshot(db, item, qty_on_hand=qty_on_hand)
    decision_snapshot = {
        "qty_on_hand": qty_on_hand,
        "reorder_point": _safe_float(item.reorder_point),
        "par_level": _safe_float(item.par_level),
        "alert_threshold_qty": _safe_float(item.alert_threshold_qty),
        "suggested_qty": suggested_qty,
        "unit": supply_order.unit,
        "state": supply_order.state,
        "simulation_run_id": simulation_run_id,
        "supply_order_created_at": supply_order.alert_triggered_at.isoformat()
        if supply_order.alert_triggered_at
        else None,
    }
    log = models.InventoryPolicyTrainingLog(
        item_id=item.id,
        supply_order_id=supply_order.id,
        simulation_run_id=simulation_run_id,
        context_features=context,
        decision_snapshot=decision_snapshot,
    )
    db.add(log)


def mark_supply_order_outcome(db: Session, supply_order: models.SupplyOrder) -> None:
    log = (
        db.query(models.InventoryPolicyTrainingLog)
        .filter(models.InventoryPolicyTrainingLog.supply_order_id == supply_order.id)
        .order_by(models.InventoryPolicyTrainingLog.created_at.desc())
        .first()
    )
    if not log:
        return

    fulfilled_at = supply_order.fulfilled_at or datetime.utcnow()
    acked_at = supply_order.acknowledged_at or supply_order.alert_triggered_at or fulfilled_at
    wait_hours = max(0.0, (fulfilled_at - acked_at).total_seconds() / 3600.0)
    sla_hours = _safe_float(supply_order.sla_hours)

    log.outcome_snapshot = {
        "state": supply_order.state,
        "fulfilled_at": fulfilled_at.isoformat(),
        "acknowledged_at": acked_at.isoformat() if acked_at else None,
        "wait_hours": wait_hours,
        "sla_hours": sla_hours,
        "late": sla_hours > 0 and wait_hours > sla_hours,
        "qty_received": _safe_float(supply_order.suggested_qty),
    }
