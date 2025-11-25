from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import random
from sqlalchemy.orm import Session
from sqlalchemy import and_

from . import models, inventory_ml


TEST_SLA_MINUTES = 2
TEST_SLA_HOURS = (Decimal(TEST_SLA_MINUTES) / Decimal(60)) if TEST_SLA_MINUTES else None


def resolve_sla_hours(explicit_hours: Decimal | None, supplier: models.Supplier | None) -> Decimal:
    """Return the SLA duration (hours) honoring the testing override when set."""
    if TEST_SLA_HOURS is not None and float(TEST_SLA_HOURS) > 0:
        return TEST_SLA_HOURS
    if explicit_hours is not None and float(explicit_hours) > 0:
        return Decimal(explicit_hours)
    supplier_lead = supplier.lead_time_hours if supplier else None
    if supplier_lead is not None and float(supplier_lead) > 0:
        return Decimal(supplier_lead)
    return Decimal("24")


def _get_default_location_id(db: Session) -> int:
    """Resolve or create the default inventory location and return its id."""
    loc = db.query(models.InventoryLocation).filter(models.InventoryLocation.name == "Default").first()
    if loc:
        return loc.id
    loc = models.InventoryLocation(name="Default")
    db.add(loc)
    db.flush()
    return loc.id


def _get_or_create_stock_level(db: Session, item_id: int, location_id: int | None = None) -> models.StockLevel:
    loc_id = location_id if location_id is not None else _get_default_location_id(db)
    level = db.query(models.StockLevel).filter(
        models.StockLevel.item_id == item_id,
        models.StockLevel.location_id == loc_id,
    ).first()
    if level is None:
        level = models.StockLevel(item_id=item_id, location_id=loc_id, qty_on_hand_cached=Decimal("0"))
        db.add(level)
    return level


def _record_movement(
    db: Session,
    *,
    item_id: int,
    qty_delta: Decimal,
    unit: str,
    reason: str,
    ref_type: str | None,
    ref_id: int | None,
    location_id: int | None = None,
    created_by: str | None = None,
) -> None:
    # Idempotency only applies when we have a concrete reference identifier (e.g. orders)
    if ref_type is not None and ref_id is not None:
        # Check pending objects in the current session to avoid duplicate inserts before flush
        for pending in db.new:
            if (
                isinstance(pending, models.StockMovement)
                and pending.item_id == item_id
                and pending.reason == reason
                and pending.ref_type == ref_type
                and pending.ref_id == ref_id
            ):
                return
        exists = (
            db.query(models.StockMovement)
            .filter(
                and_(
                    models.StockMovement.item_id == item_id,
                    models.StockMovement.reason == reason,
                    models.StockMovement.ref_type == ref_type,
                    models.StockMovement.ref_id == ref_id,
                )
            )
            .first()
        )
        if exists:
            return

    mv = models.StockMovement(
        item_id=item_id,
        location_id=location_id if location_id is not None else _get_default_location_id(db),
        qty_delta=qty_delta,
        unit=unit,
        reason=reason,
        ref_type=ref_type,
        ref_id=ref_id,
        occurred_at=datetime.utcnow(),
        created_by=created_by,
    )
    db.add(mv)

    # Update cached level
    level = _get_or_create_stock_level(db, item_id=item_id, location_id=location_id if location_id is not None else _get_default_location_id(db))
    level.qty_on_hand_cached = (level.qty_on_hand_cached or Decimal("0")) + Decimal(qty_delta)
    level.updated_at = datetime.utcnow()


def consume_stock_for_order(db: Session, order: models.Order, *, location_id: int | None = None, created_by: str | None = None) -> None:
    """Decrement stock according to recipes for all items in the order.

    Safe to call multiple times — idempotent per (order, item) thanks to movement uniqueness.
    """
    if not order or not order.items:
        return

    for item in order.items:
        # Find recipe for the sold product
        recipe = db.query(models.Recipe).filter(models.Recipe.product_id == item.product_id).first()
        if not recipe:
            # No recipe defined → skip consumption
            continue

        components = db.query(models.RecipeComponent).filter(
            models.RecipeComponent.recipe_item_id == recipe.product_id
        ).all()

        if not components:
            continue

        # Scale by quantity sold relative to recipe yield (default yield=1)
        yield_qty = Decimal(recipe.yield_qty or 1)
        multiplier = Decimal(item.quantity) / (yield_qty if yield_qty != 0 else Decimal("1"))

        for comp in components:
            qty_needed = Decimal(comp.qty_per_yield) * multiplier
            # Negative movement for sale
            _record_movement(
                db,
                item_id=comp.component_item_id,
                qty_delta=-qty_needed,
                unit=comp.unit,
                reason="sale",
                ref_type="order",
                ref_id=order.id,
                location_id=location_id,
                created_by=created_by,
            )


def ensure_replenishment_alerts(db: Session, simulation_run_id: int | None = None) -> bool:
    """Insert SupplyOrder rows whenever stock drops below the reorder point."""
    default_loc = _get_default_location_id(db)
    created = False
    now = datetime.utcnow()

    rows = (
        db.query(models.InventoryItem, models.StockLevel)
        .outerjoin(
            models.StockLevel,
            and_(
                models.StockLevel.item_id == models.InventoryItem.id,
                models.StockLevel.location_id == default_loc,
            ),
        )
        .all()
    )
    for item, level in rows:
        reorder_point = Decimal(item.reorder_point or 0)
        threshold_qty = Decimal(item.alert_threshold_qty or 0)
        trigger_qty = max(reorder_point, threshold_qty)
        if trigger_qty <= 0:
            continue
        qty_on_hand = Decimal(level.qty_on_hand_cached or 0) if level else Decimal("0")
        if qty_on_hand > trigger_qty:
            continue
        existing_order = (
            db.query(models.SupplyOrder)
            .filter(models.SupplyOrder.inventory_item_id == item.id)
            .order_by(models.SupplyOrder.alert_triggered_at.desc())
            .first()
        )
        if existing_order:
            if existing_order.state == "alert":
                continue
            if existing_order.state == "processed":
                if not existing_order.acknowledged_at:
                    continue
                sla_reference = float(resolve_sla_hours(existing_order.sla_hours, existing_order.supplier))
                if sla_reference > 0 and (now - existing_order.acknowledged_at) < timedelta(hours=sla_reference):
                    continue

        par_level = Decimal(item.par_level or 0)
        suggested_qty = par_level - qty_on_hand if par_level and par_level > qty_on_hand else trigger_qty
        if suggested_qty <= 0:
            suggested_qty = trigger_qty

        supplier_product = (
            db.query(models.SupplierProduct)
            .filter(models.SupplierProduct.inventory_item_id == item.id)
            .order_by(models.SupplierProduct.price_per_unit.asc())
            .first()
        )
        supplier_id = supplier_product.supplier_id if supplier_product else None
        unit = supplier_product.unit if supplier_product and supplier_product.unit else item.unit
        price_per_unit = supplier_product.price_per_unit if supplier_product else None
        total_price = price_per_unit * suggested_qty if price_per_unit is not None else None
        supplier_obj = supplier_product.supplier if supplier_product else None
        sla_hours = resolve_sla_hours(
            supplier_obj.lead_time_hours if supplier_obj and supplier_obj.lead_time_hours else None,
            supplier_obj,
        )

        order = models.SupplyOrder(
            inventory_item_id=item.id,
            supplier_id=supplier_id,
            state="alert",
            suggested_qty=suggested_qty,
            unit=unit or item.unit,
            price_per_unit=price_per_unit,
            total_price=total_price,
            sla_hours=sla_hours,
            alert_triggered_at=now,
        )
        db.add(order)
        db.flush([order])
        inventory_ml.record_training_snapshot(
            db,
            item=item,
            supply_order=order,
            qty_on_hand=float(qty_on_hand),
            suggested_qty=float(suggested_qty),
            simulation_run_id=simulation_run_id,
            demand_qty=None,
        )
        created = True

    if created:
        db.flush()
    return created


def finalize_processed_supply_orders(db: Session) -> bool:
    """Restock items for processed orders whose SLA timer completed."""
    now = datetime.utcnow()
    changed = False

    orders = (
        db.query(models.SupplyOrder)
        .filter(
            models.SupplyOrder.state == "processed",
            models.SupplyOrder.acknowledged_at.isnot(None),
        )
        .all()
    )

    for order in orders:
        ack = order.acknowledged_at
        if not ack:
            continue
        sla_reference = resolve_sla_hours(order.sla_hours, order.supplier)
        if (now - ack) < timedelta(hours=float(sla_reference)):
            continue

        item = order.inventory_item
        if not item:
            continue

        qty = Decimal(order.suggested_qty or 0)
        if qty <= 0:
            continue

        _record_movement(
            db,
            item_id=item.id,
            qty_delta=qty,
            unit=order.unit or item.unit,
            reason="restock",
            ref_type="supply-order",
            ref_id=order.id,
            created_by="auto-restock",
        )
        order.state = "fulfilled"
        order.fulfilled_at = now
        inventory_ml.mark_supply_order_outcome(db, order)
        changed = True

    if changed:
        db.flush()

    return changed


def acknowledge_supply_order(db: Session, order_id: int) -> models.SupplyOrder | None:
    order = db.query(models.SupplyOrder).filter(models.SupplyOrder.id == order_id).first()
    if not order:
        return None
    if order.state != "processed":
        order.state = "processed"
        order.acknowledged_at = datetime.utcnow()
        order.sla_hours = resolve_sla_hours(order.sla_hours, order.supplier)
    return order


def auto_acknowledge_supply_orders(
    db: Session,
    *,
    jitter_range: tuple[float, float] = (0.85, 1.25),
) -> bool:
    """Automatically acknowledge supply orders to keep the simulator flowing."""

    pending = (
        db.query(models.SupplyOrder)
        .filter(models.SupplyOrder.state == "alert")
        .all()
    )
    changed = False
    if not pending:
        return changed

    low, high = jitter_range
    for order in pending:
        acked = acknowledge_supply_order(db, order.id)
        if not acked:
            continue
        if acked.sla_hours:
            factor = Decimal(str(random.uniform(low, high)))
            acked.sla_hours = Decimal(acked.sla_hours) * factor
        changed = True

    if changed:
        db.flush()
    return changed
