"""Database setup (SQLite + SQLAlchemy).

The database file lives in backend/data/inventory.db and is NOT committed to
GitHub. It is created automatically on first run and filled with synthetic data.
Set DATABASE_URL in your environment to use a different database (the tests do).
"""
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

# Reads PROJECT_ROOT/.env if it exists (local development in VSCode).
# On Replit, values come from Replit Secrets instead.
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = BACKEND_DIR / "data"
# as_posix() gives forward slashes, which SQLAlchemy accepts on Windows too
DEFAULT_DATABASE_URL = f"sqlite:///{(DATA_DIR / 'inventory.db').as_posix()}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (SQLite does not store time zones)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_engine(url: str):
    is_sqlite = url.startswith("sqlite")
    if is_sqlite and url == DEFAULT_DATABASE_URL:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        url,
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )

    if is_sqlite:
        # SQLite ignores foreign keys unless this is switched on for each connection.
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI dependency: one database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
