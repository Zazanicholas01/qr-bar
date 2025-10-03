from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import menu, orders
import os
import socket
import qrcode
from starlette.responses import StreamingResponse
import io

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

app.include_router(menu.router, prefix="/api/menu", tags=["Menu"])
app.include_router(orders.router, prefix="/api/orders", tags=["Orders"])

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
