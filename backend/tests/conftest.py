"""
Pytest configuration and shared fixtures.

Tests run against a real PostgreSQL test database (`league_caddie_test`).
This avoids SQLite compatibility issues with PostgreSQL-specific types
(UUID, etc.) and ensures tests mirror production behavior.

Requires:
  - PostgreSQL running: docker compose up postgres -d
  - Test DB created once:
      docker compose exec postgres psql -U league_caddie -d league_caddie_dev \
        -c "CREATE DATABASE league_caddie_test;"

Isolation strategy
------------------
Each pytest-xdist worker creates its own PostgreSQL **schema** inside the shared
`league_caddie_test` database (e.g. `test_gw0`, `test_gw1`).  The engine for
that worker sets `search_path` to the worker schema so every table is created
and queried there — workers never touch each other's rows.

Within a worker, tables are TRUNCATED after every test function for a clean
slate.  The schema itself is dropped when the session ends.

When running without xdist (`-n 0` or plain `pytest`) the schema is named
`test_main`.

Performance notes
-----------------
- `client` is session-scoped: the FastAPI app starts once per worker, not once
  per test.  DB isolation is handled by TRUNCATE, not by app teardown.
- BCRYPT_ROUNDS=4 (set in Makefile / CI) cuts bcrypt cost 64× vs the default
  12 rounds.  bcrypt hashes are self-describing so `verify_password` works
  correctly regardless of the cost that was used to create the hash.
"""

import os

# Ensure league creation is unrestricted in tests regardless of local .env settings.
os.environ.setdefault("LEAGUE_CREATION_RESTRICTED", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

BASE_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://league_caddie:league_caddie@localhost:5432/league_caddie_test",
)

from app.database import get_db  # noqa: E402
from app.dependencies import require_active_purchase  # noqa: E402
from app.main import app  # noqa: E402

# Importing Base from app.models (not app.models.base) triggers the __init__.py,
# which imports every model class and registers them all with Base.metadata.
from app.models import Base  # noqa: E402

# ---------------------------------------------------------------------------
# Per-worker schema isolation helpers
# ---------------------------------------------------------------------------


def _worker_schema(worker_id: str) -> str:
    """Return a per-worker PostgreSQL schema name for xdist isolation."""
    return f"test_{worker_id}" if worker_id != "master" else "test_main"


def _make_engine(schema: str):
    """Create an engine whose connections default to `schema` via search_path."""
    return create_engine(
        BASE_TEST_DB_URL,
        # The leading comma keeps 'public' available for extensions / pg_catalog.
        connect_args={"options": f"-csearch_path={schema},public"},
    )


# ---------------------------------------------------------------------------
# Session-scoped fixtures (created once per worker process)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def worker_id(request) -> str:
    """Return the xdist worker ID, or 'master' when running without xdist."""
    return getattr(request.config, "workerinput", {}).get("workerid", "master")


@pytest.fixture(scope="session")
def test_engine(worker_id):
    """
    Session-scoped SQLAlchemy engine pointing at this worker's isolated schema.

    Creates the schema (and all tables within it) at session start; drops the
    schema entirely when the session ends.
    """
    schema = _worker_schema(worker_id)
    eng = _make_engine(schema)

    with eng.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        conn.commit()

    Base.metadata.create_all(bind=eng)
    yield eng

    Base.metadata.drop_all(bind=eng)
    with eng.connect() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        conn.commit()
    eng.dispose()


@pytest.fixture(scope="session")
def session_factory(test_engine):
    """Session factory bound to this worker's isolated engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session")
def client(session_factory):
    """
    FastAPI TestClient — session-scoped so the app starts up once per worker.

    Overrides `get_db` so every request uses the worker's isolated schema.
    Database isolation between test functions is handled by `clean_db` (TRUNCATE).
    """

    def _override_get_db():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    # Bypass the payment gate for all tests — existing tests don't create
    # purchase rows and shouldn't need to.  Dedicated payment-gate tests can
    # remove this override or use their own client fixture.
    def _bypass_purchase():
        return None

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[require_active_purchase] = _bypass_purchase
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Function-scoped fixtures (reset between every test)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_db(test_engine):
    """
    Truncate all tables after every test for a clean slate.

    TRUNCATE ... CASCADE handles FK dependencies. RESTART IDENTITY resets
    auto-increment sequences so IDs don't leak between tests.
    """
    yield
    table_names = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    with test_engine.connect() as conn:
        conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
        conn.commit()


@pytest.fixture
def db(session_factory):
    """Yield a SQLAlchemy session for direct DB access within a test."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Shared auth fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registered_user(client):
    """Register a test user and return the access token."""
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "password123",
            "display_name": "Test User",
        },
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(registered_user):
    """Return an Authorization header dict for the test user."""
    return {"Authorization": f"Bearer {registered_user}"}
