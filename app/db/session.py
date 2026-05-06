"""Provide database session management for the application.

Configure the SQLAlchemy engine and session factory using the database URL from
application settings, and expose a FastAPI dependency for injecting per-request
database sessions.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


engine = create_engine(settings.database_url)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for use as a FastAPI dependency.

    Open a new session at the start of each request and ensure it is closed
    after the request completes, regardless of whether an exception occurred.

    :yields: An active SQLAlchemy ``Session`` bound to the configured database.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
