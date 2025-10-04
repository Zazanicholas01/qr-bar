import math
import random
import time
import uuid
from decimal import Decimal
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal, get_db
from app.routers.menu import CATEGORIES

router = APIRouter()

MENU_ITEMS = [item for category in CATEGORIES for item in category["items"]]
DEFAULT_TABLES = [f"table{i}" for i in range(1, 11)]
ORDER_RATE_PER_HOUR = 15
SECONDS_PER_ORDER = 3600 / ORDER_RATE_PER_HOUR


class SimulationRequest(BaseModel):
    hours: float = Field(default=1.0, gt=0, description="Simulated hours to run")
    time_scale: float = Field(
        default=60.0,
        gt=0,
        description="How many simulated seconds elapse per real second. Higher = faster.",
    )
    seed: int | None = Field(default=None, description="Optional random seed for reproducibility")
    tables: List[str] | None = Field(
        default=None,
        description="Override list of table codes to target. Defaults to known tables.",
    )
    max_orders_per_user: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Maximum number of items lines per generated order",
    )


def _ensure_table(session: Session, code: str) -> models.Table:
    table = session.query(models.Table).filter(models.Table.code == code).first()
    if table is None:
        table = models.Table(code=code)
        session.add(table)
        session.flush()
    return table


def _pick_items(max_lines: int) -> list[dict]:
    total_items = max(1, min(max_lines, len(MENU_ITEMS)))
    line_count = random.randint(1, total_items)
    return random.sample(MENU_ITEMS, line_count)


def _create_order(session: Session, table: models.Table) -> models.Order:
    user_name = f"SimUser {uuid.uuid4().hex[:6]}"
    email = f"{user_name.lower()}@example.com"

    user = models.User(name=user_name, email=email, table=table, table_code=table.code)
    session.add(user)
    session.flush()

    order = models.Order(user=user, table=table, table_code=table.code)

    total_quantity = 0
    total_amount = Decimal("0")
    for item in _pick_items(max_lines=session.info.get("max_orders_per_user", 3)):
        quantity = random.randint(1, 3)
        price = Decimal(str(item["price"]))
        total_quantity += quantity
        total_amount += price * quantity
        order.items.append(
            models.OrderItem(
                product_id=item["id"],
                name=item["name"],
                unit_price=price,
                quantity=quantity,
            )
        )

    order.total_quantity = total_quantity
    order.total_amount = total_amount
    session.add(order)
    return order


def _run_simulation(params: SimulationRequest) -> None:
    if params.seed is not None:
        random.seed(params.seed)

    session = SessionLocal()
    try:
        session.info["max_orders_per_user"] = params.max_orders_per_user

        tables_source = params.tables or DEFAULT_TABLES
        available_tables = list(tables_source)
        if not available_tables:
            available_tables = DEFAULT_TABLES

        for code in available_tables:
            _ensure_table(session, code)
        session.commit()

        total_users = max(1, math.ceil(params.hours * ORDER_RATE_PER_HOUR))
        sleep_interval = SECONDS_PER_ORDER / params.time_scale

        for _ in range(total_users):
            table_code = random.choice(available_tables)
            table = _ensure_table(session, table_code)
            _create_order(session, table)
            session.commit()

            if sleep_interval > 0:
                time.sleep(sleep_interval)
    finally:
        session.close()


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_simulation(
    request: SimulationRequest,
    background_tasks: BackgroundTasks,
):
    background_tasks.add_task(_run_simulation, request)
    return {"message": "Simulation started", "total_users": int(request.hours * ORDER_RATE_PER_HOUR)}


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_simulation(db: Session = Depends(get_db)):
    db.execute(text("TRUNCATE TABLE order_items, orders, users RESTART IDENTITY CASCADE"))
    db.commit()
