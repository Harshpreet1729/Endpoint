"""One SQLAlchemy session per request/task. A session is a database workspace."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def normalize_url(url: str) -> str:
    # Railway's postgres:// URL needs the explicit psycopg 3 driver name.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return url.replace(prefix, "postgresql+psycopg://", 1)
    return url


def make_engine(url: str):
    url = normalize_url(url)
    arguments = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
    database_engine = create_engine(url, connect_args=arguments, pool_pre_ping=True, hide_parameters=True)
    if url.startswith("sqlite"):
        @event.listens_for(database_engine, "connect")
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
    return database_engine


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db
