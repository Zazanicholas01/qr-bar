"""Centralized configuration values derived from environment variables."""
import os

# Admin session/cookie configuration
ADMIN_SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY", "change-me")
ADMIN_SESSION_TTL = int(os.environ.get("ADMIN_SESSION_TTL", "86400"))
ADMIN_SESSION_COOKIE = os.environ.get("ADMIN_SESSION_COOKIE", "admin_session")
ADMIN_COOKIE_SECURE = os.environ.get("ADMIN_COOKIE_SECURE", "true").lower() != "false"

# Customer session/cookie configuration
USER_SESSION_COOKIE = os.environ.get("USER_SESSION_COOKIE", "user_session")
USER_COOKIE_SECURE = os.environ.get("USER_COOKIE_SECURE", "true").lower() != "false"
USER_SESSION_TTL = int(os.environ.get("USER_SESSION_TTL", str(7 * 24 * 3600)))

# Frontend/public URLs
FRONTEND_HOST = os.environ.get("FRONTEND_HOST", "localhost")
FRONTEND_PORT = os.environ.get("FRONTEND_PORT", "3000")
FRONTEND_PUBLIC_URL = os.environ.get("FRONTEND_PUBLIC_URL")
FRONTEND_SCHEME = os.environ.get("FRONTEND_SCHEME", "https")
FRONTEND_PUBLIC_PORT = os.environ.get("FRONTEND_PUBLIC_PORT")

# Google auth configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_AUDIENCES_RAW = os.environ.get("GOOGLE_AUDIENCES", "")
GOOGLE_AUDIENCES = {a.strip() for a in GOOGLE_AUDIENCES_RAW.split(",") if a.strip()} if GOOGLE_AUDIENCES_RAW else set()
if GOOGLE_CLIENT_ID:
    GOOGLE_AUDIENCES.add(GOOGLE_CLIENT_ID)
APP_ENV = os.environ.get("APP_ENV", "dev").lower()

# Email/debug configuration
PASSWORD_RESET_TTL = int(os.environ.get("PASSWORD_RESET_TTL", str(3600)))
EMAIL_DEBUG_LINKS = os.environ.get("EMAIL_DEBUG_LINKS", "false").lower() == "true"
APP_BASE_URL = os.environ.get("APP_BASE_URL")
EMAIL_VERIFY_TTL = int(os.environ.get("EMAIL_VERIFY_TTL", str(24 * 3600)))

# SMTP configuration
SMTP_HOST = os.environ.get("SMTP_HOST") or os.environ.get("SMTP_DEFAULT_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT") or os.environ.get("SMTP_DEFAULT_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USERNAME or "noreply@example.com")

# Database configuration
DATABASE_URL = os.environ.get("DATABASE_URL")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST") or os.environ.get("POSTGRES_SERVICE_HOST")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT") or os.environ.get("POSTGRES_SERVICE_PORT")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "baradmin")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "barpass")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "bardb")

# MinIO / object storage configuration
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "changeMe123!")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "inventory-policy-csv")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() == "true"

# Simulator defaults (overridable)
SIM_ORDER_RATE_PER_HOUR = int(os.environ.get("SIM_ORDER_RATE_PER_HOUR", "15"))
SIM_PROCESS_DELAY_MIN = float(os.environ.get("SIM_PROCESS_DELAY_MIN", "1.0"))
SIM_PROCESS_DELAY_MAX = float(os.environ.get("SIM_PROCESS_DELAY_MAX", "3.0"))
SIM_CHECKOUT_DELAY_MIN = float(os.environ.get("SIM_CHECKOUT_DELAY_MIN", "3.0"))
SIM_CHECKOUT_DELAY_MAX = float(os.environ.get("SIM_CHECKOUT_DELAY_MAX", "5.0"))
SIM_RUNTIME_MINUTES = int(os.environ.get("SIM_RUNTIME_MINUTES", "5"))
SIM_TIME_SCALE = float(os.environ.get("SIM_TIME_SCALE", "60.0"))

# Misc environment helpers
NODE_IP = os.environ.get("NODE_IP")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
