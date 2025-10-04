from datetime import datetime, timedelta
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.routers import menu, orders, tables, users
from app.database import Base, get_db, get_engine
from sqlalchemy import text
from app import models
import os
import socket
import qrcode
import base64
import io

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

frontend_host = os.environ.get("FRONTEND_HOST", "localhost")
frontend_port = os.environ.get("FRONTEND_PORT", "3000")

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

app.include_router(menu.router, prefix="/api/menu", tags=["Menu"])
app.include_router(tables.router, prefix="/api/tables", tags=["Tables"])
app.include_router(orders.router, prefix="/api/orders", tags=["Orders"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])


def _ensure_schema() -> None:
    engine = get_engine()
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
            text(
                "UPDATE users SET table_code = table_id WHERE table_code IS NULL AND table_id IS NOT NULL;"
            )
        )
        connection.execute(
            text(
                "UPDATE orders SET table_code = table_id WHERE table_code IS NULL AND table_id IS NOT NULL;"
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

    Base.metadata.create_all(bind=engine)


@app.on_event("startup")
def on_startup() -> None:
    _ensure_schema()

@app.get("/")
async def root():
    return {"message": "Welcome to the Bar API"}

def get_host_ip():
    """Returns the IP/hostname reachable by clients scanning the QR code."""
    override = os.environ.get("FRONTEND_HOST")
    if override:
        return override

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # dummy connection to extract local address
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip

@app.get("/qrcode", response_class=HTMLResponse)
def generate_qrcodes(db: Session = Depends(get_db)):
    ip = get_host_ip()
    port = os.environ.get("FRONTEND_PORT", "3000")
    base_url = f"http://{ip}:{port}"

    tables = db.query(models.Table).order_by(models.Table.code.asc()).all()

    if not tables:
        default_tables = [models.Table(code=f"table{i}") for i in range(1, 11)]
        db.add_all(default_tables)
        db.commit()
        tables = default_tables

    qrs: list[tuple[str, str, str, str]] = []

    for table in tables:
        table_url = f"{base_url}/table/{table.code}"
        buf = io.BytesIO()
        qrcode.make(table_url).save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        qrs.append((table.code, table.name or table.code, table_url, encoded))

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


@app.get("/admin/orders", response_class=HTMLResponse)
def list_orders_admin(request: Request, db: Session = Depends(get_db)):
    orders = (
        db.query(models.Order)
        .filter(models.Order.status != "closed")
        .order_by(models.Order.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "orders.html",
        {"request": request, "orders": orders},
    )


@app.post("/admin/orders/{order_id}/delete")
def delete_order_admin(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    db.delete(order)
    db.commit()

    return RedirectResponse(url="/admin/orders", status_code=303)


@app.post("/admin/orders/{order_id}/process")
def mark_order_processed(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = "processed"
    db.commit()

    return RedirectResponse(url="/admin/orders", status_code=303)


@app.post("/admin/orders/{order_id}/checkout")
def mark_order_checkout(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = "closed"
    db.commit()

    return RedirectResponse(url="/admin/orders", status_code=303)


@app.get("/admin/orders/closed", response_class=HTMLResponse)
def list_closed_orders(
    request: Request,
    day: str | None = Query(default=None, description="Date in YYYY-MM-DD format"),
    db: Session = Depends(get_db),
):
    try:
        if day:
            target_date = datetime.strptime(day, "%Y-%m-%d")
        else:
            target_date = datetime.utcnow()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

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

    return templates.TemplateResponse(
        "orders_closed.html",
        {
            "request": request,
            "orders": orders,
            "selected_day": selected_day,
        },
    )
