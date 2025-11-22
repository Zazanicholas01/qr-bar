import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.routers import menu, orders, simulator, tables, users
from app.routers import auth as auth_router
from app.routers import ai
from app.api.routers import inventory_api, qrcode as qrcode_router, admin as admin_router, admin_dashboard
from app.db.schema import ensure_schema_and_seed

app = FastAPI()

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

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.include_router(menu.router, prefix="/api/menu", tags=["Menu"])
app.include_router(tables.router, prefix="/api/tables", tags=["Tables"])
app.include_router(orders.router, prefix="/api/orders", tags=["Orders"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(simulator.router, prefix="/api/simulator", tags=["Simulator"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])
app.include_router(auth_router.router, prefix="/api/auth", tags=["Auth"])
app.include_router(qrcode_router.router, tags=["QR"])
app.include_router(inventory_api.router)
app.include_router(admin_router.router)
app.include_router(admin_dashboard.router)


@app.on_event("startup")
def on_startup() -> None:
    ensure_schema_and_seed()


@app.get("/")
async def root():
    return {"message": "Welcome to the Bar API"}
