"""chat_message_citations

Revision ID: b7c2e9d41f60
Revises: a81f5c9e3b02
Create Date: 2026-09-24

Persist an assistant message's citations (marker, document, page, chunk type,
passage, figure uri) alongside its text. Without this, reopening a past
conversation showed answers with no sources at all — the one thing a user
needs to verify them. Nullable: user messages and pre-existing answers have none.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b7c2e9d41f60'
down_revision: str | None = 'a81f5c9e3b02'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('chat_messages',
                  sa.Column('citations', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('chat_messages', 'citations')
