"""audit_action conversation_delete

Revision ID: c3f1a8b52d90
Revises: b7c2e9d41f60
Create Date: 2026-09-25

Add the CONVERSATION_DELETE value to the audit_action enum so deleting a
conversation can be recorded in the audit trail. The enum's labels are the
Python member NAMES (SQLAlchemy's default), i.e. uppercase. PostgreSQL 12+
allows ADD VALUE inside a transaction as long as the value isn't used in the
same one.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3f1a8b52d90'
down_revision: str | None = 'b7c2e9d41f60'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'CONVERSATION_DELETE'")


def downgrade() -> None:
    # PostgreSQL can't remove a value from an enum type; leaving it is harmless.
    pass
