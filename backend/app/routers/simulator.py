import logging
import math
import random
import threading
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field, validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import inventory as inventory_svc, inventory_ml, models, security
from app.database import SessionLocal, get_db
from app.routers.menu import CATEGORIES

logger = logging.getLogger(__name__)
# Ensure our simulator logs are visible even if root is at WARNING
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

router = APIRouter()

MENU_ITEMS = [item for category in CATEGORIES for item in category["items"]]
DEFAULT_TABLES = [f"table{i}" for i in range(1, 11)]
ORDER_RATE_PER_HOUR = 15
SECONDS_PER_ORDER = 3600 / ORDER_RATE_PER_HOUR
SIM_PAYMENT_METHODS = ["cash", "card", "mobile", "other"]


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
    runtime_minutes: int = Field(
        default=5,
        ge=1,
        le=1440,
        description="Real minutes to keep the simulator active.",
    )
    process_delay_min_minutes: float = Field(
        default=1.0,
        ge=0.1,
        description="Minimum minutes before an order moves from pending to processed.",
    )
    process_delay_max_minutes: float = Field(
        default=3.0,
        ge=0.1,
        description="Maximum minutes before an order moves from pending to processed.",
    )
    checkout_delay_min_minutes: float = Field(
        default=3.0,
        ge=0.5,
        description="Minimum minutes between processing and checkout.",
    )
    checkout_delay_max_minutes: float = Field(
        default=5.0,
        ge=0.5,
        description="Maximum minutes between processing and checkout.",
    )
    label: str | None = Field(
        default=None,
        description="Optional label for the simulation run.",
    )

    @validator("process_delay_max_minutes")
    def _validate_process_range(cls, v, values):
        min_val = values.get("process_delay_min_minutes", 0)
        if v < min_val:
            raise ValueError("process_delay_max_minutes must be >= process_delay_min_minutes")
        return v

    @validator("checkout_delay_max_minutes")
    def _validate_checkout_range(cls, v, values):
        min_val = values.get("checkout_delay_min_minutes", 0)
        if v < min_val:
            raise ValueError("checkout_delay_max_minutes must be >= checkout_delay_min_minutes")
        return v


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


def _schedule_processing(order_id: int, run_id: int | None, params: SimulationRequest) -> None:
    delay_seconds = random.uniform(
        params.process_delay_min_minutes,
        params.process_delay_max_minutes,
    ) * 60.0
    timer = threading.Timer(
        delay_seconds,
        _mark_order_processed,
        args=(order_id, run_id, params.checkout_delay_min_minutes, params.checkout_delay_max_minutes),
    )
    timer.daemon = True
    timer.start()


def _mark_order_processed(
    order_id: int,
    run_id: int | None,
    checkout_min: float,
    checkout_max: float,
) -> None:
    session = SessionLocal()
    try:
        order = session.query(models.Order).filter(models.Order.id == order_id).first()
        if not order:
            logger.warning("Sim processing skipped: order %s not found", order_id)
            return
        if order.status == "closed":
            logger.info("Sim processing skipped: order %s already closed", order_id)
            return
        order.status = "processed"
        session.commit()
        logger.info("Sim order %s marked as processed", order_id)
    except Exception as exc:
        session.rollback()
        logger.exception("Sim order %s processing failed: %s", order_id, exc)
        return
    finally:
        session.close()

    delay_seconds = random.uniform(checkout_min, checkout_max) * 60.0
    timer = threading.Timer(delay_seconds, _checkout_order, args=(order_id, run_id))
    timer.daemon = True
    timer.start()


def _checkout_order(order_id: int, run_id: int | None) -> None:
    session = SessionLocal()
    try:
        order = session.query(models.Order).filter(models.Order.id == order_id).first()
        if not order:
            logger.warning("Sim checkout skipped: order %s not found", order_id)
            return
        if order.status == "closed":
            logger.info("Sim checkout skipped: order %s already closed", order_id)
            return

        method = random.choice(SIM_PAYMENT_METHODS)
        order.status = "closed"
        if order.transaction:
            order.transaction.method = method
            order.transaction.amount = order.total_amount
            order.transaction.created_at = datetime.utcnow()
        else:
            session.add(
                models.Transaction(
                    order=order,
                    method=method,
                    amount=order.total_amount,
                )
            )

        inventory_svc.consume_stock_for_order(session, order, created_by="simulator")
        movements = (
            session.query(models.StockMovement)
            .filter(
                models.StockMovement.ref_type == "order",
                models.StockMovement.ref_id == order.id,
                models.StockMovement.reason == "sale",
            )
            .all()
        )
        consumption_map: dict[int, float] = {}
        for movement in movements:
            if not movement.item_id:
                continue
            consumption_map[movement.item_id] = consumption_map.get(movement.item_id, 0.0) + abs(
                float(movement.qty_delta or 0)
            )
        for item_id, consumed_qty in consumption_map.items():
            item = (
                session.query(models.InventoryItem)
                .filter(models.InventoryItem.id == item_id)
                .first()
            )
            if not item:
                continue
            inventory_ml.record_training_snapshot(
                session,
                item=item,
                supply_order=None,
                qty_on_hand=None,
                suggested_qty=consumed_qty,
                simulation_run_id=run_id,
                event="checkout",
                metadata={"order_id": order.id},
            )
        restocked = inventory_svc.finalize_processed_supply_orders(session)
        try:
            alerts_created = inventory_svc.ensure_replenishment_alerts(session, simulation_run_id=run_id)
            acknowledged = inventory_svc.auto_acknowledge_supply_orders(session)
        except Exception as exc:
            logger.exception("Sim order %s supply workflow failed: %s", order_id, exc)
            alerts_created = False
            acknowledged = False

        run = None
        if run_id is not None:
            run = session.query(models.SimulationRun).filter(models.SimulationRun.id == run_id).first()
        if run:
            run.orders_closed = (run.orders_closed or 0) + 1

        if restocked or alerts_created or acknowledged:
            session.flush()
        session.commit()
        logger.info(
            "Sim order %s closed (run_id=%s, restocked=%s, alerts=%s, ack=%s)",
            order.id,
            run_id,
            restocked,
            alerts_created,
            acknowledged,
        )
    except Exception as exc:
        session.rollback()
        logger.exception("Sim order %s checkout failed: %s", order_id, exc)
    finally:
        session.close()


def _run_simulation(params: SimulationRequest) -> None:
    if params.seed is not None:
        random.seed(params.seed)

    session = SessionLocal()
    try:
        simulation_run = models.SimulationRun(
            label=params.label or "ml-data-capture",
            runtime_minutes=params.runtime_minutes,
            status="running",
        )
        session.add(simulation_run)
        session.commit()
        session.refresh(simulation_run)
        run_id = simulation_run.id

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
        end_time = datetime.utcnow() + timedelta(minutes=params.runtime_minutes)

        while datetime.utcnow() < end_time:
            session.refresh(simulation_run)
            if simulation_run.status != "running":
                logger.info("Simulation run %s stopped; ending loop", simulation_run.id)
                break
            table_code = random.choice(available_tables)
            table = _ensure_table(session, table_code)
            order = _create_order(session, table)
            session.commit()

            simulation_run.orders_created = (simulation_run.orders_created or 0) + 1
            session.commit()

            _schedule_processing(order.id, run_id, params)

            if sleep_interval > 0:
                time.sleep(sleep_interval)

        session.refresh(simulation_run)
        if simulation_run.status == "running":
            simulation_run.status = "completed"
        simulation_run.ended_at = datetime.utcnow()
        session.commit()

        session.expire_all()
        inventory_ml.record_simulation_run_snapshots(session, simulation_run=simulation_run)
        session.commit()
    finally:
        session.close()


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_simulation(
    request: SimulationRequest,
    background_tasks: BackgroundTasks,
    admin: models.StaffUser = Depends(security.require_admin_api),
):
    db = SessionLocal()
    try:
        existing = (
            db.query(models.SimulationRun)
            .filter(models.SimulationRun.status == "running")
            .first()
        )
        if existing:
            raise HTTPException(status_code=409, detail="A simulation run is already in progress")
    finally:
        db.close()
    background_tasks.add_task(_run_simulation, request)
    return {"message": "Simulation started", "total_users": int(request.hours * ORDER_RATE_PER_HOUR)}


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_simulation(
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(security.require_admin_api),
):
    db.execute(
        text("TRUNCATE TABLE order_items, transactions, orders, users RESTART IDENTITY CASCADE")
    )
    db.commit()
