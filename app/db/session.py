"""Async engine + session factory and the FastAPI DB dependency.

Connection pooling (pool_pre_ping recycles dead connections) is configured here;
the spec requires PostgreSQL connection pooling for the ~50-user target.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_settings = get_settings()

engine = create_async_engine(
    _settings.database_url_async,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Request-scoped session. Commits are explicit in the route/service layer."""
    async with AsyncSessionLocal() as session:
        yield session
