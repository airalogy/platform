"""Add immutable model usage metering events.

Revision ID: 0006_model_usage_events
Revises: 0005_record_substring_search
Create Date: 2026-07-22 00:00:00.000000
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_model_usage_events"
down_revision: str | None = "0005_record_substring_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_usage_events",
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("call_id", sa.String(length=128), nullable=False),
        sa.Column("operation_id", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("parent_operation_id", sa.String(length=128), nullable=True),
        sa.Column("feature", sa.String(length=255), nullable=True),
        sa.Column("lab_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("chat_id", sa.UUID(), nullable=True),
        sa.Column(
            "context_attributes",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
        sa.Column("call_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("requested_model", sa.String(length=255), nullable=False),
        sa.Column("resolved_model", sa.String(length=255), nullable=False),
        sa.Column("usage_source", sa.String(length=32), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cached_input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cache_creation_input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("reasoning_tokens", sa.BigInteger(), nullable=False),
        sa.Column("audio_input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("audio_output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("accepted_prediction_tokens", sa.BigInteger(), nullable=False),
        sa.Column("rejected_prediction_tokens", sa.BigInteger(), nullable=False),
        sa.Column("audio_seconds", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("provider_cost", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("provider_cost_currency", sa.String(length=16), nullable=True),
        sa.Column("provider_cost_source", sa.String(length=64), nullable=True),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column(
            "raw_usage",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.BigInteger(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed', 'cancelled')",
            name="ck_model_usage_events_status",
        ),
        sa.CheckConstraint(
            "usage_source IN ('provider', 'litellm', 'estimated', 'unavailable')",
            name="ck_model_usage_events_usage_source",
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND total_tokens >= 0 "
            "AND cached_input_tokens >= 0 "
            "AND cache_creation_input_tokens >= 0 "
            "AND reasoning_tokens >= 0 AND audio_input_tokens >= 0 "
            "AND audio_output_tokens >= 0 "
            "AND accepted_prediction_tokens >= 0 "
            "AND rejected_prediction_tokens >= 0",
            name="ck_model_usage_events_non_negative_tokens",
        ),
        sa.CheckConstraint(
            "latency_ms >= 0",
            name="ck_model_usage_events_non_negative_latency",
        ),
        sa.CheckConstraint(
            "audio_seconds IS NULL OR audio_seconds >= 0",
            name="ck_model_usage_events_non_negative_audio_seconds",
        ),
        sa.CheckConstraint(
            "provider_cost IS NULL OR provider_cost >= 0",
            name="ck_model_usage_events_non_negative_provider_cost",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )

    op.create_index(
        "ix_model_usage_events_call_id", "model_usage_events", ["call_id"]
    )
    op.create_index(
        "ix_model_usage_events_operation", "model_usage_events", ["operation_id"]
    )
    op.create_index(
        "ix_model_usage_events_request", "model_usage_events", ["request_id"]
    )
    op.create_index(
        "ix_model_usage_events_user_started",
        "model_usage_events",
        ["user_id", "started_at"],
    )
    op.create_index(
        "ix_model_usage_events_lab_started",
        "model_usage_events",
        ["lab_id", "started_at"],
    )
    op.create_index(
        "ix_model_usage_events_project_started",
        "model_usage_events",
        ["project_id", "started_at"],
    )
    op.create_index(
        "ix_model_usage_events_chat_started",
        "model_usage_events",
        ["chat_id", "started_at"],
    )
    op.create_index(
        "ix_model_usage_events_model_started",
        "model_usage_events",
        ["provider", "resolved_model", "started_at"],
    )
    op.create_index(
        "ix_model_usage_events_provider_request",
        "model_usage_events",
        ["provider_request_id"],
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.prevent_model_usage_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'model_usage_events is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER model_usage_events_append_only
        BEFORE UPDATE OR DELETE ON public.model_usage_events
        FOR EACH ROW EXECUTE FUNCTION public.prevent_model_usage_event_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS model_usage_events_append_only "
        "ON public.model_usage_events"
    )
    op.drop_table("model_usage_events")
    op.execute(
        "DROP FUNCTION IF EXISTS public.prevent_model_usage_event_mutation()"
    )
