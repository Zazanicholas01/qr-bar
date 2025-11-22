import os
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.engine.url import make_url

from app.core import config

Base = declarative_base()


def _build_database_url() -> str:
    # Prefer explicit URL if provided
    url = config.DATABASE_URL
    if url:
        # If legacy URL points to localhost, rewrite host/port from env to work in-cluster
        try:
            u = make_url(url)
            if u.host in {"127.0.0.1", "localhost"}:
                override_host = config.POSTGRES_HOST
                override_port = config.POSTGRES_PORT
                if override_host:
                    # URL.set returns a new URL with overrides
                    if override_port:
                        u = u.set(host=override_host, port=int(override_port))
                    else:
                        u = u.set(host=override_host)
                    return str(u)
        except Exception:
            # If parsing fails, fall back to the provided URL
            pass
        return url

    # Defaults tuned for Kubernetes services
    user = config.POSTGRES_USER
    password = config.POSTGRES_PASSWORD
    # Use explicit POSTGRES_HOST if set; otherwise fall back to service envs; else default "postgres"
    host = config.POSTGRES_HOST or "postgres"
    port = config.POSTGRES_PORT or "5432"
    database = config.POSTGRES_DB

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
