"""
SQLite storage layer: engine creation, session factory, and migrations.

Uses SQLAlchemy 2 declarative ORM with a single shared engine per process.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from agent.core import config as _config


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def _get_engine():
    global _engine
    if _engine is None:
        _config.settings.ensure_dirs()
        db_url = f"sqlite:///{_config.settings.db_path}"
        _engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            echo=False,
        )

        # Enable WAL mode and foreign-key enforcement for every connection.
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return _engine


def _get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=_get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _SessionLocal


def init_db() -> None:
    """Create all tables if they don't exist (idempotent)."""
    # Import models so Base sees them before create_all.
    import agent.core.artifacts  # noqa: F401
    import agent.core.chat  # noqa: F401

    Base.metadata.create_all(bind=_get_engine())


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a transactional session; commit on clean exit, rollback on error."""
    factory = _get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
