"""Add governed research Compute Jobs.

Revision ID: 0032_research_compute_jobs
Revises: 0031_research_compute_runners
Create Date: 2026-09-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_research_compute_jobs"
down_revision: str | None = "0031_research_compute_runners"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = (
    "research_compute_jobs",
    "research_compute_job_inputs",
)


# Historical model in 154cc8d; output_manifest belongs to 0033, analysis to 0061.
FROZEN_MODEL_COMMIT = "154cc8d"


def upgrade() -> None:
    op.create_table(
        "research_compute_jobs",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.func.uuid_generate_v7()
        ),
        sa.Column(
            "action_id",
            sa.UUID(),
            sa.ForeignKey("research_actions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "compute_environment_id",
            sa.UUID(),
            sa.ForeignKey("research_compute_environments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "compute_environment_revision_id",
            sa.UUID(),
            sa.ForeignKey(
                "research_compute_environment_revisions.id", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        sa.Column("compute_environment_revision", sa.Integer(), nullable=False),
        sa.Column(
            "runner_id",
            sa.UUID(),
            sa.ForeignKey("research_compute_runners.id", ondelete="SET NULL"),
        ),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("source_code", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("result_schema", sa.JSON(), nullable=False),
        sa.Column("environment_snapshot", sa.JSON(), nullable=False),
        sa.Column("resource_limits", sa.JSON(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(38, 18)),
        sa.Column("actual_cost", sa.Numeric(38, 18)),
        sa.Column("currency", sa.String(3)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("lease_token_digest", sa.String(64)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("cancel_reason", sa.Text()),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        *[
            sa.Column(name, sa.DateTime(timezone=True))
            for name in (
                "approved_at",
                "queued_at",
                "leased_at",
                "started_at",
                "heartbeat_at",
                "cancel_requested_at",
                "completed_at",
            )
        ],
        sa.UniqueConstraint("action_id", name="uq_research_compute_job_action"),
        sa.CheckConstraint(
            "status IN ('awaiting_approval', 'queued', 'leased', 'running', "
            "'cancel_requested', 'completed', 'failed', 'cancelled')",
            name="ck_research_compute_job_status",
        ),
        sa.CheckConstraint(
            "language IN ('python', 'r')", name="ck_research_compute_job_language"
        ),
        sa.CheckConstraint(
            "length(source_sha256) = 64", name="ck_research_compute_job_source_digest"
        ),
        sa.CheckConstraint(
            "lease_token_digest IS NULL OR length(lease_token_digest) = 64",
            name="ck_research_compute_job_lease_digest",
        ),
        sa.CheckConstraint(
            "timeout_seconds BETWEEN 1 AND 86400",
            name="ck_research_compute_job_timeout",
        ),
        sa.CheckConstraint(
            "((estimated_cost IS NULL AND currency IS NULL) OR "
            "(estimated_cost >= 0 AND currency IS NOT NULL AND "
            "length(currency) = 3 AND currency = upper(currency)))",
            name="ck_research_compute_job_cost_pair",
        ),
    )
    for column in (
        "action_id",
        "compute_environment_id",
        "compute_environment_revision_id",
        "runner_id",
    ):
        op.create_index(
            f"ix_research_compute_jobs_{column}",
            "research_compute_jobs",
            [column],
            unique=column == "action_id",
        )
    for name, columns in (
        ("status_lease", ["status", "lease_expires_at"]),
        ("runner_status", ["runner_id", "status"]),
        ("environment_status", ["compute_environment_revision_id", "status"]),
    ):
        op.create_index(
            f"ix_research_compute_jobs_{name}", "research_compute_jobs", columns
        )
    op.create_table(
        "research_compute_job_inputs",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.func.uuid_generate_v7()
        ),
        sa.Column(
            "compute_job_id",
            sa.UUID(),
            sa.ForeignKey("research_compute_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "data_asset_id",
            sa.UUID(),
            sa.ForeignKey("data_assets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "data_asset_version_id",
            sa.UUID(),
            sa.ForeignKey("data_asset_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("mount_name", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "compute_job_id", "position", name="uq_research_compute_job_input_position"
        ),
        sa.UniqueConstraint(
            "compute_job_id",
            "data_asset_version_id",
            name="uq_research_compute_job_input_asset_version",
        ),
    )
    for column in ("compute_job_id", "data_asset_id", "data_asset_version_id"):
        op.create_index(
            f"ix_research_compute_job_inputs_{column}",
            "research_compute_job_inputs",
            [column],
        )


def downgrade() -> None:
    for table in reversed(TABLE_NAMES):
        op.drop_table(table)
