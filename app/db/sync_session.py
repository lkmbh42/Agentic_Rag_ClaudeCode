"""Synchronous engine/session for the worker-side ingestion pipeline.

Parsing/OCR is CPU-bound and synchronous, so the worker uses a plain sync
SQLAlchemy session rather than the async stack the API uses.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()

sync_engine = create_engine(
    _settings.database_url_sync, pool_pre_ping=True, future=True
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine, expire_on_commit=False, class_=Session
)
