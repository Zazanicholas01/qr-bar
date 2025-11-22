import smtplib
from email.message import EmailMessage

from app.core import config


def send_email(to_address: str, subject: str, body: str) -> bool:
    host = config.SMTP_HOST
    port = config.SMTP_PORT
    username = config.SMTP_USERNAME
    password = config.SMTP_PASSWORD
    sender = config.SMTP_FROM

    if not host or not username or not password:
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
