"""Persist versioned manual Workflows without changing legacy Workflow assets."""

import sqlalchemy as sa
from alembic import op

revision = "0063_workflow_definitions"
down_revision = "0062_analysis_compute_ai"
branch_labels = None
depends_on = None
TABLE_NAMES = ("workflow_definitions", "workflow_revisions", "workflow_run_bindings")


def identity():
    return sa.Column(
        "id", sa.UUID(), primary_key=True, server_default=sa.func.uuid_generate_v7()
    )


def reference(name, target, ondelete="RESTRICT"):
    return sa.Column(
        name, sa.UUID(), sa.ForeignKey(target, ondelete=ondelete), nullable=False
    )


def created():
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def upgrade():
    op.create_table(
        "workflow_definitions",
        identity(),
        reference("project_id", "projects.id", "CASCADE"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        reference("created_by_user_id", "users.id"),
        created(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("revision >= 1", name="ck_workflow_definition_revision"),
    )
    op.create_index(
        "ix_workflow_definitions_project_id", "workflow_definitions", ["project_id"]
    )
    op.create_table(
        "workflow_revisions",
        identity(),
        reference("definition_id", "workflow_definitions.id", "CASCADE"),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("graph", sa.JSON(), nullable=False),
        sa.Column("pins", sa.JSON(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.UUID(), nullable=False),
        reference("created_by_user_id", "users.id"),
        created(),
        sa.UniqueConstraint("definition_id", "revision", name="uq_workflow_revision"),
        sa.UniqueConstraint(
            "created_by_user_id", "idempotency_key", name="uq_workflow_revision_request"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_workflow_revision_number"),
        sa.CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$'", name="ck_workflow_revision_digest"
        ),
    )
    op.create_index(
        "ix_workflow_revisions_definition_id", "workflow_revisions", ["definition_id"]
    )
    op.create_table(
        "workflow_run_bindings",
        identity(),
        reference("workflow_revision_id", "workflow_revisions.id"),
        reference("task_id", "research_tasks.id", "CASCADE"),
        reference("run_id", "research_runs.id", "CASCADE"),
        sa.Column("environment_digest", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.UUID(), nullable=False),
        reference("created_by_user_id", "users.id"),
        created(),
        sa.UniqueConstraint("run_id", name="uq_workflow_run_binding"),
        sa.UniqueConstraint(
            "created_by_user_id", "idempotency_key", name="uq_workflow_run_request"
        ),
    )
    for column in ("workflow_revision_id", "task_id"):
        op.create_index(
            f"ix_workflow_run_bindings_{column}", "workflow_run_bindings", [column]
        )
    op.execute("""
        CREATE FUNCTION reject_workflow_history_update() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'Workflow revisions and runtime lineage are immutable'; END;
        $$ LANGUAGE plpgsql;
    """)
    for table in ("workflow_revisions", "workflow_run_bindings"):
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_workflow_history_update()"
        )


def downgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE workflow_definitions, workflow_revisions, workflow_run_bindings IN ACCESS EXCLUSIVE MODE"
        )
    )
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM workflow_definitions)")):
        raise RuntimeError("Cannot downgrade while versioned Workflow assets exist")
    for table in (
        "workflow_run_bindings",
        "workflow_revisions",
        "workflow_definitions",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION reject_workflow_history_update()")
