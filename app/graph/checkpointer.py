"""Postgres checkpointer for LangGraph (conversation persistence).

LangGraph's PostgresSaver owns its own tables (checkpoints, checkpoint_blobs,
checkpoint_writes) and creates them via .setup(). This is separate from the
Alembic-managed app schema by design — Alembic does not manage LangGraph's
internal tables; `setup()` is idempotent and run at startup.
"""

from __future__ import annotations

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

_settings = get_settings()


def build_checkpointer(conninfo: str | None = None, max_size: int = 10) -> PostgresSaver:
    pool = ConnectionPool(
        conninfo=conninfo or _settings.database_url_psycopg,
        min_size=1,
        max_size=max_size,
        kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
        open=True,
    )
    saver = PostgresSaver(pool)
    saver.setup()  # idempotent: creates checkpoint tables if absent
    return saver
