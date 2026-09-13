"""Seal conditional decisions and exact downstream Workflow inputs."""

import sqlalchemy as sa
from alembic import op

revision = "0064_workflow_node_resolutions"
down_revision = "0063_workflow_definitions"
branch_labels = None
depends_on = None
TABLE_NAMES = ("workflow_node_resolutions",)


def upgrade():
    op.create_table(
        "workflow_node_resolutions",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.func.uuid_generate_v7()
        ),
        sa.Column(
            "workflow_revision_id",
            sa.UUID(),
            sa.ForeignKey("workflow_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.UUID(),
            sa.ForeignKey("research_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.UUID(),
            sa.ForeignKey("research_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "action_id",
            sa.UUID(),
            sa.ForeignKey("research_actions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_id", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("initial_values", sa.JSON(), nullable=False),
        sa.Column("receipt", sa.JSON(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("action_id", name="uq_workflow_node_resolution_action"),
        sa.UniqueConstraint(
            "run_id", "node_id", name="uq_workflow_node_resolution_node"
        ),
        sa.CheckConstraint(
            "state IN ('ready', 'branch_not_selected', 'blocked', 'failed')",
            name="ck_workflow_node_resolution_state",
        ),
        sa.CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$'", name="ck_workflow_node_resolution_digest"
        ),
    )
    for column in ("task_id", "run_id"):
        op.create_index(
            f"ix_workflow_node_resolutions_{column}",
            "workflow_node_resolutions",
            [column],
        )
    op.execute(
        "CREATE TRIGGER immutable_workflow_node_resolutions BEFORE UPDATE ON workflow_node_resolutions FOR EACH ROW EXECUTE FUNCTION reject_workflow_history_update()"
    )


def downgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text("LOCK TABLE workflow_node_resolutions IN ACCESS EXCLUSIVE MODE")
    )
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM workflow_node_resolutions)")
    ):
        raise RuntimeError("Cannot downgrade while Workflow resolution receipts exist")
    op.drop_table("workflow_node_resolutions")
