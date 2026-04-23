"""
Database session management.

- Engine is created once at import time from DATABASE_URL in config.
- get_db() is a FastAPI dependency that yields a session per request
  and guarantees rollback on exception + close on exit.
- create_tables() is called at app startup (lifespan) to ensure the
  schema exists without running migrations — safe for local dev and CI.
  Production should use Alembic migrations instead.
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,       # test connections before use (handles DB restarts)
    pool_size=5,
    max_overflow=10,
    echo=settings.DEBUG,      # log all SQL in debug mode
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Base class for all ORM models
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """Yield a DB session; roll back on any exception, always close."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Context manager for use outside request scope (e.g. audit logger)
# ---------------------------------------------------------------------------

@contextmanager
def db_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Schema initialisation (dev / CI only)
# ---------------------------------------------------------------------------

def create_tables() -> None:
    """Create all tables that don't yet exist. Idempotent."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified/created")
    except Exception as e:
        logger.error("Failed to create database tables", extra={"error": str(e)})
        raise


def check_connection() -> bool:
    """Return True if the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection OK", extra={"url": _redact_url(settings.DATABASE_URL)})
        return True
    except Exception as e:
        logger.error("Database connection failed", extra={"error": str(e)})
        return False


def _redact_url(url: str) -> str:
    """Replace password in a DB URL with *** for safe logging."""
    import re
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)
