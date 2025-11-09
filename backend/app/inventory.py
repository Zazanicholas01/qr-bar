from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import and_

from . import models


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
    # Idempotency check for order-related movements
    exists = db.query(models.StockMovement).filter(
        and_(
            models.StockMovement.item_id == item_id,
            models.StockMovement.reason == reason,
            models.StockMovement.ref_type == ref_type,
            models.StockMovement.ref_id == ref_id,
        )
    ).first()
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
