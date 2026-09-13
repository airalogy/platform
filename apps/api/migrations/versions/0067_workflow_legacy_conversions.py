"""Private lineage for user-confirmed legacy Workflow structure conversions."""

import sqlalchemy as sa
from alembic import op

revision = "0067_workflow_legacy_conversions"
down_revision = "0066_workflow_compute_methods"
branch_labels = None
depends_on = None
TABLE_NAMES = ("workflow_legacy_conversions",)


def upgrade():
    op.create_table(
        "workflow_legacy_conversions",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.func.uuid_generate_v7()
        ),
        sa.Column(
            "source_workflow_id",
            sa.UUID(),
            sa.ForeignKey("protocol_workflows.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "definition_id",
            sa.UUID(),
            sa.ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_revision_id",
            sa.UUID(),
            sa.ForeignKey("workflow_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("node_mapping", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.UUID(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "created_by_user_id", "idempotency_key", name="uq_workflow_legacy_request"
        ),
        sa.UniqueConstraint("workflow_revision_id", name="uq_workflow_legacy_revision"),
        sa.CheckConstraint(
            "source_digest ~ '^[0-9a-f]{64}$'", name="ck_workflow_legacy_source_digest"
        ),
        sa.CheckConstraint(
            "request_digest ~ '^[0-9a-f]{64}$'",
            name="ck_workflow_legacy_request_digest",
        ),
    )
    for name in ("source_workflow_id", "created_by_user_id"):
        op.create_index(
            f"ix_workflow_legacy_conversions_{name}",
            "workflow_legacy_conversions",
            [name],
        )
    op.execute(
        "CREATE TRIGGER immutable_workflow_legacy_conversions BEFORE UPDATE ON workflow_legacy_conversions FOR EACH ROW EXECUTE FUNCTION reject_workflow_history_update()"
    )


def downgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text("LOCK TABLE workflow_legacy_conversions IN ACCESS EXCLUSIVE MODE")
    )
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM workflow_legacy_conversions)")
    ):
        raise RuntimeError(
            "Cannot downgrade while legacy Workflow conversion receipts exist"
        )
    op.drop_table("workflow_legacy_conversions")
