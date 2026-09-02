"""Typed digital execution records for Research Actions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ResearchToolJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchWaitEventStatus(StrEnum):
    WAITING = "waiting"
    RECEIVED = "received"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ResearchExecutorBindingPolicy(StrEnum):
    ALWAYS_ASK = "always_ask"
    ALLOW_READ_ONLY = "allow_read_only"
    DENY = "deny"


class ResearchExecutorBinding(Base):
    __tablename__ = "research_executor_bindings"
    __table_args__ = (
        UniqueConstraint(
            "lab_id",
            "capability_key",
            "capability_version",
            "executor_type",
            "executor_ref_type",
            "executor_ref_id",
            name="uq_research_executor_bindings_identity",
        ),
        Index(
            "ix_research_executor_bindings_resolution",
            "lab_id",
            "capability_key",
            "capability_version",
            "enabled",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    capability_key: Mapped[str] = mapped_column(String(255), nullable=False)
    capability_version: Mapped[str] = mapped_column(String(64), nullable=False)
    executor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    executor_ref_type: Mapped[str] = mapped_column(String(64), nullable=False)
    executor_ref_id: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_policy: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ResearchExecutorBindingPolicy.ALWAYS_ASK.value,
    )
    constraints: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    priority: Mapped[int] = mapped_column(nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchExecutorBindingAudit(Base):
    __tablename__ = "research_executor_binding_audits"
    __table_args__ = (
        UniqueConstraint(
            "binding_id",
            "revision",
            name="uq_research_executor_binding_audits_revision",
        ),
        Index(
            "ix_research_executor_binding_audits_lab_created",
            "lab_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    binding_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_executor_bindings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchToolJob(Base):
    __tablename__ = "research_tool_jobs"
    __table_args__ = (
        UniqueConstraint("action_id", name="uq_research_tool_job_action"),
        Index("ix_research_tool_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_actions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    tool_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tool_version: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ResearchToolJobStatus.QUEUED.value
    )
    timeout_seconds: Mapped[int] = mapped_column(nullable=False, default=60)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchWaitEvent(Base):
    __tablename__ = "research_wait_events"
    __table_args__ = (
        UniqueConstraint("action_id", name="uq_research_wait_event_action"),
        UniqueConstraint("event_key", name="uq_research_wait_event_key"),
        Index("ix_research_wait_events_status_due", "status", "due_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_actions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    event_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    expected_event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    received_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ResearchWaitEventStatus.WAITING.value
    )
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
