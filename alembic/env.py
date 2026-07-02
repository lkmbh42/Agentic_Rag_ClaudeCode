"""Alembic environment.

DB URL resolution order:
  1. ALEMBIC_DATABASE_URL env var  (used by the test harness for the test DB)
  2. settings.database_url_sync     (normal app config)

target_metadata comes from app.models (importing the package registers every
model on Base.metadata), so autogenerate sees the whole schema.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.models import Base  # noqa: F401 - imports register all models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return os.environ.get("ALEMBIC_DATABASE_URL") or get_settings().database_url_sync


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    # LangGraph owns its checkpointer tables (created via PostgresSaver.setup()).
    # Alembic must never manage/drop them.
    if type_ == "table" and name.startswith("checkpoint"):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        include_object=_include_object,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
