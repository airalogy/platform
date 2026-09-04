"""Add bounded Instrument Control Sessions.

Revision ID: 0047_instrument_control_sessions
Revises: 0046_research_reproduction_assessments
Create Date: 2026-09-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0047_instrument_control_sessions"
down_revision: str | None = "0046_research_reproduction_assessments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "research_instrument_control_sessions"
TABLE_NAMES = (TABLE_NAME,)


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if TABLE_NAME not in tables:
        op.create_table(
            TABLE_NAME,
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("uuid_generate_v7()"),
                nullable=False,
            ),
            sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("gateway_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "equipment_booking_id", postgresql.UUID(as_uuid=True), nullable=False
            ),
            sa.Column("mode", sa.String(length=32), nullable=False),
            sa.Column(
                "status",
                sa.String(length=32),
                server_default="queued",
                nullable=False,
            ),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), server_default="", nullable=False),
            sa.Column("program", sa.JSON(), nullable=False),
            sa.Column("program_digest", sa.String(length=64), nullable=False),
            sa.Column("creation_digest", sa.String(length=64), nullable=False),
            sa.Column("idempotency_key", sa.String(length=160), nullable=False),
            sa.Column("entry_step_key", sa.String(length=64), nullable=False),
            sa.Column("current_step_key", sa.String(length=64), nullable=True),
            sa.Column("pending_step_key", sa.String(length=64), nullable=True),
            sa.Column("issued_steps", sa.Integer(), server_default="0", nullable=False),
            sa.Column(
                "executed_steps", sa.Integer(), server_default="0", nullable=False
            ),
            sa.Column("max_steps", sa.Integer(), nullable=False),
            sa.Column("max_duration_seconds", sa.Integer(), nullable=False),
            sa.Column("pause_reason", sa.Text(), server_default="", nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("stop_reason", sa.Text(), nullable=True),
            sa.Column(
                "created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
            ),
            sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "mode IN ('bounded_sequence', 'feedback_loop')",
                name="ck_research_instrument_control_mode",
            ),
            sa.CheckConstraint(
                "status IN ('queued', 'running', 'paused_for_review', "
                "'stop_requested', 'completed', 'failed', 'cancelled', 'stopped')",
                name="ck_research_instrument_control_status",
            ),
            sa.CheckConstraint(
                "max_steps BETWEEN 1 AND 50",
                name="ck_research_instrument_control_max_steps",
            ),
            sa.CheckConstraint(
                "max_duration_seconds BETWEEN 1 AND 86400",
                name="ck_research_instrument_control_max_duration",
            ),
            sa.CheckConstraint(
                "executed_steps >= 0 AND executed_steps <= max_steps",
                name="ck_research_instrument_control_executed_steps",
            ),
            sa.CheckConstraint(
                "issued_steps >= executed_steps",
                name="ck_research_instrument_control_issued_steps",
            ),
            sa.CheckConstraint(
                "length(program_digest) = 64",
                name="ck_research_instrument_control_digest",
            ),
            sa.CheckConstraint(
                "length(creation_digest) = 64",
                name="ck_research_instrument_control_creation_digest",
            ),
            sa.ForeignKeyConstraint(
                ["run_id"], ["research_runs.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["gateway_id"],
                ["research_instrument_gateways.id"],
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["resource_id"], ["resources.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["equipment_booking_id"],
                ["equipment_bookings.id"],
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "run_id",
                "idempotency_key",
                name="uq_research_instrument_control_key",
            ),
        )
        op.create_index(
            "ix_research_instrument_control_run_status",
            TABLE_NAME,
            ["run_id", "status"],
        )
        op.create_index(
            "ix_research_instrument_control_gateway_status",
            TABLE_NAME,
            ["gateway_id", "status"],
        )

    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("research_instrument_jobs")
    }
    if "control_session_id" not in columns:
        op.add_column(
            "research_instrument_jobs",
            sa.Column(
                "control_session_id", postgresql.UUID(as_uuid=True), nullable=True
            ),
        )
        op.add_column(
            "research_instrument_jobs",
            sa.Column("control_step_key", sa.String(length=64), nullable=True),
        )
        op.add_column(
            "research_instrument_jobs",
            sa.Column("control_execution_index", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_research_instrument_job_control_session",
            "research_instrument_jobs",
            TABLE_NAME,
            ["control_session_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(
            "ix_research_instrument_jobs_control_session_id",
            "research_instrument_jobs",
            ["control_session_id"],
        )
        op.create_unique_constraint(
            "uq_research_instrument_job_control_execution",
            "research_instrument_jobs",
            ["control_session_id", "control_execution_index"],
        )
        op.create_check_constraint(
            "ck_research_instrument_job_control_context",
            "research_instrument_jobs",
            "(control_session_id IS NULL AND control_step_key IS NULL AND "
            "control_execution_index IS NULL) OR "
            "(control_session_id IS NOT NULL AND control_step_key IS NOT NULL AND "
            "control_execution_index IS NOT NULL)",
        )


def downgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("research_instrument_jobs")
    }
    if "control_session_id" in columns:
        op.drop_constraint(
            "ck_research_instrument_job_control_context",
            "research_instrument_jobs",
            type_="check",
        )
        op.drop_constraint(
            "uq_research_instrument_job_control_execution",
            "research_instrument_jobs",
            type_="unique",
        )
        op.drop_index(
            "ix_research_instrument_jobs_control_session_id",
            table_name="research_instrument_jobs",
        )
        op.drop_constraint(
            "fk_research_instrument_job_control_session",
            "research_instrument_jobs",
            type_="foreignkey",
        )
        op.drop_column("research_instrument_jobs", "control_execution_index")
        op.drop_column("research_instrument_jobs", "control_step_key")
        op.drop_column("research_instrument_jobs", "control_session_id")
    if TABLE_NAME in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_index(
            "ix_research_instrument_control_gateway_status", table_name=TABLE_NAME
        )
        op.drop_index(
            "ix_research_instrument_control_run_status", table_name=TABLE_NAME
        )
        op.drop_table(TABLE_NAME)
