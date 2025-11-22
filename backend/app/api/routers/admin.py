from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import models, security, inventory as inventory_svc
from app.database import get_db, get_engine
from app.api.routers import simulator
from app.core.constants import PAYMENT_METHODS
from app.api import deps
from app.services import orders as orders_service
from app.services import reset as reset_service

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/admin/", response_class=HTMLResponse)
def admin_welcome(request: Request, db: Session = Depends(get_db), admin: models.StaffUser = Depends(deps.require_admin)):
    reset_status = request.query_params.get("reset")
    sim_status = request.query_params.get("sim")
    latest_run = db.query(models.SimulationRun).order_by(models.SimulationRun.started_at.desc()).first()
    active_run = db.query(models.SimulationRun).filter(models.SimulationRun.status == "running").first()
    return templates.TemplateResponse(
        "admin_welcome.html",
        {
            "request": request,
            "admin": admin,
            "reset_status": reset_status,
            "simulation_state": {
                "latest": latest_run,
                "active": active_run,
                "is_running": bool(active_run),
                "status": sim_status,
            },
        },
    )


@router.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if security.get_admin_from_request(request, db):
        return RedirectResponse(url="/admin/orders", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/admin/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(models.StaffUser).filter(models.StaffUser.username == username).first()
    if not user or not security.verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Credenziali non valide"},
            status_code=400,
        )

    response = RedirectResponse(url="/admin/orders", status_code=303)
    security.set_admin_session(response, user)
    return response


@router.post("/admin/logout")
def logout(request: Request):
    response = RedirectResponse(url="/admin/login", status_code=303)
    security.clear_admin_session(response)
    return response


@router.post("/admin/simulator/start")
def start_admin_simulation(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(deps.require_admin),
):

    running = db.query(models.SimulationRun).filter(models.SimulationRun.status == "running").first()
    if running:
        return RedirectResponse(url="/admin/?sim=running", status_code=303)

    payload = simulator.SimulationRequest(label="admin-panel-run")
    background_tasks.add_task(simulator._run_simulation, payload)
    return RedirectResponse(url="/admin/?sim=started", status_code=303)


@router.post("/admin/simulator/stop")
def stop_admin_simulation(
    request: Request,
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(deps.require_admin),
):

    running = db.query(models.SimulationRun).filter(models.SimulationRun.status == "running").first()
    if not running:
        return RedirectResponse(url="/admin/?sim=none", status_code=303)

    running.status = "stopped"
    running.ended_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(url="/admin/?sim=stopped", status_code=303)


@router.get("/admin/orders", response_class=HTMLResponse)
def list_orders_admin(request: Request, db: Session = Depends(get_db), admin: models.StaffUser = Depends(deps.require_admin)):

    orders = (
        db.query(models.Order)
        .filter(models.Order.status != "closed")
        .order_by(models.Order.created_at.desc())
        .all()
    )

    return templates.TemplateResponse(
        "orders.html",
        {
            "request": request,
            "orders": orders,
            "payment_methods": PAYMENT_METHODS,
        },
    )


@router.post("/admin/orders/{order_id}/delete")
def delete_order_admin(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(deps.require_admin),
):
    try:
        orders_service.delete_order(db, order_id)
        db.commit()
    except LookupError:
        raise HTTPException(status_code=404, detail="Order not found")
    return RedirectResponse(url="/admin/orders", status_code=303)


@router.post("/admin/orders/{order_id}/process")
def mark_order_processed(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(deps.require_admin),
):
    try:
        orders_service.process_order(db, order_id)
        db.commit()
    except LookupError:
        raise HTTPException(status_code=404, detail="Order not found")
    return RedirectResponse(url="/admin/orders", status_code=303)


@router.post("/admin/orders/{order_id}/checkout")
def mark_order_checkout(
    order_id: int,
    request: Request,
    payment_method: str = Form(...),
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(deps.require_admin),
):
    try:
        orders_service.checkout_order(
            db,
            order_id,
            payment_method,
            consume_inventory=True,
            created_by="checkout",
        )
        db.commit()
    except LookupError:
        db.rollback()
        raise HTTPException(status_code=404, detail="Order not found")
    except ValueError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Unsupported payment method")
    except Exception:
        db.rollback()
        return RedirectResponse(url="/admin/orders", status_code=303)

    return RedirectResponse(url="/admin/orders", status_code=303)


@router.post("/admin/test/reset-user-session")
def reset_user_session_from_admin(request: Request, db: Session = Depends(get_db), admin: models.StaffUser = Depends(deps.require_admin)):
    response = RedirectResponse(url="/admin/", status_code=303)
    try:
        security.clear_user_session(response, request, db)
    except Exception:
        pass
    return response


@router.post("/admin/test/reset-all-cookies")
def reset_all_cookies_from_admin(request: Request, db: Session = Depends(get_db), admin: models.StaffUser = Depends(deps.require_admin)):
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


@router.post("/admin/test/revoke-all-user-sessions")
def revoke_all_user_sessions(request: Request, db: Session = Depends(get_db), admin: models.StaffUser = Depends(deps.require_admin)):
    response = RedirectResponse(url="/admin/", status_code=303)
    try:
        db.query(models.AuthSession).delete()
        db.commit()
    except Exception:
        db.rollback()
    return response


@router.post("/admin/test/reset-demo-data")
def reset_demo_data(
    request: Request,
    db: Session = Depends(get_db),
    admin: models.StaffUser = Depends(deps.require_admin),
):

    engine = get_engine()
    with engine.begin() as connection:
        reset_service.reset_demo_data(connection)

    return RedirectResponse(url="/admin/?reset=success", status_code=303)
