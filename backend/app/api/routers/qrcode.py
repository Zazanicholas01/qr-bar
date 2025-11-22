import base64
import io

import qrcode
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import models
from app.core.urls import build_public_base_url
from app.database import get_db

router = APIRouter()


@router.get("/qrcode", response_class=HTMLResponse)
def generate_qrcodes(request: Request, db: Session = Depends(get_db)):
    base_url = build_public_base_url(request)

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
