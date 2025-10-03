from fastapi import FastAPI
from app.routers import menu, orders
import socket
import qrcode
from starlette.responses import StreamingResponse
import io

app = FastAPI()

app.include_router(menu.router, prefix="/api/menu", tags=["Menu"])
app.include_router(orders.router, prefix="/api/orders", tags=["Orders"])

@app.get("/")
async def root():
    return {"message": "Welcome to the Bar API"}

def get_host_ip():
    """Ottiene l'IP della macchina host nella LAN"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # connessione dummy
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip

@app.get("/qrcode")
def generate_qrcode():
    ip = get_host_ip()
    url = f"http://{ip}:3000"   # indirizzo frontend React
    qr = qrcode.make(url)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")
