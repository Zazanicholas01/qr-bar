from datetime import datetime, timedelta
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.routers import menu, orders, simulator, tables, users
from app.routers import auth as auth_router
from app.routers import ai
from app.database import Base, get_db, get_engine
from sqlalchemy import text
from app import models, security
from app import inventory as inventory_svc
import os
import socket
import qrcode
import base64
import io

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

frontend_host = os.environ.get("FRONTEND_HOST", "localhost")
frontend_port = os.environ.get("FRONTEND_PORT", "3000")
frontend_public_url = os.environ.get("FRONTEND_PUBLIC_URL")

allowed_origins = {
    f"http://{frontend_host}:{frontend_port}",
    f"https://{frontend_host}:{frontend_port}",
    f"http://{frontend_host}",
    f"https://{frontend_host}",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.include_router(menu.router, prefix="/api/menu", tags=["Menu"])
app.include_router(tables.router, prefix="/api/tables", tags=["Tables"])
app.include_router(orders.router, prefix="/api/orders", tags=["Orders"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(simulator.router, prefix="/api/simulator", tags=["Simulator"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])
app.include_router(auth_router.router, prefix="/api/auth", tags=["Auth"])

PAYMENT_METHODS = [
    "cash",
    "card",
    "mobile",
    "other",
]


def _column_exists(connection, table: str, column: str) -> bool:
    result = connection.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    )
    return result.first() is not None


def _ensure_schema() -> None:
    # Create or migrate schema as needed
    engine = get_engine()
    # Ensure all ORM tables exist before running ALTERs against them
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
        # Migrate existing schema if needed
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
        # Unique email constraint (case-insensitive) via index
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

    # Run again is harmless; kept for idempotency
    Base.metadata.create_all(bind=engine)
    _bootstrap_admin()

    # Seed minimal inventory (items, recipes, and initial stock) if empty
    with engine.begin() as connection:
        # Take an advisory lock to avoid concurrent seeding across replicas
        got_lock = connection.execute(
            text("SELECT pg_try_advisory_lock( hashtextextended('inventory_seed', 0) )")
        ).scalar()
        if not got_lock:
            return
        try:
            count_items = connection.execute(text("SELECT COUNT(*) FROM inventory_items")).scalar() or 0
            if count_items == 0:
                # Ensure default location exists and get its id
                connection.execute(
                    text("INSERT INTO inventory_locations (name, created_at) VALUES ('Default', NOW()) ON CONFLICT (name) DO NOTHING")
                )
                default_loc_id = connection.execute(
                    text("SELECT id FROM inventory_locations WHERE name='Default'")
                ).scalar()

                # Inventory items (sku, name, unit)
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
                ]
                for sku, name, unit in items:
                    connection.execute(
                        text("INSERT INTO inventory_items (sku, name, unit, created_at) VALUES (:sku,:name,:unit, NOW()) ON CONFLICT (sku) DO NOTHING"),
                        {"sku": sku, "name": name, "unit": unit},
                    )

                # Map SKUs to IDs
                sku_to_id = {}
                res = connection.execute(text("SELECT id, sku FROM inventory_items"))
                for row in res:
                    sku_to_id[row[1]] = row[0]

                # Recipes for existing menu product IDs
                recipes = [
                    # product_id, yield_qty, yield_unit
                    (1, 1, "pcs"),   # Espresso
                    (2, 1, "pcs"),   # Espresso Macchiato
                    (3, 1, "pcs"),   # Cappuccino
                    (4, 1, "pcs"),   # Latte Macchiato
                    (5, 1, "pcs"),   # Americano
                    (20, 1, "pcs"),  # Orange juice
                    (21, 1, "pcs"),  # Water still (bottle)
                    (22, 1, "pcs"),  # Water sparkling (bottle)
                    (23, 1, "pcs"),  # Iced tea
                    (40, 1, "pcs"),  # Beer 330ml
                    (41, 1, "pcs"),  # White wine glass
                    (42, 1, "pcs"),  # Red wine glass
                    (60, 1, "pcs"),  # Spritz
                    (61, 1, "pcs"),  # Negroni
                    (80, 1, "pcs"),  # Mojito
                    (81, 1, "pcs"),  # Espresso Martini
                ]
                for pid, yq, yu in recipes:
                    connection.execute(
                        text("INSERT INTO recipes (product_id, yield_qty, yield_unit) VALUES (:pid,:yq,:yu) ON CONFLICT (product_id) DO NOTHING"),
                        {"pid": pid, "yq": yq, "yu": yu},
                    )

                # Recipe components per product (component sku, qty, unit)
                def comp(product_id, sku, qty, unit):
                    return {
                        "recipe_item_id": product_id,
                        "component_item_id": sku_to_id.get(sku),
                        "qty": qty,
                        "unit": unit,
                    }

                comps = []
                # Coffee drinks
                comps += [comp(1, "COFFEE-BEANS", 7, "g")]
                comps += [comp(2, "COFFEE-BEANS", 7, "g"), comp(2, "MILK", 20, "ml")]
                comps += [comp(3, "COFFEE-BEANS", 7, "g"), comp(3, "MILK", 150, "ml")]
                comps += [comp(4, "COFFEE-BEANS", 7, "g"), comp(4, "MILK", 200, "ml")]
                comps += [comp(5, "COFFEE-BEANS", 7, "g")]
                # Soft drinks
                comps += [comp(20, "ORANGE-JUICE", 250, "ml")]
                comps += [comp(21, "WATER-STILL", 500, "ml")]
                comps += [comp(22, "WATER-SPARK", 500, "ml")]
                comps += [comp(23, "ICED-TEA", 330, "ml")]
                # Beer & wine
                comps += [comp(40, "BEER-KEG", 330, "ml")]
                comps += [comp(41, "WINE-WHITE", 150, "ml")]
                comps += [comp(42, "WINE-RED", 150, "ml")]
                # Aperitivi
                comps += [comp(60, "APEROL", 60, "ml"), comp(60, "PROSECCO", 90, "ml"), comp(60, "SODA", 30, "ml"), comp(60, "ICE-CUBE", 3, "pcs"), comp(60, "ORANGE", 0.2, "pcs")]
                comps += [comp(61, "GIN", 30, "ml"), comp(61, "CAMPARI", 30, "ml"), comp(61, "VERMOUTH-ROSSO", 30, "ml"), comp(61, "ICE-CUBE", 3, "pcs"), comp(61, "ORANGE", 0.2, "pcs")]
                # Cocktails
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

                # Seed starting stock via movements (receive)
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
                ]
                for sku, qty, unit in seed_stock:
                    item_id = sku_to_id.get(sku)
                    if not item_id:
                        continue
                    # Ensure stock level row for default location
                    connection.execute(
                        text(
                            "INSERT INTO stock_levels (item_id, location_id, qty_on_hand_cached, updated_at) "
                            "VALUES (:iid, :loc, 0, NOW()) ON CONFLICT (item_id, location_id) DO NOTHING"
                        ),
                        {"iid": item_id, "loc": default_loc_id},
                    )
                    # Insert seed movement if not already present; then update cached qty only if inserted
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
        finally:
            # Release advisory lock
            connection.execute(text("SELECT pg_advisory_unlock( hashtextextended('inventory_seed', 0) )"))


@app.on_event("startup")
def on_startup() -> None:
    _ensure_schema()


@app.get("/")
async def root():
    return {"message": "Welcome to the Bar API"}


def get_host_ip():
    """Returns the IP/hostname reachable by clients scanning the QR code."""

    # Check for explicit override
    override = os.environ.get("FRONTEND_HOST")
    if override:
        return override

    # Attempt to determine local IP address
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # dummy connection to extract local address
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip


def _build_public_base_url(request: Request) -> str:
    """Build a publicly reachable base URL.

    Priority:
    1) FRONTEND_PUBLIC_URL if set
    2) X-Forwarded-* headers or Host header from the current request
    3) NODE_IP (Downward API) or fallback to container-detected IP
    """
    # 1) Explicit override
    if frontend_public_url:
        return frontend_public_url.rstrip("/")

    # 2) Prefer the Host header seen by the client; avoid injecting ports from proxies
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    client_host = request.headers.get("host")
    if client_host:
        return f"{proto}://{client_host}"
    # Fallback to X-Forwarded-Host if Host is unavailable
    xf_host = request.headers.get("x-forwarded-host")
    if xf_host:
        return f"{proto}://{xf_host}"

    # 3) Fall back to node/container IP
    ip = os.environ.get("NODE_IP") or get_host_ip()
    scheme = os.environ.get("FRONTEND_SCHEME", "https")
    port = os.environ.get("FRONTEND_PUBLIC_PORT")
    if not port:
        port = "443" if scheme == "https" else "80"
    if (scheme == "https" and port == "443") or (scheme == "http" and port == "80"):
        return f"{scheme}://{ip}"
    return f"{scheme}://{ip}:{port}"


@app.get("/qrcode", response_class=HTMLResponse)
def generate_qrcodes(request: Request, db: Session = Depends(get_db)):

    # Determine the base URL for the QR codes
    base_url = _build_public_base_url(request)

    # Ensure at least 10 tables exist
    tables = db.query(models.Table).order_by(models.Table.code.asc()).all()

    if not tables:
        default_tables = [models.Table(code=f"table{i}") for i in range(1, 11)]
        db.add_all(default_tables)
        db.commit()
        tables = default_tables

    # Generate QR codes for each table
    qrs: list[tuple[str, str, str, str]] = []

    for table in tables:
        table_url = f"{base_url}/table/{table.code}"
        buf = io.BytesIO()
        qrcode.make(table_url).save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        qrs.append((table.code, table.name or table.code, table_url, encoded))

    # Create simple HTML content to display the QR codes
    html_parts = [
        "<html><head><title>QR Table Codes</title>",
        "<style>body{font-family:Arial;margin:2rem;background:#f5f5f5;}",
        ".grid{display:grid;gap:1.5rem;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));}",
        ".card{background:#fff;border-radius:12px;padding:1rem;box-shadow:0 6px 16px rgba(0,0,0,0.1);text-align:center;}",
        ".card img{max-width:180px;height:auto;margin:0.75rem auto;}",
        ".card h2{margin:0.25rem 0 0;font-size:1.1rem;color:#4e342e;}",
        ".card small{color:#7a6a64;display:block;margin-bottom:0.25rem;}",
        ".card p{font-size:0.85rem;word-break:break-all;color:#444;}",
        "</style></head><body>",
        "<h1>QR code per i tavoli</h1>",
        "<div class='grid'>",
    ]

    for table_code, table_label, table_url, encoded in qrs:
        html_parts.extend(
            [
                "<div class='card'>",
                f"<h2>{table_label}</h2>",
                f"<small>{table_code}</small>",
                f"<img src='data:image/png;base64,{encoded}' alt='QR {table_code}' />",
                f"<p>{table_url}</p>",
                "</div>",
            ]
        )

    html_parts.append("</div></body></html>")

    return "".join(html_parts)


def _bootstrap_admin() -> None:

    # If username or password missing, do nothing
    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    if not username or not password:
        return

    # Hash the password 
    engine = get_engine()
    password_hash = security.hash_password(password)

    # Open a DB connection to check if user already exists
    with engine.begin() as connection:
        existing = connection.execute(
            text("SELECT 1 FROM staff_users WHERE username = :username"),
            {"username": username},
        ).first()
        if existing:
            return
        
        # If not exists, create the admin user
        connection.execute(
            text(
                "INSERT INTO staff_users (username, password_hash, role, created_at) "
                "VALUES (:username, :password_hash, :role, NOW())"
            ),
            {"username": username, "password_hash": password_hash, "role": "admin"},
        )


@app.get("/admin/", response_class=HTMLResponse)
def admin_welcome(request: Request, db: Session = Depends(get_db)):
    """Simple welcome page for staff: link to login or orders if authenticated."""
    admin = security.get_admin_from_request(request, db)
    return templates.TemplateResponse(
        "admin_welcome.html",
        {"request": request, "admin": admin},
    )


@app.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if security.get_admin_from_request(request, db):
        return RedirectResponse(url="/admin/orders", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/admin/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    
    # If wrong credentials, show error
    user = db.query(models.StaffUser).filter(models.StaffUser.username == username).first()
    if not user or not security.verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Credenziali non valide"},
            status_code=400,
        )

    # If correct, set session cookie and redirect to orders page
    response = RedirectResponse(url="/admin/orders", status_code=303)
    security.set_admin_session(response, user)
    return response


@app.post("/admin/logout")
def logout(request: Request):
    response = RedirectResponse(url="/admin/login", status_code=303)
    security.clear_admin_session(response)
    return response


@app.get("/admin/orders", response_class=HTMLResponse)
def list_orders_admin(request: Request, db: Session = Depends(get_db)):
    
    # Session cookie check
    if not security.get_admin_from_request(request, db):
        return RedirectResponse(url="/admin/login", status_code=303)
    
    # List of non-closed orders
    orders = (
        db.query(models.Order)
        .filter(models.Order.status != "closed")
        .order_by(models.Order.created_at.desc())
        .all()
    )

    # Renders orders.html template
    return templates.TemplateResponse(
        "orders.html",
        {
            "request": request,
            "orders": orders,
            "payment_methods": PAYMENT_METHODS,
        },
    )


@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    
    # Renders dashboard.html template
    if not security.get_admin_from_request(request, db):
        return RedirectResponse(url="/admin/login", status_code=303)
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.post("/admin/orders/{order_id}/delete")
def delete_order_admin(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if not security.get_admin_from_request(request, db):
        return RedirectResponse(url="/admin/login", status_code=303)
    
    # Checks whether the order exists
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    # Deletes from DB
    db.delete(order)
    db.commit()

    # Redirects to refresh changes
    return RedirectResponse(url="/admin/orders", status_code=303)


@app.post("/admin/orders/{order_id}/process")
def mark_order_processed(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if not security.get_admin_from_request(request, db):
        return RedirectResponse(url="/admin/login", status_code=303)
    
    # Search for the order
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    # Change status, commit and refresh
    order.status = "processed"
    db.commit()

    return RedirectResponse(url="/admin/orders", status_code=303)


@app.post("/admin/orders/{order_id}/checkout")
def mark_order_checkout(
    order_id: int,
    request: Request,
    payment_method: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        if not security.get_admin_from_request(request, db):
            return RedirectResponse(url="/admin/login", status_code=303)

        # Search for the order
        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")

        # Validate payment method
        method = payment_method.strip().lower()
        if method not in PAYMENT_METHODS:
            raise HTTPException(status_code=400, detail="Unsupported payment method")

        # Mark order as closed and create transaction record on the DB
        order.status = "closed"
        if order.transaction:
            order.transaction.method = method
            order.transaction.amount = order.total_amount
            order.transaction.created_at = datetime.utcnow()
        else:
            transaction = models.Transaction(
                order=order,
                method=method,
                amount=order.total_amount,
            )
            db.add(transaction)

        # Consume inventory based on recipes before committing
        try:
            inventory_svc.consume_stock_for_order(db, order, created_by="checkout")
        except Exception:
            # Fail-safe: do not block checkout if inventory fails; consider logging in real setup
            pass

        db.commit()
    except Exception:
        db.rollback()
        return RedirectResponse(url="/admin/orders", status_code=303)

    return RedirectResponse(url="/admin/orders", status_code=303)


@app.get("/api/dashboard/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(security.require_admin_api),
):
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
    items = [
        {"name": name, "total": float(total)}
        for name, total in item_rows
    ]

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
    payments = [
        {"method": method.capitalize(), "count": count}
        for method, count in payment_rows
    ]

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

    hourly_dates = [
        (now - timedelta(days=offset)).date()
        for offset in reversed(range(7))
    ]
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
    week_windows = [
        current_week_start - timedelta(weeks=offset)
        for offset in reversed(range(8))
    ]

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

    dow_labels = {
        0: "Dom",
        1: "Lun",
        2: "Mar",
        3: "Mer",
        4: "Gio",
        5: "Ven",
        6: "Sab",
    }
    dow_order = [1, 2, 3, 4, 5, 6, 0]
    dow_days = [
        {"index": idx, "label": dow_labels[idx]}
        for idx in dow_order
    ]
    dow_values: dict[str, dict[str, float | int]] = {}
    for row in dow_rows:
        week_start = row["week_start"]
        dow = int(row["dow"])
        key = f"{week_start.isoformat()}|{dow}"
        dow_values[key] = {
            "order_count": int(row["order_count"]),
            "total_amount": float(row["total_amount"] or 0),
        }

    heatmaps = {
        "hourly": {
            "dates": [day.isoformat() for day in hourly_dates],
            "hours": list(range(24)),
            "values": hourly_values,
        },
        "day_of_week": {
            "weeks": [week.isoformat() for week in week_windows],
            "days": dow_days,
            "values": dow_values,
        },
    }

    return {
        "total_amount": float(total_amount or 0),
        "closed_count": closed_count,
        "items": items,
        "payments": payments,
        "heatmaps": heatmaps,
        "generated_at": datetime.utcnow().isoformat(),
    }


@app.get("/admin/orders/closed", response_class=HTMLResponse)
def list_closed_orders(
    request: Request,
    day: str | None = Query(default=None, description="Date in YYYY-MM-DD format"),
    hour: int | None = Query(default=None, ge=0, le=23, description="Optional hour filter 0-23"),
    db: Session = Depends(get_db),
):
    if not security.get_admin_from_request(request, db):
        return RedirectResponse(url="/admin/login", status_code=303)

    # Date parsing or default today
    try:
        if day:
            target_date = datetime.strptime(day, "%Y-%m-%d")
        else:
            target_date = datetime.utcnow()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Set start and end for the selected day or hour window
    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    if hour is not None:
        start = start_of_day + timedelta(hours=hour)
        end = start + timedelta(hours=1)
    else:
        start = start_of_day
        end = start + timedelta(days=1)

    # Query closed orders created between start and end
    orders = (
        db.query(models.Order)
        .filter(
            models.Order.status == "closed",
            models.Order.created_at >= start,
            models.Order.created_at < end,
        )
        .order_by(models.Order.created_at.desc())
        .all()
    )

    selected_day = start.strftime("%Y-%m-%d")

    # Renders orders_closed.html template
    return templates.TemplateResponse(
        "orders_closed.html",
        {
            "request": request,
            "orders": orders,
            "selected_day": selected_day,
        },
    )


@app.get("/admin/inventory", response_class=HTMLResponse)
def admin_inventory(request: Request, db: Session = Depends(get_db)):
    if not security.get_admin_from_request(request, db):
        return RedirectResponse(url="/admin/login", status_code=303)
    # Resolve default location id for display
    default_loc = db.query(models.InventoryLocation).filter(models.InventoryLocation.name == "Default").first()
    default_loc_id = default_loc.id if default_loc else None
    join_cond = (models.StockLevel.item_id == models.InventoryItem.id)
    if default_loc_id is not None:
        join_cond = join_cond & (models.StockLevel.location_id == default_loc_id)
    rows = (
        db.query(models.InventoryItem, models.StockLevel)
        .outerjoin(models.StockLevel, join_cond)
        .order_by(models.InventoryItem.name)
        .all()
    )
    items = [
        {
            "sku": itm.sku,
            "name": itm.name,
            "unit": itm.unit,
            "qty": float((lvl.qty_on_hand_cached if lvl else 0) or 0),
        }
        for itm, lvl in rows
    ]
    return templates.TemplateResponse(
        "inventory.html",
        {"request": request, "items": items},
    )


@app.post("/admin/inventory/adjust")
def admin_inventory_adjust(
    request: Request,
    sku: str = Form(...),
    delta: float = Form(...),
    unit: str = Form("pcs"),
    reason: str = Form("adjust"),
    db: Session = Depends(get_db),
):
    if not security.get_admin_from_request(request, db):
        return RedirectResponse(url="/admin/login", status_code=303)
    item = db.query(models.InventoryItem).filter(models.InventoryItem.sku == sku).first()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    inventory_svc._record_movement(
        db,
        item_id=item.id,
        qty_delta=delta,
        unit=unit or item.unit,
        reason=reason,
        ref_type="admin-adjust",
        ref_id=None,
        created_by="admin",
    )
    db.commit()
    return RedirectResponse(url="/admin/inventory", status_code=303)


# =====================
# Testing helpers (cookie reset from Admin)
# =====================

@app.post("/admin/test/reset-user-session")
def reset_user_session_from_admin(request: Request, db: Session = Depends(get_db)):
    response = RedirectResponse(url="/admin/", status_code=303)
    try:
        security.clear_user_session(response, request, db)
    except Exception:
        pass
    return response


@app.post("/admin/test/reset-all-cookies")
def reset_all_cookies_from_admin(request: Request, db: Session = Depends(get_db)):
    response = RedirectResponse(url="/admin/", status_code=303)
    try:
        security.clear_user_session(response, request, db)
    except Exception:
        pass
    try:
        security.clear_admin_session(response)
    except Exception:
        pass
    return response


# ===================
# Minimal inventory API
# ===================
from pydantic import BaseModel


class InventoryAdjust(BaseModel):
    item_sku: str
    qty_delta: float
    unit: str = "pcs"
    reason: str = "adjust"


@app.get("/api/inventory/levels")
def get_inventory_levels(db: Session = Depends(get_db), admin: models.StaffUser = Depends(security.require_admin_api)):
    rows = (
        db.query(models.StockLevel, models.InventoryItem)
        .join(models.InventoryItem, models.InventoryItem.id == models.StockLevel.item_id)
        .all()
    )
    return [
        {
            "sku": item.sku,
            "name": item.name,
            "qty_on_hand": float(level.qty_on_hand_cached or 0),
            "unit": item.unit,
        }
        for level, item in rows
    ]


@app.post("/api/inventory/adjust")
def adjust_inventory(payload: InventoryAdjust, db: Session = Depends(get_db), admin: models.StaffUser = Depends(security.require_admin_api)):
    item = db.query(models.InventoryItem).filter(models.InventoryItem.sku == payload.item_sku).first()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    inventory_svc._record_movement(
        db,
        item_id=item.id,
        qty_delta=payload.qty_delta,
        unit=payload.unit,
        reason=payload.reason,
        ref_type="adjust",
        ref_id=None,
        created_by="api",
    )
    db.commit()
    return {"ok": True}
