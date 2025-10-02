from fastapi import FastAPI
from routers import menu, orders

app = FastAPI()

app.include_router(menu.router, prefix="/api/menu", tags=["Menu"])
app.include_router(orders.router, prefix="/api/orders", tags=["Orders"])
