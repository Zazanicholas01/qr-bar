from __future__ import annotations

import csv
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from app import models
from app.services import minio_storage
from app.core import config


HEADERS = [
    "simulation_run_id",
    "item_id",
    "location_id",
    "event_time",
    "demand_qty",
    "on_hand_before",
    "on_hand_after",
    "inventory_position_before",
    "inventory_position_after",
    "reorder_point",
    "safety_stock",
    "lead_time_days",
    "order_qty_placed",
    "backorder_qty",
    "stockout_flag",
    "threshold_type",
    "threshold_value",
    "threshold_breached_flag",
    "policy_version",
    "source",
    "created_at",
]


def _to_cell(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _rows_for_logs(logs: Iterable[models.InventoryPolicyLog]) -> Iterable[dict]:
    for log in logs:
        yield {
            "simulation_run_id": log.simulation_run_id,
            "item_id": log.item_id,
            "location_id": log.location_id,
            "event_time": _to_cell(log.event_time),
            "demand_qty": _to_cell(log.demand_qty),
            "on_hand_before": _to_cell(log.on_hand_before),
            "on_hand_after": _to_cell(log.on_hand_after),
            "inventory_position_before": _to_cell(log.inventory_position_before),
            "inventory_position_after": _to_cell(log.inventory_position_after),
            "reorder_point": _to_cell(log.reorder_point),
            "safety_stock": _to_cell(log.safety_stock),
            "lead_time_days": _to_cell(log.lead_time_days),
            "order_qty_placed": _to_cell(log.order_qty_placed),
            "backorder_qty": _to_cell(log.backorder_qty),
            "stockout_flag": _to_cell(log.stockout_flag),
            "threshold_type": _to_cell(log.threshold_type),
            "threshold_value": _to_cell(log.threshold_value),
            "threshold_breached_flag": _to_cell(log.threshold_breached_flag),
            "policy_version": _to_cell(log.policy_version),
            "source": _to_cell(log.source),
            "created_at": _to_cell(log.created_at),
        }


def export_inventory_policy_logs_to_minio(db: Session, *, simulation_run_id: int) -> str | None:
    """
    Export inventory_policy_logs for a simulation run to CSV and upload to MinIO.
    Returns the object path (bucket/object) if uploaded, else None.
    """
    logs = (
        db.query(models.InventoryPolicyLog)
        .filter(models.InventoryPolicyLog.simulation_run_id == simulation_run_id)
        .order_by(models.InventoryPolicyLog.event_time.asc(), models.InventoryPolicyLog.id.asc())
        .all()
    )
    # Always produce a CSV, even if empty, so runs are traceable
    tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, newline="", suffix=".csv")
    try:
        writer = csv.DictWriter(tmp, fieldnames=HEADERS)
        writer.writeheader()
        for row in _rows_for_logs(logs):
            writer.writerow(row)
        tmp.flush()

        minio_cfg = minio_storage.get_minio_config()
        client = minio_storage.get_client(minio_cfg)
        object_name = f"inventory_policy_logs/run_{simulation_run_id}.csv"
        return minio_storage.upload_file(
            client,
            bucket=minio_cfg.bucket,
            object_name=object_name,
            file_path=tmp.name,
            content_type="text/csv",
        )
    finally:
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass
