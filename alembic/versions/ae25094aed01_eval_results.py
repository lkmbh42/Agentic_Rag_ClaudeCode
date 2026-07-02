"""eval results

Revision ID: ae25094aed01
Revises: c718d4e33838
Create Date: 2026-06-22 14:45:48.058633

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ae25094aed01'
down_revision: str | None = 'c718d4e33838'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'eval_results',
        sa.Column('request_id', sa.UUID(), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('route', sa.String(length=64), nullable=True),
        sa.Column('cache_hit', sa.Boolean(), nullable=False),
        sa.Column('faithfulness', sa.Float(), nullable=True),
        sa.Column('answer_relevancy', sa.Float(), nullable=True),
        sa.Column('context_relevancy', sa.Float(), nullable=True),
        sa.Column('retrieval_quality', sa.Float(), nullable=True),
        sa.Column('citation_accuracy', sa.Float(), nullable=True),
        sa.Column('only_allowed_documents', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_eval_results')),
    )
    op.create_index(op.f('ix_eval_results_request_id'), 'eval_results', ['request_id'], unique=False)
    # NOTE: LangGraph checkpointer tables are intentionally NOT touched here
    # (excluded via env.py include_object); they are managed by PostgresSaver.setup().


def downgrade() -> None:
    op.drop_index(op.f('ix_eval_results_request_id'), table_name='eval_results')
    op.drop_table('eval_results')
