"""Link Research Resource reservations to actual Record consumption.

Revision ID: 0038_research_resource_consumptions
Revises: 0037_knowledge_ai_provenance
Create Date: 2026-09-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.model_registry import import_models

revision: str = "0038_research_resource_consumptions"
down_revision: str | None = "0037_knowledge_ai_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = ("research_resource_consumptions",)


def upgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    table_names = set(sa.inspect(bind).get_table_names())
    for name in TABLE_NAMES:
        if name not in table_names:
            Base.metadata.tables[name].create(bind=bind, checkfirst=True)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.prevent_research_resource_consumption_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'research_resource_consumptions is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS research_resource_consumptions_append_only
        ON public.research_resource_consumptions
        """
    )
    op.execute(
        """
        CREATE TRIGGER research_resource_consumptions_append_only
        BEFORE UPDATE OR DELETE ON public.research_resource_consumptions
        FOR EACH ROW EXECUTE FUNCTION public.prevent_research_resource_consumption_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS research_resource_consumptions_append_only
        ON public.research_resource_consumptions
        """
    )
    op.execute(
        "DROP FUNCTION IF EXISTS public.prevent_research_resource_consumption_mutation()"
    )
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    Base.metadata.tables[TABLE_NAMES[0]].drop(bind=bind, checkfirst=True)
