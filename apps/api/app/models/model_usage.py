from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ModelUsageEvent(Base):
    """Immutable metering event for one real upstream model call.

    Identity columns intentionally do not use foreign keys. Billing evidence must
    survive deletion of operational entities, and usage may be written from a
    separate transaction before the related chat transaction commits.
    """

    __tablename__ = "model_usage_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('succeeded', 'failed', 'cancelled')",
            name="ck_model_usage_events_status",
        ),
        CheckConstraint(
            "usage_source IN ('provider', 'litellm', 'estimated', 'unavailable')",
            name="ck_model_usage_events_usage_source",
        ),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND total_tokens >= 0 "
            "AND cached_input_tokens >= 0 "
            "AND cache_creation_input_tokens >= 0 "
            "AND reasoning_tokens >= 0 AND audio_input_tokens >= 0 "
            "AND audio_output_tokens >= 0 "
            "AND accepted_prediction_tokens >= 0 "
            "AND rejected_prediction_tokens >= 0",
            name="ck_model_usage_events_non_negative_tokens",
        ),
        CheckConstraint(
            "latency_ms >= 0",
            name="ck_model_usage_events_non_negative_latency",
        ),
        CheckConstraint(
            "audio_seconds IS NULL OR audio_seconds >= 0",
            name="ck_model_usage_events_non_negative_audio_seconds",
        ),
        CheckConstraint(
            "provider_cost IS NULL OR provider_cost >= 0",
            name="ck_model_usage_events_non_negative_provider_cost",
        ),
        Index("ix_model_usage_events_operation", "operation_id"),
        Index("ix_model_usage_events_request", "request_id"),
        Index("ix_model_usage_events_user_started", "user_id", "started_at"),
        Index("ix_model_usage_events_lab_started", "lab_id", "started_at"),
        Index(
            "ix_model_usage_events_project_started", "project_id", "started_at"
        ),
        Index("ix_model_usage_events_chat_started", "chat_id", "started_at"),
        Index(
            "ix_model_usage_events_model_started",
            "provider",
            "resolved_model",
            "started_at",
        ),
        Index("ix_model_usage_events_provider_request", "provider_request_id"),
    )

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    call_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    operation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parent_operation_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    feature: Mapped[str | None] = mapped_column(String(255), nullable=True)

    lab_id: Mapped[UUID | None] = mapped_column(nullable=True)
    user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    project_id: Mapped[UUID | None] = mapped_column(nullable=True)
    chat_id: Mapped[UUID | None] = mapped_column(nullable=True)
    context_attributes: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'::json")
    )

    call_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_model: Mapped[str] = mapped_column(String(255), nullable=False)
    resolved_model: Mapped[str] = mapped_column(String(255), nullable=False)
    usage_source: Mapped[str] = mapped_column(String(32), nullable=False)

    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    cache_creation_input_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    reasoning_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    audio_input_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    audio_output_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    accepted_prediction_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    rejected_prediction_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    audio_seconds: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 6), nullable=True
    )

    provider_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(38, 18), nullable=True
    )
    provider_cost_currency: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    provider_cost_source: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    provider_request_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_usage: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'::json")
    )
    event_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'::json"),
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latency_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
