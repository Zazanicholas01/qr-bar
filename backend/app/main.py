from datetime import datetime, timedelta
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.routers import menu, orders, users
from app.database import Base, get_db, get_engine
from app import models
import os
import socket
import qrcode
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
app.include_router(orders.router, prefix="/api/orders", tags=["Orders"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])


@app.on_event("startup")
def create_tables() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

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

@app.get("/qrcode")
def generate_qrcode():
    ip = get_host_ip()
    port = os.environ.get("FRONTEND_PORT", "3000")
    url = f"http://{ip}:{port}"   # indirizzo frontend React
    qr = qrcode.make(url)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


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
