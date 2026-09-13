"""Persist bounded analysis generation requests and their explicit provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0060_analysis_ai"
down_revision = "0059_analysis"
branch_labels = None
depends_on = None
TABLE_NAMES = ("analysis_ai_requests",)


def upgrade():
    # Keep this DDL independent of future application model changes.
    op.create_table(
        "analysis_ai_requests",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.func.uuid_generate_v7(),
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "protocol_id",
            sa.UUID(),
            sa.ForeignKey("protocols.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "analysis_run_id",
            sa.UUID(),
            sa.ForeignKey("analysis_runs.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "previous_request_id",
            sa.UUID(),
            sa.ForeignKey("analysis_ai_requests.id", ondelete="RESTRICT"),
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(16), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("operation_id", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("source_selection", sa.JSON(), nullable=False),
        sa.Column("source_manifest", sa.JSON(), nullable=False),
        sa.Column("input_context", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("output", sa.JSON(none_as_null=True)),
        sa.Column("output_digest", sa.String(64)),
        sa.Column("error", sa.String(64)),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "kind IN ('draft','interpretation')", name="ck_analysis_ai_kind"
        ),
        sa.CheckConstraint(
            "(kind = 'draft' AND analysis_run_id IS NULL) OR "
            "(kind = 'interpretation' AND analysis_run_id IS NOT NULL)",
            name="ck_analysis_ai_run_kind",
        ),
        sa.CheckConstraint(
            "state IN ('generating','generated','failed')",
            name="ck_analysis_ai_state",
        ),
        sa.CheckConstraint(
            "state <> 'generated' OR output IS NOT NULL",
            name="ck_analysis_ai_generated_output",
        ),
        sa.CheckConstraint(
            "(output IS NULL) = (output_digest IS NULL)",
            name="ck_analysis_ai_output_pair",
        ),
        sa.CheckConstraint(
            "previous_request_id IS NULL OR previous_request_id <> id",
            name="ck_analysis_ai_not_self",
        ),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_ai_request_fingerprint",
        ),
        sa.CheckConstraint(
            "input_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_ai_input_digest"
        ),
        sa.CheckConstraint(
            "source_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_ai_source_digest"
        ),
        sa.CheckConstraint(
            "output_digest IS NULL OR output_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_ai_output_digest",
        ),
    )
    for column in (
        "project_id",
        "protocol_id",
        "analysis_run_id",
        "previous_request_id",
    ):
        op.create_index(
            f"ix_analysis_ai_requests_{column}", "analysis_ai_requests", [column]
        )
    op.create_index(
        "ix_analysis_ai_requests_owner_protocol_created",
        "analysis_ai_requests",
        ["created_by_user_id", "protocol_id", "created_at"],
    )
    op.create_index(
        "ix_analysis_ai_requests_state_deadline",
        "analysis_ai_requests",
        ["state", "deadline"],
    )
    for table in ("analysis_previews", "analysis_runs"):
        op.add_column(
            table,
            sa.Column("ai_provenance", sa.JSON(), nullable=False, server_default="{}"),
        )


def downgrade():
    for table in ("analysis_runs", "analysis_previews"):
        op.drop_column(table, "ai_provenance")
    op.drop_table("analysis_ai_requests")
