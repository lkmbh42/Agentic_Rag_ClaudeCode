"""Test harness.

- Creates a dedicated `rag_test` database and applies Alembic migrations to it
  (this doubles as the "migrations apply cleanly" DoD check).
- Each test runs against a freshly-truncated schema with a seeded org:
    departments A & B; admin; alice (dept A); bob (dept B);
    collection collA (dept A); collection collB (dept B).
- The app's get_db dependency is overridden to use the test database.

Runs inside the backend image (so app deps are importable) on the compose
network (so `postgres` and `redis` resolve).
"""

from __future__ import annotations

import subprocess
import sys

import psycopg2
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker as sync_sessionmaker

from app.config import get_settings
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models.collection import Collection
from app.models.department import Department
from app.models.enums import Role
from app.models.user import User

_settings = get_settings()

# Pin graph-behavior flags for deterministic tests, independent of the dev .env
# overrides (which disable eval/hallucination and zero the retries for CPU speed).
_settings.hallucination_check_enabled = True
_settings.max_retrieval_retries = 2
_settings.max_generation_retries = 1

TEST_DB = "rag_test"

_SYNC_TEST_URL = (
    f"postgresql+psycopg2://{_settings.postgres_user}:{_settings.postgres_password}"
    f"@{_settings.postgres_host}:{_settings.postgres_port}/{TEST_DB}"
)
_ASYNC_TEST_URL = (
    f"postgresql+asyncpg://{_settings.postgres_user}:{_settings.postgres_password}"
    f"@{_settings.postgres_host}:{_settings.postgres_port}/{TEST_DB}"
)
# Plain libpq URL for the psycopg3 LangGraph checkpointer.
PSYCOPG_TEST_URL = (
    f"postgresql://{_settings.postgres_user}:{_settings.postgres_password}"
    f"@{_settings.postgres_host}:{_settings.postgres_port}/{TEST_DB}"
)

_TABLES = [
    "message_feedback", "audit_logs", "chat_messages", "chat_sessions",
    "permissions", "documents", "collections", "users", "departments",
]

# Known test passwords.
ADMIN_PW = "admin-pass-123"
ALICE_PW = "alice-pass-123"
BOB_PW = "bob-pass-123"


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> None:
    """(Re)create rag_test and run migrations to head."""
    conn = psycopg2.connect(
        host=_settings.postgres_host,
        port=_settings.postgres_port,
        user=_settings.postgres_user,
        password=_settings.postgres_password,
        dbname="postgres",
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (TEST_DB,),
        )
        cur.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}"')
        cur.execute(f'CREATE DATABASE "{TEST_DB}"')
    conn.close()

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", _SYNC_TEST_URL)
    # env.py reads ALEMBIC_DATABASE_URL first.
    import os

    os.environ["ALEMBIC_DATABASE_URL"] = _SYNC_TEST_URL
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(_ASYNC_TEST_URL, poolclass=None)
    # Clean slate before each test.
    async with eng.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE TABLE {', '.join(_TABLES)} RESTART IDENTITY CASCADE")
        )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker(engine):
    return async_sessionmaker(bind=engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def client(sessionmaker):
    async def _get_test_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _get_test_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seed(sessionmaker) -> dict:
    """Seed departments, users, and collections. Returns ids + credentials."""
    async with sessionmaker() as db:
        dept_a = Department(name="Engineering")
        dept_b = Department(name="Finance")
        db.add_all([dept_a, dept_b])
        await db.flush()

        admin = User(email="admin@example.com", hashed_password=hash_password(ADMIN_PW),
                     role=Role.ADMIN, department_id=None)
        alice = User(email="alice@example.com", hashed_password=hash_password(ALICE_PW),
                     role=Role.USER, department_id=dept_a.id)
        bob = User(email="bob@example.com", hashed_password=hash_password(BOB_PW),
                   role=Role.USER, department_id=dept_b.id)
        db.add_all([admin, alice, bob])

        coll_a = Collection(name="Eng Docs", department_id=dept_a.id)
        coll_b = Collection(name="Finance Docs", department_id=dept_b.id)
        db.add_all([coll_a, coll_b])
        await db.flush()

        data = {
            "dept_a": dept_a.id, "dept_b": dept_b.id,
            "admin": {"email": admin.email, "password": ADMIN_PW, "id": admin.id},
            "alice": {"email": alice.email, "password": ALICE_PW, "id": alice.id},
            "bob": {"email": bob.email, "password": BOB_PW, "id": bob.id},
            "coll_a": coll_a.id, "coll_b": coll_b.id,
        }
        await db.commit()
    return data


@pytest_asyncio.fixture
async def login(client):
    """Returns an async helper: login(email, password) -> Authorization headers."""
    async def _login(email: str, password: str) -> dict[str, str]:
        resp = await client.post("/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200, resp.text
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    return _login


# --------------------------------------------------------------------------- #
# Phase 3 (ingestion) fixtures — sync DB + test Qdrant collection + samples
# --------------------------------------------------------------------------- #
_sync_engine = create_engine(_SYNC_TEST_URL, future=True)
_SyncSession = sync_sessionmaker(bind=_sync_engine, expire_on_commit=False)


@pytest.fixture
def sync_session(_migrated_database):
    """Sync session to rag_test for exercising the worker-side indexer."""
    with _SyncSession() as session:
        yield session
        session.rollback()


@pytest.fixture
def test_qindex():
    """A throwaway Qdrant collection, recreated per test for isolation."""
    from app.ingestion.qdrant_index import QdrantIndex

    qi = QdrantIndex(collection="rag_chunks_test")
    if qi.client.collection_exists(qi.collection):
        qi.client.delete_collection(qi.collection)
    qi.ensure_collection()
    yield qi
    if qi.client.collection_exists(qi.collection):
        qi.client.delete_collection(qi.collection)


@pytest.fixture(autouse=True)
def _reset_async_redis():
    """Each test gets its own event loop; the lru-cached async Redis client is
    bound to one loop, so clear it per test (a test-harness concern only — prod
    runs a single uvicorn loop)."""
    from app.core.redis import get_redis

    get_redis.cache_clear()
    yield
    get_redis.cache_clear()


@pytest.fixture
def checkpointer_conninfo(_migrated_database) -> str:
    return PSYCOPG_TEST_URL


@pytest.fixture(scope="session")
def samples_dir(tmp_path_factory) -> str:
    """Generate the sample documents once per test session."""
    out = str(tmp_path_factory.mktemp("samples"))
    subprocess.run([sys.executable, "scripts/make_samples.py", out], check=True)
    return out
