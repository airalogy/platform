"""Typed digital execution records for Research Actions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
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


class ResearchResourceReservationStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    RELEASED = "released"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class ResearchBudgetEntryKind(StrEnum):
    RESERVE = "reserve"
    RELEASE = "release"
    EXPENSE = "expense"
    CREDIT = "credit"


class ResearchNotificationDeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class ResearchBudgetEntry(Base):
    """Immutable reservation and actual-cost ledger for one Research Task."""

    __tablename__ = "research_budget_entries"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "idempotency_key", name="uq_research_budget_entry_idempotency"
        ),
        CheckConstraint("amount > 0", name="ck_research_budget_entry_positive"),
        CheckConstraint(
            "kind IN ('reserve', 'release', 'expense', 'credit')",
            name="ck_research_budget_entry_kind",
        ),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_research_budget_entry_currency",
        ),
        CheckConstraint(
            "length(command_digest) = 64",
            name="ck_research_budget_entry_digest",
        ),
        Index("ix_research_budget_entries_task_created", "task_id", "created_at"),
        Index("ix_research_budget_entries_run", "run_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_runs.id", ondelete="SET NULL")
    )
    action_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_actions.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    source_ref: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    command_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchResourceReservation(Base):
    __tablename__ = "research_resource_reservations"
    __table_args__ = (
        UniqueConstraint(
            "action_id", name="uq_research_resource_reservation_action"
        ),
        Index(
            "ix_research_resource_reservations_resource_status",
            "resource_id",
            "status",
        ),
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
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    resource_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("resource_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    resource_revision: Mapped[int] = mapped_column(nullable=False)
    container_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resource_containers.id", ondelete="RESTRICT")
    )
    inventory_reservation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("inventory_reservations.id", ondelete="SET NULL"), unique=True
    )
    equipment_booking_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("equipment_bookings.id", ondelete="SET NULL"), unique=True
    )
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    unit: Mapped[str | None] = mapped_column(String(32))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ResearchResourceReservationStatus.PROPOSED.value,
    )
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


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


class ResearchHumanExecutorProfile(Base):
    """Lab-governed human availability and verified skill claims."""

    __tablename__ = "research_human_executor_profiles"
    __table_args__ = (
        UniqueConstraint(
            "lab_id", "user_id", name="uq_research_human_executor_profile_user"
        ),
        CheckConstraint(
            "availability IN ('available', 'unavailable')",
            name="ck_research_human_executor_profile_availability",
        ),
        CheckConstraint(
            "max_concurrent_items BETWEEN 1 AND 100",
            name="ck_research_human_executor_profile_capacity",
        ),
        CheckConstraint(
            "available_from IS NULL OR available_until IS NULL "
            "OR available_from < available_until",
            name="ck_research_human_executor_profile_window",
        ),
        Index(
            "ix_research_human_executor_profiles_lab_availability",
            "lab_id",
            "availability",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    availability: Mapped[str] = mapped_column(
        String(32), nullable=False, default="available"
    )
    available_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_concurrent_items: Mapped[int] = mapped_column(nullable=False, default=1)
    skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
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


class ResearchHumanExecutorProfileAudit(Base):
    __tablename__ = "research_human_executor_profile_audits"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "revision",
            name="uq_research_human_executor_profile_audit_revision",
        ),
        Index(
            "ix_research_human_executor_profile_audits_lab_created",
            "lab_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_human_executor_profiles.id", ondelete="CASCADE"),
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


class ResearchNotification(Base):
    """Private attention item derived from a durable Research event."""

    __tablename__ = "research_notifications"
    __table_args__ = (
        UniqueConstraint(
            "recipient_user_id",
            "deduplication_key",
            name="uq_research_notification_recipient_dedupe",
        ),
        CheckConstraint(
            "kind IN ('work_item_assigned', 'approval_requested')",
            name="ck_research_notification_kind",
        ),
        CheckConstraint(
            "priority IN ('normal', 'high')",
            name="ck_research_notification_priority",
        ),
        Index(
            "ix_research_notifications_recipient_read",
            "recipient_user_id",
            "read_at",
            "created_at",
        ),
        Index("ix_research_notifications_task_created", "task_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_actions.id", ondelete="SET NULL"), index=True
    )
    work_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_human_work_items.id", ondelete="SET NULL"), index=True
    )
    approval_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_approvals.id", ondelete="SET NULL"), index=True
    )
    recipient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_path: Mapped[str] = mapped_column(String(512), nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(255), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchNotificationDelivery(Base):
    """Mutable delivery state; the persistent job keeps retry attempt history."""

    __tablename__ = "research_notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "notification_id",
            "channel",
            name="uq_research_notification_delivery_channel",
        ),
        CheckConstraint(
            "channel IN ('email')",
            name="ck_research_notification_delivery_channel",
        ),
        CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'skipped')",
            name="ck_research_notification_delivery_status",
        ),
        Index(
            "ix_research_notification_deliveries_status_updated",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    notification_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_notifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="email")
    destination: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ResearchNotificationDeliveryStatus.PENDING.value,
    )
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
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
