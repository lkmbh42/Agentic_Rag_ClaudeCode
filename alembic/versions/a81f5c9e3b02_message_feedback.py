"""message_feedback

Revision ID: a81f5c9e3b02
Revises: f3a9c1d24e57
Create Date: 2026-07-04

Phase 4 (spec task 4): 👍/👎 + reason on assistant messages, persisted for
eval mining. One row per (message, user); repeat feedback updates in place.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a81f5c9e3b02'
down_revision: str | None = 'f3a9c1d24e57'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'message_feedback',
        sa.Column('message_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('rating', sa.String(length=8), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['chat_messages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id', 'user_id', name='uq_feedback_message_user'),
    )
    op.create_index('ix_message_feedback_message_id', 'message_feedback', ['message_id'])
    op.create_index('ix_message_feedback_user_id', 'message_feedback', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_message_feedback_user_id', table_name='message_feedback')
    op.drop_index('ix_message_feedback_message_id', table_name='message_feedback')
    op.drop_table('message_feedback')
