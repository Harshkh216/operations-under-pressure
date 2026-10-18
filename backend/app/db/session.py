"""Database engine, session factory, and session dependency.

A single engine is created per process. Each request gets its own session via
``get_db``. Test code overrides the engine via ``set_test_engine`` so tests
run against an isolated SQLite database.
"""

from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

# --- Engine selection -------------------------------------------------------
# SQLite needs special args (check_same_thread, foreign keys) that Postgres
# does not accept, so branch on the URL scheme.

_connect_args: dict[str, object] = {}
if settings.is_sqlite:
    _connect_args = {"check_same_thread": False}

engine: Engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped session. Rolls back on error."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def set_test_engine(new_engine: Engine) -> None:
    """Swap the global engine + session factory (used by the test suite)."""
    global engine, SessionLocal
    engine = new_engine
    SessionLocal.configure(bind=new_engine)


__all__ = ["engine", "SessionLocal", "get_db", "set_test_engine"]
