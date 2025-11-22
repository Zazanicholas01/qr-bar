from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from app import models, inventory as inventory_svc
from app.core.constants import PAYMENT_METHODS


def _normalize_payment(method: str, allowed: Iterable[str] = PAYMENT_METHODS) -> str:
    normalized = method.strip().lower()
    if normalized not in allowed:
        raise ValueError("Unsupported payment method")
    return normalized


def process_order(db: Session, order_id: int) -> models.Order:
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order is None:
        raise LookupError("Order not found")
    order.status = "processed"
    db.flush()
    return order


def delete_order(db: Session, order_id: int) -> None:
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order is None:
        raise LookupError("Order not found")
    db.delete(order)
    db.flush()


def reset_orders(db: Session) -> None:
    """Truncate orders and related tables for simulation/admin resets."""
    db.execute(
        text("TRUNCATE TABLE order_items, transactions, orders, users RESTART IDENTITY CASCADE")
    )
    db.flush()


def checkout_order(
    db: Session,
    order_id: int,
    payment_method: str,
    *,
    consume_inventory: bool = True,
    created_at: datetime | None = None,
    created_by: str | None = None,
) -> models.Order:
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order is None:
        raise LookupError("Order not found")

    method = _normalize_payment(payment_method)
    order.status = "closed"
    timestamp = created_at or datetime.utcnow()

    if order.transaction:
        order.transaction.method = method
        order.transaction.amount = order.total_amount
        order.transaction.created_at = timestamp
    else:
        transaction = models.Transaction(
            order=order,
            method=method,
            amount=order.total_amount,
            created_at=timestamp,
        )
        db.add(transaction)

    if consume_inventory:
        try:
            inventory_svc.consume_stock_for_order(db, order, created_by=created_by)
        except Exception:
            # Fail-safe: do not block checkout if inventory consumption fails
            pass

    db.flush()
    return order
