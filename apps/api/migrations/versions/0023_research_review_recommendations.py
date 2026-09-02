"""Add immutable independent Research review recommendations.

Revision ID: 0023_research_review_recommendations
Revises: 0022_protocol_improvement_ai_provenance
Create Date: 2026-09-03 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

from migrations.model_registry import import_models

revision: str = "0023_research_review_recommendations"
down_revision: str | None = "0022_protocol_improvement_ai_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = ("research_review_recommendations",)


def upgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    Base.metadata.tables[TABLE_NAMES[0]].create(bind=bind, checkfirst=True)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.prevent_research_review_recommendation_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'research_review_recommendations is append-only';
        END;
        $$
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS research_review_recommendations_append_only "
        "ON public.research_review_recommendations"
    )
    op.execute(
        """
        CREATE TRIGGER research_review_recommendations_append_only
        BEFORE UPDATE OR DELETE ON public.research_review_recommendations
        FOR EACH ROW EXECUTE FUNCTION public.prevent_research_review_recommendation_mutation()
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    op.execute(
        "DROP TRIGGER IF EXISTS research_review_recommendations_append_only "
        "ON public.research_review_recommendations"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS public.prevent_research_review_recommendation_mutation()"
    )
    Base.metadata.tables[TABLE_NAMES[0]].drop(bind=bind, checkfirst=True)
