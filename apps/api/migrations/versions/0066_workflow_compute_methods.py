"""Seal explicitly published Compute contracts without changing builtin seals."""

import sqlalchemy as sa
from alembic import op

revision = "0066_workflow_compute_methods"
down_revision = "0065_workflow_analysis"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workflow_analysis_methods",
        sa.Column("compute_contract", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE workflow_analysis_methods, workflow_revisions IN ACCESS EXCLUSIVE MODE"
        )
    )
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM workflow_analysis_methods "
            "WHERE compute_contract::jsonb <> '{}'::jsonb) OR EXISTS "
            "(SELECT 1 FROM workflow_revisions WHERE graph ->> 'schema_version' = '3')"
        )
    ):
        raise RuntimeError(
            "Cannot downgrade while published Compute methods or version 3 Workflows exist"
        )
    op.drop_column("workflow_analysis_methods", "compute_contract")
