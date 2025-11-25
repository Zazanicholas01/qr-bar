from sqlalchemy import text
from sqlalchemy.engine import Connection


def reset_demo_data(connection: Connection) -> None:
    connection.execute(
        text(
            "TRUNCATE TABLE "
            "inventory_policy_training_logs, "
            "inventory_policy_logs, "
            "supply_orders, "
            "order_items, "
            "transactions, "
            "orders, "
            "email_tokens, "
            "auth_sessions, "
            "users "
            "RESTART IDENTITY CASCADE"
        )
    )
    connection.execute(
        text("DELETE FROM stock_movements WHERE COALESCE(ref_type, '') <> 'seed'")
    )
    connection.execute(
        text(
            "UPDATE stock_levels AS sl "
            "SET qty_on_hand_cached = COALESCE(( "
            "  SELECT SUM(qty_delta) "
            "  FROM stock_movements sm "
            "  WHERE sm.item_id = sl.item_id AND sm.location_id = sl.location_id AND sm.ref_type = 'seed' "
            "), 0), "
            "updated_at = NOW()"
        )
    )
