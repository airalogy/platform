"""Add governed Research human executor profiles.

Revision ID: 0024_research_human_executor_profiles
Revises: 0023_research_review_recommendations
Create Date: 2026-09-03 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

from migrations.model_registry import import_models

revision: str = "0024_research_human_executor_profiles"
down_revision: str | None = "0023_research_review_recommendations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = (
    "research_human_executor_profiles",
    "research_human_executor_profile_audits",
)


def _tables(metadata):
    return [metadata.tables[name] for name in TABLE_NAMES]


def upgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    Base.metadata.create_all(bind=bind, tables=_tables(Base.metadata))
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.prevent_research_human_executor_profile_audit_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'research_human_executor_profile_audits is append-only';
        END;
        $$
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS research_human_executor_profile_audits_append_only "
        "ON public.research_human_executor_profile_audits"
    )
    op.execute(
        """
        CREATE TRIGGER research_human_executor_profile_audits_append_only
        BEFORE UPDATE OR DELETE ON public.research_human_executor_profile_audits
        FOR EACH ROW EXECUTE FUNCTION public.prevent_research_human_executor_profile_audit_mutation()
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    op.execute(
        "DROP TRIGGER IF EXISTS research_human_executor_profile_audits_append_only "
        "ON public.research_human_executor_profile_audits"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "public.prevent_research_human_executor_profile_audit_mutation()"
    )
    Base.metadata.drop_all(bind=bind, tables=list(reversed(_tables(Base.metadata))))
