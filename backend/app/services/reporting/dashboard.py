from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.schemas.dashboard import (
    DashboardSummary,
    DashboardItem,
    DashboardPayment,
    DashboardHeatmaps,
)

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models


def get_dashboard_summary(db: Session) -> DashboardSummary:
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
    items = [DashboardItem(name=name, total=float(total)) for name, total in item_rows]

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
    payments = [DashboardPayment(method=method.capitalize(), count=count) for method, count in payment_rows]

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

    heatmaps = DashboardHeatmaps(
        hourly={
            "dates": [day.isoformat() for day in hourly_dates],
            "hours": list(range(24)),
            "values": hourly_values,
        },
        day_of_week={
            "weeks": [week.isoformat() for week in week_windows],
            "days": dow_days,
            "values": dow_values,
        },
    )

    return DashboardSummary(
        total_amount=float(total_amount or 0),
        closed_count=closed_count,
        items=items,
        payments=payments,
        heatmaps=heatmaps,
        generated_at=datetime.utcnow().isoformat(),
    )
