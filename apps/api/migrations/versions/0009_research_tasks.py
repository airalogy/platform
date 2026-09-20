"""Add durable research task orchestration.

Revision ID: 0009_research_tasks
Revises: 0008_record_exports
Create Date: 2026-09-02 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

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
    _ensure_legacy_workflow_table(bind)
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


def _ensure_legacy_workflow_table(bind) -> None:
    """Repair early 0008 installations before research_runs references this table.

    Later initial-schema definitions include it, but already-stamped installations
    never re-run 0001. Keep this prerequisite frozen rather than importing a future
    Workflow model. Existing tables and their data are left untouched. The table
    belongs to the initial schema, so downgrading 0009 must not remove it.
    """
    if sa.inspect(bind).has_table("protocol_workflows"):
        return
    metadata = sa.MetaData()
    for name in ("projects", "users", "protocols"):
        sa.Table(name, metadata, sa.Column("id", sa.UUID(), primary_key=True))
    table = sa.Table(
        "protocol_workflows",
        metadata,
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            index=True,
            server_default=sa.func.uuid_generate_v7(),
        ),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False, index=True
        ),
        sa.Column(
            "root_protocol_id", sa.UUID(), sa.ForeignKey("protocols.id"), index=True
        ),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("workflow_info", sa.JSON(), nullable=False),
        sa.Column("path_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime()),
    )
    table.create(bind=bind)
