import os
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


def _build_database_url() -> str:
    # Prefer explicit URL if provided
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    # Defaults tuned for Kubernetes services
    user = os.environ.get("POSTGRES_USER", "baradmin")
    password = os.environ.get("POSTGRES_PASSWORD", "barpass")
    # Use explicit POSTGRES_HOST if set; otherwise fall back to service envs; else default "postgres"
    host = os.environ.get(
        "POSTGRES_HOST",
        os.environ.get("POSTGRES_SERVICE_HOST", "postgres"),
    )
    port = os.environ.get("POSTGRES_PORT", os.environ.get("POSTGRES_SERVICE_PORT", "5432"))
    database = os.environ.get("POSTGRES_DB", "bardb")

    # Keep psycopg2 driver by default; works with our image
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"


@lru_cache()
def get_engine():
    database_url = _build_database_url()
    # pool_pre_ping helps recycle stale connections across K8s/network blips
    return create_engine(database_url, future=True, pool_pre_ping=True)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
