"""Use language-neutral substring search for record contents.

Revision ID: 0005_record_substring_search
Revises: 0004_organizational_units
Create Date: 2026-07-21 00:00:00.000000
"""

from typing import Sequence

from alembic import op

revision: str = "0005_record_substring_search"
down_revision: str | None = "0004_organizational_units"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("DROP INDEX IF EXISTS public.records_search_document_tsv_idx")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS records_search_document_trgm_idx
        ON public.records
        USING gin (
            public.record_search_document(data::jsonb, report) gin_trgm_ops
        )
        WHERE deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.records_search_document_trgm_idx")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS records_search_document_tsv_idx
        ON public.records
        USING gin (
            to_tsvector(
                'english',
                public.record_search_document(data::jsonb, report)
            )
        )
        WHERE deleted_at IS NULL
        """
    )
