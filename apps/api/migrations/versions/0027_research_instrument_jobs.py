"""Add leased Instrument Jobs.

Revision ID: 0027_research_instrument_jobs
Revises: 0026_research_instrument_gateways
Create Date: 2026-09-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_research_instrument_jobs"
down_revision: str | None = "0026_research_instrument_gateways"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = ("research_instrument_jobs",)


def upgrade() -> None:
    # Keep this historical revision independent from the current ORM model.
    # Later revisions extend this table; importing the live model here would make
    # a fresh migration accidentally reference tables that do not exist yet.
    op.create_table(
        "research_instrument_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v7()"),
            nullable=False,
        ),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gateway_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "resource_revision_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("resource_revision", sa.Integer(), nullable=False),
        sa.Column(
            "equipment_booking_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("command_key", sa.String(length=128), nullable=False),
        sa.Column("command_version", sa.String(length=64), nullable=False),
        sa.Column("command_revision", sa.Integer(), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=False),
        sa.Column("risk", sa.String(length=32), nullable=False),
        sa.Column("device_confirmation_required", sa.Boolean(), nullable=False),
        sa.Column("safety_contract", sa.JSON(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("lease_token_digest", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("device_confirmation", sa.JSON(), nullable=False),
        sa.Column("safety_attestation", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("stop_reason", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'leased', 'running', 'stop_requested', "
            "'completed', 'failed', 'cancelled', 'stopped')",
            name="ck_research_instrument_job_status",
        ),
        sa.CheckConstraint(
            "lease_token_digest IS NULL OR length(lease_token_digest) = 64",
            name="ck_research_instrument_job_lease_digest",
        ),
        sa.CheckConstraint(
            "risk IN ('read_only', 'low', 'medium', 'high')",
            name="ck_research_instrument_job_risk",
        ),
        sa.CheckConstraint(
            "timeout_seconds BETWEEN 1 AND 86400",
            name="ck_research_instrument_job_timeout",
        ),
        sa.ForeignKeyConstraint(
            ["action_id"], ["research_actions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["gateway_id"],
            ["research_instrument_gateways.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["command_id"],
            ["research_instrument_commands.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["resource_revision_id"],
            ["resource_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["equipment_booking_id"],
            ["equipment_bookings.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_id", name="uq_research_instrument_job_action"),
    )
    op.create_index(
        "ix_research_instrument_jobs_action_id",
        "research_instrument_jobs",
        ["action_id"],
        unique=True,
    )
    op.create_index(
        "ix_research_instrument_jobs_gateway_id",
        "research_instrument_jobs",
        ["gateway_id"],
    )
    op.create_index(
        "ix_research_instrument_jobs_command_id",
        "research_instrument_jobs",
        ["command_id"],
    )
    op.create_index(
        "ix_research_instrument_jobs_resource_id",
        "research_instrument_jobs",
        ["resource_id"],
    )
    op.create_index(
        "ix_research_instrument_jobs_equipment_booking_id",
        "research_instrument_jobs",
        ["equipment_booking_id"],
    )
    op.create_index(
        "ix_research_instrument_jobs_gateway_status_created",
        "research_instrument_jobs",
        ["gateway_id", "status", "created_at"],
    )
    op.create_index(
        "ix_research_instrument_jobs_booking_status",
        "research_instrument_jobs",
        ["equipment_booking_id", "status"],
    )
    op.create_index(
        "ix_research_instrument_jobs_status_lease",
        "research_instrument_jobs",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_table("research_instrument_jobs")
