import os
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


def _build_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    user = os.environ.get("POSTGRES_USER", "baradmin")
    password = os.environ.get("POSTGRES_PASSWORD", "barpass")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    database = os.environ.get("POSTGRES_DB", "bardb")

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"


@lru_cache()
def get_engine():
    database_url = _build_database_url()
    return create_engine(database_url, future=True)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
