"""Add durable research task orchestration.

Revision ID: 0009_research_tasks
Revises: 0008_record_exports
Create Date: 2026-09-02 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

from migrations.model_registry import import_models

revision: str = "0009_research_tasks"
down_revision: str | None = "0008_record_exports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_NAMES = (
    "research_tasks",
    "research_task_protocols",
    "research_runs",
    "research_plan_versions",
    "research_actions",
    "research_action_dependencies",
    "research_protocol_runs",
    "research_human_work_items",
    "research_approvals",
    "research_events",
    "research_artifact_links",
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
        CREATE OR REPLACE FUNCTION public.prevent_research_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'research_events is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER research_events_append_only
        BEFORE UPDATE OR DELETE ON public.research_events
        FOR EACH ROW EXECUTE FUNCTION public.prevent_research_event_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS research_events_append_only ON public.research_events"
    )
    op.execute("DROP FUNCTION IF EXISTS public.prevent_research_event_mutation()")
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    Base.metadata.drop_all(bind=bind, tables=list(reversed(_tables(Base.metadata))))
