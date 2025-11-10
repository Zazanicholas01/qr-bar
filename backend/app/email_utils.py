import os
import smtplib
from email.message import EmailMessage


def send_email(to_address: str, subject: str, body: str) -> bool:
    host = os.environ.get("SMTP_HOST") or os.environ.get("SMTP_DEFAULT_HOST")
    port = int(os.environ.get("SMTP_PORT") or os.environ.get("SMTP_DEFAULT_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("SMTP_FROM", username or "noreply@example.com")

    if not host:
        # SMTP not configured; act as no-op in dev
        print(f"[email] (noop) To: {to_address}\nSubject: {subject}\n\n{body}")
        return False

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        if username and password:
            server.login(username, password)
        server.send_message(msg)
    return True
