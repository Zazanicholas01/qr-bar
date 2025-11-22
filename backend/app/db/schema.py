from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from app import security
from app.database import Base, get_engine
from app.core import config


def _column_exists(connection, table: str, column: str) -> bool:
    result = connection.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    )
    return result.first() is not None


def _bootstrap_admin() -> None:
    """Create an admin user if ADMIN_USERNAME/ADMIN_PASSWORD are provided."""
    username = config.ADMIN_USERNAME
    password = config.ADMIN_PASSWORD
    if not username or not password:
        return

    engine = get_engine()
    password_hash = security.hash_password(password)

    with engine.begin() as connection:
        existing = connection.execute(
            text("SELECT 1 FROM staff_users WHERE username = :username"),
            {"username": username},
        ).first()
        if existing:
            return

        connection.execute(
            text(
                "INSERT INTO staff_users (username, password_hash, role, created_at) "
                "VALUES (:username, :password_hash, :role, NOW())"
            ),
            {"username": username, "password_hash": password_hash, "role": "admin"},
        )


def ensure_schema_and_seed() -> None:
    """Create/migrate schema and seed minimal data."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS tables (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(80) UNIQUE NOT NULL,
                    name VARCHAR(120),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        connection.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS table_code VARCHAR(80);")
        )
        connection.execute(
            text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS table_code VARCHAR(80);")
        )
        connection.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(30);")
        )
        connection.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS age INTEGER;")
        )
        connection.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);")
        )
        connection.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP;")
        )
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users (lower(email)) WHERE email IS NOT NULL;")
        )
        if _column_exists(connection, "users", "table_id"):
            connection.execute(
                text(
                    "UPDATE users SET table_code = table_id "
                    "WHERE table_code IS NULL AND table_id IS NOT NULL;"
                )
            )
        if _column_exists(connection, "orders", "table_id"):
            connection.execute(
                text(
                    "UPDATE orders SET table_code = table_id "
                    "WHERE table_code IS NULL AND table_id IS NOT NULL;"
                )
            )
        connection.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS table_id;"))
        connection.execute(text("ALTER TABLE orders DROP COLUMN IF EXISTS table_id;"))
        connection.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS table_ref_id INTEGER;"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS table_ref_id INTEGER;"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS starting_stock_qty NUMERIC(12,3);"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS alert_threshold_qty NUMERIC(12,3);"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS storage_capacity_qty NUMERIC(12,3);"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS holding_cost_per_unit NUMERIC(12,2);"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS stockout_cost_per_unit NUMERIC(12,2);"
            )
        )

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS suppliers (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200) UNIQUE NOT NULL,
                    lead_time_hours INTEGER,
                    contact_email VARCHAR(200),
                    notes VARCHAR(255),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS supplier_products (
                    id SERIAL PRIMARY KEY,
                    supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
                    inventory_item_id INTEGER NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
                    price_per_unit NUMERIC(12,2),
                    unit VARCHAR(16),
                    min_qty NUMERIC(12,3),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_supplier_product UNIQUE (supplier_id, inventory_item_id)
                );
                """
            )
        )
        connection.execute(
            text(
                "ALTER TABLE supplier_products ADD COLUMN IF NOT EXISTS discount_pct NUMERIC(5,2);"
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS supply_orders (
                    id SERIAL PRIMARY KEY,
                    inventory_item_id INTEGER REFERENCES inventory_items(id) ON DELETE SET NULL,
                    supplier_id INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
                    state VARCHAR(24) NOT NULL DEFAULT 'alert',
                    suggested_qty NUMERIC(12,3) NOT NULL,
                    unit VARCHAR(16) NOT NULL DEFAULT 'pcs',
                    price_per_unit NUMERIC(12,2),
                    total_price NUMERIC(12,2),
                    sla_hours NUMERIC(8,2),
                    alert_triggered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    acknowledged_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        connection.execute(
            text("ALTER TABLE supply_orders ADD COLUMN IF NOT EXISTS fulfilled_at TIMESTAMP;")
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS simulation_runs (
                    id SERIAL PRIMARY KEY,
                    label VARCHAR(120),
                    status VARCHAR(24) NOT NULL DEFAULT 'running',
                    runtime_minutes INTEGER NOT NULL DEFAULT 30,
                    orders_created INTEGER NOT NULL DEFAULT 0,
                    orders_closed INTEGER NOT NULL DEFAULT 0,
                    notes VARCHAR(255),
                    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP
                );
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS inventory_policy_training_logs (
                    id SERIAL PRIMARY KEY,
                    item_id INTEGER REFERENCES inventory_items(id) ON DELETE SET NULL,
                    supply_order_id INTEGER REFERENCES supply_orders(id) ON DELETE SET NULL,
                    simulation_run_id INTEGER REFERENCES simulation_runs(id) ON DELETE SET NULL,
                    context_features JSONB NOT NULL,
                    decision_snapshot JSONB NOT NULL,
                    outcome_snapshot JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        codes = set()
        result = connection.execute(
            text("SELECT DISTINCT table_code FROM orders WHERE table_code IS NOT NULL")
        )
        codes.update(row[0] for row in result if row[0])
        result = connection.execute(
            text("SELECT DISTINCT table_code FROM users WHERE table_code IS NOT NULL")
        )
        codes.update(row[0] for row in result if row[0])

        for code in codes:
            res = connection.execute(
                text(
                    "INSERT INTO tables (code, created_at) VALUES (:code, CURRENT_TIMESTAMP) "
                    "ON CONFLICT (code) DO NOTHING RETURNING id"
                ),
                {"code": code},
            )
            table_id = res.scalar()
            if table_id is None:
                table_id = connection.execute(
                    text("SELECT id FROM tables WHERE code = :code"), {"code": code}
                ).scalar()

            if table_id is not None:
                connection.execute(
                    text(
                        "UPDATE orders SET table_ref_id = :tid WHERE table_code = :code AND (table_ref_id IS NULL OR table_ref_id <> :tid)"
                    ),
                    {"tid": table_id, "code": code},
                )
                connection.execute(
                    text(
                        "UPDATE users SET table_ref_id = :tid WHERE table_code = :code AND (table_ref_id IS NULL OR table_ref_id <> :tid)"
                    ),
                    {"tid": table_id, "code": code},
                )

    Base.metadata.create_all(bind=engine)
    _bootstrap_admin()

    with engine.begin() as connection:
        got_lock = connection.execute(
            text("SELECT pg_try_advisory_lock( hashtextextended('inventory_seed', 0) )")
        ).scalar()
        if not got_lock:
            return
        try:
            count_items = connection.execute(text("SELECT COUNT(*) FROM inventory_items")).scalar() or 0
            if count_items == 0:
                connection.execute(
                    text("INSERT INTO inventory_locations (name, created_at) VALUES ('Default', NOW()) ON CONFLICT (name) DO NOTHING")
                )
                default_loc_id = connection.execute(
                    text("SELECT id FROM inventory_locations WHERE name='Default'")
                ).scalar()

                items = [
                    ("COFFEE-BEANS", "Coffee beans", "g"),
                    ("MILK", "Milk", "ml"),
                    ("ORANGE-JUICE", "Orange juice", "ml"),
                    ("WATER-STILL", "Water (still)", "ml"),
                    ("WATER-SPARK", "Water (sparkling)", "ml"),
                    ("ICED-TEA", "Iced tea", "ml"),
                    ("BEER-KEG", "Beer (keg)", "ml"),
                    ("WINE-WHITE", "Wine (white)", "ml"),
                    ("WINE-RED", "Wine (red)", "ml"),
                    ("APEROL", "Aperol", "ml"),
                    ("PROSECCO", "Prosecco", "ml"),
                    ("SODA", "Soda water", "ml"),
                    ("GIN", "Gin", "ml"),
                    ("CAMPARI", "Campari", "ml"),
                    ("VERMOUTH-ROSSO", "Vermouth Rosso", "ml"),
                    ("RUM", "Rum", "ml"),
                    ("VODKA", "Vodka", "ml"),
                    ("COFFEE-LIQUEUR", "Coffee liqueur", "ml"),
                    ("LIME", "Lime", "pcs"),
                    ("MINT", "Mint", "g"),
                    ("SUGAR-SYRUP", "Sugar syrup", "ml"),
                    ("ICE-CUBE", "Ice cube", "pcs"),
                    ("ORANGE", "Orange", "pcs"),
                    ("COLD-BREW-CONCENTRATE", "Cold Brew Concentrate", "gal"),
                    ("CUP-16OZ-COMPOST", "Compostable Cold Cups 16oz", "sleeve"),
                ]
                for sku, name, unit in items:
                    connection.execute(
                        text("INSERT INTO inventory_items (sku, name, unit, created_at) VALUES (:sku,:name,:unit, NOW()) ON CONFLICT (sku) DO NOTHING"),
                        {"sku": sku, "name": name, "unit": unit},
                    )

                sku_to_id = {}
                res = connection.execute(text("SELECT id, sku FROM inventory_items"))
                for row in res:
                    sku_to_id[row[1]] = row[0]

                par_targets = [
                    ("COLD-BREW-CONCENTRATE", 30, 20),
                    ("CUP-16OZ-COMPOST", 320, 220),
                    ("COFFEE-BEANS", 60, 30),
                ]
                for sku, par_level, reorder_point in par_targets:
                    connection.execute(
                        text(
                            "UPDATE inventory_items SET par_level = :par, reorder_point = :reorder WHERE sku = :sku"
                        ),
                        {"par": par_level, "reorder": reorder_point, "sku": sku},
                    )

                def comp(product_id, sku, qty, unit):
                    return {
                        "recipe_item_id": product_id,
                        "component_item_id": sku_to_id.get(sku),
                        "qty": qty,
                        "unit": unit,
                    }

                recipes = [
                    (1, 1, "pcs"),
                    (2, 1, "pcs"),
                    (3, 1, "pcs"),
                    (4, 1, "pcs"),
                    (5, 1, "pcs"),
                    (20, 1, "pcs"),
                    (21, 1, "pcs"),
                    (22, 1, "pcs"),
                    (23, 1, "pcs"),
                    (40, 1, "pcs"),
                    (41, 1, "pcs"),
                    (42, 1, "pcs"),
                    (60, 1, "pcs"),
                    (61, 1, "pcs"),
                    (80, 1, "pcs"),
                    (81, 1, "pcs"),
                ]
                for pid, yq, yu in recipes:
                    connection.execute(
                        text("INSERT INTO recipes (product_id, yield_qty, yield_unit) VALUES (:pid,:yq,:yu) ON CONFLICT (product_id) DO NOTHING"),
                        {"pid": pid, "yq": yq, "yu": yu},
                    )

                comps = []
                comps += [comp(1, "COFFEE-BEANS", 7, "g")]
                comps += [comp(2, "COFFEE-BEANS", 7, "g"), comp(2, "MILK", 20, "ml")]
                comps += [comp(3, "COFFEE-BEANS", 7, "g"), comp(3, "MILK", 150, "ml")]
                comps += [comp(4, "COFFEE-BEANS", 7, "g"), comp(4, "MILK", 200, "ml")]
                comps += [comp(5, "COFFEE-BEANS", 7, "g")]
                comps += [comp(20, "ORANGE-JUICE", 250, "ml")]
                comps += [comp(21, "WATER-STILL", 500, "ml")]
                comps += [comp(22, "WATER-SPARK", 500, "ml")]
                comps += [comp(23, "ICED-TEA", 330, "ml")]
                comps += [comp(40, "BEER-KEG", 330, "ml")]
                comps += [comp(41, "WINE-WHITE", 150, "ml")]
                comps += [comp(42, "WINE-RED", 150, "ml")]
                comps += [comp(60, "APEROL", 60, "ml"), comp(60, "PROSECCO", 90, "ml"), comp(60, "SODA", 30, "ml"), comp(60, "ICE-CUBE", 3, "pcs"), comp(60, "ORANGE", 0.2, "pcs")]
                comps += [comp(61, "GIN", 30, "ml"), comp(61, "CAMPARI", 30, "ml"), comp(61, "VERMOUTH-ROSSO", 30, "ml"), comp(61, "ICE-CUBE", 3, "pcs"), comp(61, "ORANGE", 0.2, "pcs")]
                comps += [comp(80, "RUM", 50, "ml"), comp(80, "SODA", 100, "ml"), comp(80, "LIME", 0.5, "pcs"), comp(80, "MINT", 3, "g"), comp(80, "SUGAR-SYRUP", 10, "ml"), comp(80, "ICE-CUBE", 4, "pcs")]
                comps += [comp(81, "VODKA", 40, "ml"), comp(81, "COFFEE-LIQUEUR", 20, "ml"), comp(81, "COFFEE-BEANS", 7, "g"), comp(81, "ICE-CUBE", 3, "pcs")]

                for c in comps:
                    if not c["component_item_id"]:
                        continue
                    connection.execute(
                        text(
                            "INSERT INTO recipe_components (recipe_item_id, component_item_id, qty_per_yield, unit) "
                            "VALUES (:rid,:cid,:qty,:unit)"
                        ),
                        {"rid": c["recipe_item_id"], "cid": c["component_item_id"], "qty": c["qty"], "unit": c["unit"]},
                    )

                seed_stock = [
                    ("COFFEE-BEANS", 5000, "g"),
                    ("MILK", 20000, "ml"),
                    ("ORANGE-JUICE", 5000, "ml"),
                    ("WATER-STILL", 20000, "ml"),
                    ("WATER-SPARK", 20000, "ml"),
                    ("ICED-TEA", 5000, "ml"),
                    ("BEER-KEG", 50000, "ml"),
                    ("WINE-WHITE", 10000, "ml"),
                    ("WINE-RED", 10000, "ml"),
                    ("APEROL", 5000, "ml"),
                    ("PROSECCO", 10000, "ml"),
                    ("SODA", 20000, "ml"),
                    ("GIN", 5000, "ml"),
                    ("CAMPARI", 5000, "ml"),
                    ("VERMOUTH-ROSSO", 5000, "ml"),
                    ("RUM", 5000, "ml"),
                    ("VODKA", 5000, "ml"),
                    ("COFFEE-LIQUEUR", 3000, "ml"),
                    ("LIME", 50, "pcs"),
                    ("MINT", 500, "g"),
                    ("SUGAR-SYRUP", 3000, "ml"),
                    ("ICE-CUBE", 1000, "pcs"),
                    ("ORANGE", 50, "pcs"),
                    ("COLD-BREW-CONCENTRATE", 18, "gal"),
                    ("CUP-16OZ-COMPOST", 180, "sleeve"),
                ]
                for sku, qty, unit in seed_stock:
                    item_id = sku_to_id.get(sku)
                    if not item_id:
                        continue
                    connection.execute(
                        text(
                            "INSERT INTO stock_levels (item_id, location_id, qty_on_hand_cached, updated_at) "
                            "VALUES (:iid, :loc, 0, NOW()) ON CONFLICT (item_id, location_id) DO NOTHING"
                        ),
                        {"iid": item_id, "loc": default_loc_id},
                    )
                    connection.execute(
                        text(
                            "WITH ins AS (\n"
                            "  INSERT INTO stock_movements (item_id, location_id, qty_delta, unit, reason, ref_type, ref_id, occurred_at)\n"
                            "  VALUES (:iid, :loc, :q, :u, 'receive', 'seed', :rid, NOW())\n"
                            "  ON CONFLICT ON CONSTRAINT uq_movement_idem DO NOTHING\n"
                            "  RETURNING 1\n"
                            ")\n"
                            "UPDATE stock_levels SET qty_on_hand_cached = COALESCE(qty_on_hand_cached,0) + :q, updated_at = NOW()\n"
                            "WHERE item_id = :iid AND location_id = :loc AND EXISTS (SELECT 1 FROM ins)"
                        ),
                        {"iid": item_id, "loc": default_loc_id, "q": qty, "u": unit, "rid": item_id},
                    )

                threshold_ratio = Decimal("0.2")
                for sku, qty, _ in seed_stock:
                    qty_decimal = Decimal(str(qty))
                    threshold_qty = qty_decimal * threshold_ratio
                    connection.execute(
                        text(
                            "UPDATE inventory_items "
                            "SET starting_stock_qty = COALESCE(starting_stock_qty, :start_qty), "
                            "alert_threshold_qty = COALESCE(alert_threshold_qty, :threshold) "
                            "WHERE sku = :sku"
                        ),
                        {
                            "start_qty": qty_decimal,
                            "threshold": threshold_qty,
                            "sku": sku,
                        },
                    )

            sku_to_id = {
                row[1]: row[0]
                for row in connection.execute(text("SELECT id, sku FROM inventory_items"))
            }

            connection.execute(
                text(
                    """
                    WITH initial AS (
                        SELECT item_id, SUM(qty_delta) AS qty
                        FROM stock_movements
                        WHERE ref_type = 'seed'
                        GROUP BY item_id
                    )
                    UPDATE inventory_items ii
                    SET starting_stock_qty = COALESCE(ii.starting_stock_qty, initial.qty),
                        alert_threshold_qty = COALESCE(ii.alert_threshold_qty, initial.qty * 0.2)
                    FROM initial
                    WHERE ii.id = initial.item_id
                    """
                )
            )

            existing_suppliers = connection.execute(text("SELECT COUNT(*) FROM suppliers")).scalar() or 0
            if existing_suppliers == 0:
                suppliers_seed = [
                    ("North Coast Roasters", 48, "roasters@northcoast.example", "Tostatori artigianali · focus cold brew"),
                    ("Summit Paper Co.", 24, "ops@summitpaper.example", "Packaging compostabile locale"),
                    ("Harvest Dairies", 72, "sales@harvestdairies.example", "Forniamo latte fresco e alternative vegetali"),
                ]
                for name, lead_hours, email, notes in suppliers_seed:
                    connection.execute(
                        text(
                            "INSERT INTO suppliers (name, lead_time_hours, contact_email, notes, created_at) "
                            "VALUES (:name,:lead,:email,:notes, NOW()) "
                            "ON CONFLICT (name) DO UPDATE SET lead_time_hours = EXCLUDED.lead_time_hours, "
                            "contact_email = EXCLUDED.contact_email, notes = EXCLUDED.notes"
                        ),
                        {"name": name, "lead": lead_hours, "email": email, "notes": notes},
                    )

            supplier_ids = {
                row[1]: row[0]
                for row in connection.execute(text("SELECT id, name FROM suppliers"))
            }

            existing_supplier_products = connection.execute(text("SELECT COUNT(*) FROM supplier_products")).scalar() or 0
            if existing_supplier_products == 0:
                supplier_products_seed = [
                    ("North Coast Roasters", "COLD-BREW-CONCENTRATE", 42.00, "box", 6),
                    ("North Coast Roasters", "COFFEE-BEANS", 22.50, "kg", 2),
                    ("Summit Paper Co.", "CUP-16OZ-COMPOST", 6.80, "sleeve", 50),
                    ("Summit Paper Co.", "ORANGE", 18.00, "crate", 1),
                    ("Harvest Dairies", "MILK", 1.45, "L", 48),
                ]
                for supplier_name, sku, price, unit_name, min_qty in supplier_products_seed:
                    supplier_id = supplier_ids.get(supplier_name)
                    item_id = sku_to_id.get(sku)
                    if not supplier_id or not item_id:
                        continue
                    connection.execute(
                        text(
                            "INSERT INTO supplier_products (supplier_id, inventory_item_id, price_per_unit, unit, min_qty, created_at) "
                            "VALUES (:sid,:item,:price,:unit,:min, NOW()) "
                            "ON CONFLICT (supplier_id, inventory_item_id) DO UPDATE "
                            "SET price_per_unit = EXCLUDED.price_per_unit, unit = EXCLUDED.unit, min_qty = EXCLUDED.min_qty"
                        ),
                        {"sid": supplier_id, "item": item_id, "price": price, "unit": unit_name, "min": min_qty},
                    )

            existing_supply_orders = connection.execute(text("SELECT COUNT(*) FROM supply_orders")).scalar() or 0
            if existing_supply_orders == 0:
                cup_item_id = sku_to_id.get("CUP-16OZ-COMPOST")
                summit_id = supplier_ids.get("Summit Paper Co.")
                if cup_item_id and summit_id:
                    alert_dt = datetime.utcnow() - timedelta(hours=3)
                    ack_dt = alert_dt + timedelta(hours=1)
                    qty = Decimal("220")
                    price = Decimal("6.80")
                    total = price * qty
                    connection.execute(
                        text(
                            "INSERT INTO supply_orders (inventory_item_id, supplier_id, state, suggested_qty, unit, "
                            "price_per_unit, total_price, sla_hours, alert_triggered_at, acknowledged_at, created_at) "
                            "VALUES (:item,:supplier,'processed',:qty,'sleeve',:price,:total,8,:alert,:ack,:created)"
                        ),
                        {
                            "item": cup_item_id,
                            "supplier": summit_id,
                            "qty": qty,
                            "price": price,
                            "total": total,
                            "alert": alert_dt,
                            "ack": ack_dt,
                            "created": alert_dt,
                        },
                    )
                cb_item_id = sku_to_id.get("COLD-BREW-CONCENTRATE")
                ncr_id = supplier_ids.get("North Coast Roasters")
                if cb_item_id and ncr_id:
                    alert_dt = datetime.utcnow() - timedelta(hours=1, minutes=30)
                    qty = Decimal("12")
                    price = Decimal("42.00")
                    total = price * qty
                    connection.execute(
                        text(
                            "INSERT INTO supply_orders (inventory_item_id, supplier_id, state, suggested_qty, unit, "
                            "price_per_unit, total_price, sla_hours, alert_triggered_at, created_at) "
                            "VALUES (:item,:supplier,'alert',:qty,'box',:price,:total,12,:alert,:alert)"
                        ),
                        {
                            "item": cb_item_id,
                            "supplier": ncr_id,
                            "qty": qty,
                            "price": price,
                            "total": total,
                            "alert": alert_dt,
                        },
                    )
        finally:
            connection.execute(text("SELECT pg_advisory_unlock( hashtextextended('inventory_seed', 0) )"))
