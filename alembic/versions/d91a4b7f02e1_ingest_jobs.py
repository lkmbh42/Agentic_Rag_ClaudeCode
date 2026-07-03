"""ingest jobs

Revision ID: d91a4b7f02e1
Revises: ae25094aed01
Create Date: 2026-07-03

Phase 2: queue-driven ingestion progress persisted to Postgres (spec task 6).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd91a4b7f02e1'
down_revision: str | None = 'ae25094aed01'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'ingest_jobs',
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.Enum('QUEUED', 'PARSING', 'CAPTIONING', 'INDEXING',
                                    'INDEXED', 'FAILED', name='ingest_status'),
                  nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ingest_jobs_document_id'), 'ingest_jobs', ['document_id'])
    op.create_index(op.f('ix_ingest_jobs_status'), 'ingest_jobs', ['status'])


def downgrade() -> None:
    op.drop_index(op.f('ix_ingest_jobs_status'), table_name='ingest_jobs')
    op.drop_index(op.f('ix_ingest_jobs_document_id'), table_name='ingest_jobs')
    op.drop_table('ingest_jobs')
    sa.Enum(name='ingest_status').drop(op.get_bind(), checkfirst=True)
