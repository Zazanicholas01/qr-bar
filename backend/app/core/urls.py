import socket
from fastapi import Request

from app.core import config


def get_host_ip() -> str:
    """Return an IP/hostname reachable by clients scanning the QR code."""
    if config.FRONTEND_HOST:
        return config.FRONTEND_HOST

    # Use a dummy UDP socket to discover local IP without sending data
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
    finally:
        sock.close()
    return ip


def build_public_base_url(request: Request) -> str:
    """Build a publicly reachable base URL.

    Priority:
    1) FRONTEND_PUBLIC_URL if set
    2) X-Forwarded-* headers or Host header from the current request
    3) NODE_IP (Downward API) or fallback to container-detected IP
    """
    if config.FRONTEND_PUBLIC_URL:
        return config.FRONTEND_PUBLIC_URL.rstrip("/")

    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    client_host = request.headers.get("host")
    if client_host:
        return f"{proto}://{client_host}"

    xf_host = request.headers.get("x-forwarded-host")
    if xf_host:
        return f"{proto}://{xf_host}"

    ip = config.NODE_IP or get_host_ip()
    scheme = config.FRONTEND_SCHEME
    port = config.FRONTEND_PUBLIC_PORT
    if not port:
        port = "443" if scheme == "https" else "80"
    if (scheme == "https" and port == "443") or (scheme == "http" and port == "80"):
        return f"{scheme}://{ip}"
    return f"{scheme}://{ip}:{port}"
