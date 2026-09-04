"""Add immutable finalized Research Result Package snapshots.

Revision ID: 0035_research_result_package_snapshots
Revises: 0034_research_claim_ai_provenance
Create Date: 2026-09-04 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

from migrations.model_registry import import_models

revision: str = "0035_research_result_package_snapshots"
down_revision: str | None = "0034_research_claim_ai_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = ("research_result_package_snapshots",)


def upgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    Base.metadata.create_all(
        bind=bind,
        tables=[Base.metadata.tables[name] for name in TABLE_NAMES],
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.prevent_research_result_package_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'research_result_package_snapshots is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS research_result_package_snapshots_append_only
        ON public.research_result_package_snapshots
        """
    )
    op.execute(
        """
        CREATE TRIGGER research_result_package_snapshots_append_only
        BEFORE UPDATE OR DELETE ON public.research_result_package_snapshots
        FOR EACH ROW EXECUTE FUNCTION public.prevent_research_result_package_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS research_result_package_snapshots_append_only
        ON public.research_result_package_snapshots
        """
    )
    op.execute(
        "DROP FUNCTION IF EXISTS public.prevent_research_result_package_mutation()"
    )
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    Base.metadata.drop_all(
        bind=bind,
        tables=[Base.metadata.tables[name] for name in reversed(TABLE_NAMES)],
    )
