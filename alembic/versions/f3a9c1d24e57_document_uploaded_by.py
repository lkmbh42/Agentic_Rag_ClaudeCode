"""documents.uploaded_by_id

Revision ID: f3a9c1d24e57
Revises: d91a4b7f02e1
Create Date: 2026-07-04

Phase 3 metadata path (spec task 2): the "author" facet of the metadata intent
needs a first-class uploader on documents. Nullable; existing rows are
backfilled from the audit log (UPLOAD entries carry the acting user).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f3a9c1d24e57'
down_revision: str | None = 'd91a4b7f02e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('uploaded_by_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_documents_uploaded_by_id_users', 'documents', 'users',
        ['uploaded_by_id'], ['id'], ondelete='SET NULL',
    )
    # Backfill from the audit trail: the earliest UPLOAD entry per document.
    op.execute(
        """
        UPDATE documents d SET uploaded_by_id = (
            SELECT a.user_id FROM audit_logs a
            WHERE a.resource_type = 'document'
              AND a.action = 'UPLOAD'
              AND a.resource_id = d.id::text
            ORDER BY a.created_at ASC
            LIMIT 1
        )
        WHERE d.uploaded_by_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint('fk_documents_uploaded_by_id_users', 'documents', type_='foreignkey')
    op.drop_column('documents', 'uploaded_by_id')
