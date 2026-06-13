"""Shared pytest fixtures for the full test suite.

Sets required environment variables before any ``app.*`` module is imported so
that ``pydantic_settings`` picks up test values when ``Settings()`` is
instantiated at module-import time.
"""

from __future__ import annotations

import os
import time

# --- Set env vars BEFORE any app import ---
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/ai_job_copilot_test",
)
os.environ.setdefault("SESSION_SECRET_KEY", "test-secret-key-for-tests-only-32ch")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
os.environ.setdefault("JOB_SEARCH_PROVIDER", "fixture")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.db.base import Base
from app.db.session import get_db
from app.main import app

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
TEST_USER_EMAIL = "test@example.com"
TEST_USER_PASSWORD = "Sicher!Passwort99"


# ---------------------------------------------------------------------------
# Database engine — created once per session, tables created/dropped once
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_engine():
    """Create a SQLAlchemy engine for the test database.

    :yields: The test engine; drops all tables when the session ends.
    """
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


# ---------------------------------------------------------------------------
# Per-test session with savepoint isolation
# ---------------------------------------------------------------------------

@pytest.fixture
def db(test_engine):
    """Yield a database session isolated via a savepoint.

    Services may call ``session.commit()``; each such call commits to a
    SAVEPOINT.  The outer connection transaction is rolled back at teardown,
    leaving no residual data between tests.

    :param test_engine: Session-scoped SQLAlchemy engine.
    :yields: An isolated :class:`sqlalchemy.orm.Session`.
    """
    with test_engine.connect() as conn:
        conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        conn.rollback()


# ---------------------------------------------------------------------------
# Seeded fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_user(db):
    """Create and return a persisted test user.

    :param db: Function-scoped database session.
    :returns: A :class:`app.models.user.User` instance.
    """
    from app.crud.user import create_user
    from app.schemas.user import UserCreate

    user = create_user(db, UserCreate(email=TEST_USER_EMAIL, password=TEST_USER_PASSWORD))
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_job(db):
    """Create and return a persisted test job.

    :param db: Function-scoped database session.
    :returns: A :class:`app.models.job.Job` instance.
    """
    from app.models.job import Job

    job = Job(
        title="Software Engineer",
        company="Test GmbH",
        external_job_id="ext-001",
        source="test",
    )
    db.add(job)
    db.flush()
    db.commit()
    db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# FastAPI TestClient — with get_db override
# ---------------------------------------------------------------------------

@pytest.fixture
def client(db):
    """Return a TestClient whose ``get_db`` dependency yields the test session.

    :param db: Function-scoped database session.
    :yields: A :class:`starlette.testclient.TestClient`.
    """
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=True, follow_redirects=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(client, test_user):
    """Return a TestClient that has completed a real login flow.

    Exercises the actual ``POST /auth/login`` endpoint so the session cookie
    is set exactly as it would be in production.

    :param client: TestClient with get_db override.
    :param test_user: Seeded user whose credentials are used.
    :yields: The same client, now carrying a valid session cookie.
    """
    response = client.post(
        "/auth/login",
        data={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
    )
    assert response.status_code == 303, (
        f"Login failed (status {response.status_code}): {response.text[:200]}"
    )
    return client
