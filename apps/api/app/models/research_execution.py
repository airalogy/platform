"""Typed digital execution records for Research Actions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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


class ResearchAutonomyPolicy(Base):
    """Current Lab policy for automatic Research Action execution."""

    __tablename__ = "research_autonomy_policies"
    __table_args__ = (
        UniqueConstraint("lab_id", name="uq_research_autonomy_policies_lab"),
        CheckConstraint("revision >= 1", name="ck_research_autonomy_policies_revision"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
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


class ResearchAutonomyPolicyAudit(Base):
    """Immutable revision ledger for Lab Research autonomy policy."""

    __tablename__ = "research_autonomy_policy_audits"
    __table_args__ = (
        UniqueConstraint(
            "policy_id",
            "revision",
            name="uq_research_autonomy_policy_audits_revision",
        ),
        Index(
            "ix_research_autonomy_policy_audits_lab_created",
            "lab_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_autonomy_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


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


class ResearchInstrumentRisk(StrEnum):
    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ResearchInstrumentJobStatus(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    STOP_REQUESTED = "stop_requested"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STOPPED = "stopped"


class ResearchComputeJobStatus(StrEnum):
    AWAITING_APPROVAL = "awaiting_approval"
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchServiceJobStatus(StrEnum):
    BLOCKED = "blocked"
    AWAITING_QUOTE = "awaiting_quote"
    AWAITING_APPROVAL = "awaiting_approval"
    ORDERED = "ordered"
    IN_FULFILLMENT = "in_fulfillment"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchComputeEnvironment(Base):
    """Stable Lab identity for an immutable compute-environment lineage."""

    __tablename__ = "research_compute_environments"
    __table_args__ = (
        UniqueConstraint(
            "lab_id", "environment_key", name="uq_research_compute_environment_key"
        ),
        Index("ix_research_compute_environments_lab", "lab_id", "archived_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    environment_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchComputeEnvironmentRevision(Base):
    """Immutable execution and resource contract for one compute environment."""

    __tablename__ = "research_compute_environment_revisions"
    __table_args__ = (
        UniqueConstraint(
            "compute_environment_id",
            "revision",
            name="uq_research_compute_environment_revision",
        ),
        CheckConstraint(
            "network_policy IN ('none', 'egress_allowlist')",
            name="ck_research_compute_environment_network_policy",
        ),
        CheckConstraint(
            "risk IN ('low', 'medium', 'high')",
            name="ck_research_compute_environment_risk",
        ),
        CheckConstraint(
            "((estimated_cost_per_hour IS NULL AND currency IS NULL) OR "
            "(estimated_cost_per_hour >= 0 AND currency IS NOT NULL AND "
            "length(currency) = 3 AND currency = upper(currency)))",
            name="ck_research_compute_environment_cost_pair",
        ),
        Index(
            "ix_research_compute_environment_revisions_environment",
            "compute_environment_id",
            "revision",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    compute_environment_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_compute_environments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    runner_protocol_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="airalogy.compute-runner.v1"
    )
    image_ref: Mapped[str] = mapped_column(String(2048), nullable=False)
    runtime_version: Mapped[str] = mapped_column(String(128), nullable=False)
    allowed_languages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    resource_limits: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    network_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="none"
    )
    allowed_egress_hosts: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    input_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    software_manifest: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    estimated_cost_per_hour: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    currency: Mapped[str | None] = mapped_column(String(3))
    risk: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchComputeRunner(Base):
    """Lab-owned identity and credential boundary for an isolated Compute Runner."""

    __tablename__ = "research_compute_runners"
    __table_args__ = (
        UniqueConstraint("lab_id", "name", name="uq_research_compute_runner_name"),
        CheckConstraint(
            "length(token_digest) = 64",
            name="ck_research_compute_runner_token_digest",
        ),
        CheckConstraint(
            "max_concurrent_jobs BETWEEN 1 AND 64",
            name="ck_research_compute_runner_concurrency",
        ),
        Index(
            "ix_research_compute_runners_lab_enabled",
            "lab_id",
            "enabled",
        ),
    )

    json_exclude_fields: ClassVar[list[str]] = ["token_digest"]

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    runner_protocol_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="airalogy.compute-runner.v1"
    )
    max_concurrent_jobs: Mapped[int] = mapped_column(nullable=False, default=1)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    token_hint: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    last_report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
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
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchComputeRunnerEnvironment(Base):
    """Explicit authorization for a Runner to use one exact environment revision."""

    __tablename__ = "research_compute_runner_environments"
    __table_args__ = (
        UniqueConstraint(
            "runner_id",
            "compute_environment_revision_id",
            name="uq_research_compute_runner_environment",
        ),
        Index(
            "ix_research_compute_runner_environments_runner",
            "runner_id",
            "archived_at",
        ),
        Index(
            "ix_research_compute_runner_environments_revision",
            "compute_environment_revision_id",
            "archived_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    runner_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_compute_runners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    compute_environment_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_compute_environments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    compute_environment_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_compute_environment_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchComputeRunnerAudit(Base):
    """Immutable Runner and environment-binding configuration history."""

    __tablename__ = "research_compute_runner_audits"
    __table_args__ = (
        UniqueConstraint(
            "runner_id",
            "revision",
            name="uq_research_compute_runner_audit_revision",
        ),
        Index(
            "ix_research_compute_runner_audits_runner_created",
            "runner_id",
            "created_at",
        ),
        Index(
            "ix_research_compute_runner_audits_lab_created",
            "lab_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    runner_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_compute_runners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    binding_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_compute_runner_environments.id", ondelete="SET NULL"),
        index=True,
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchComputeJob(Base):
    """One approved, version-pinned computation leased to an isolated Runner."""

    __tablename__ = "research_compute_jobs"
    __table_args__ = (
        UniqueConstraint("action_id", name="uq_research_compute_job_action"),
        CheckConstraint(
            "status IN ('awaiting_approval', 'queued', 'leased', 'running', "
            "'cancel_requested', 'completed', 'failed', 'cancelled')",
            name="ck_research_compute_job_status",
        ),
        CheckConstraint(
            "language IN ('python', 'r')",
            name="ck_research_compute_job_language",
        ),
        CheckConstraint(
            "length(source_sha256) = 64",
            name="ck_research_compute_job_source_digest",
        ),
        CheckConstraint(
            "lease_token_digest IS NULL OR length(lease_token_digest) = 64",
            name="ck_research_compute_job_lease_digest",
        ),
        CheckConstraint(
            "timeout_seconds BETWEEN 1 AND 86400",
            name="ck_research_compute_job_timeout",
        ),
        CheckConstraint(
            "((estimated_cost IS NULL AND currency IS NULL) OR "
            "(estimated_cost >= 0 AND currency IS NOT NULL AND "
            "length(currency) = 3 AND currency = upper(currency)))",
            name="ck_research_compute_job_cost_pair",
        ),
        Index(
            "ix_research_compute_jobs_status_lease",
            "status",
            "lease_expires_at",
        ),
        Index(
            "ix_research_compute_jobs_runner_status",
            "runner_id",
            "status",
        ),
        Index(
            "ix_research_compute_jobs_environment_status",
            "compute_environment_revision_id",
            "status",
        ),
    )

    json_exclude_fields: ClassVar[list[str]] = ["lease_token_digest", "source_code"]

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_actions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    compute_environment_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_compute_environments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    compute_environment_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_compute_environment_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    compute_environment_revision: Mapped[int] = mapped_column(nullable=False)
    runner_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_compute_runners.id", ondelete="SET NULL"), index=True
    )
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    input_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    environment_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    resource_limits: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    timeout_seconds: Mapped[int] = mapped_column(nullable=False)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    actual_cost: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    currency: Mapped[str | None] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ResearchComputeJobStatus.AWAITING_APPROVAL.value,
    )
    lease_token_digest: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_manifest: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    usage: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchComputeJobInput(Base):
    """An exact, Platform-controlled DataAsset version exposed to one job."""

    __tablename__ = "research_compute_job_inputs"
    __table_args__ = (
        UniqueConstraint(
            "compute_job_id", "position", name="uq_research_compute_job_input_position"
        ),
        UniqueConstraint(
            "compute_job_id",
            "data_asset_version_id",
            name="uq_research_compute_job_input_asset_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    compute_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_compute_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    data_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("data_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    data_asset_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("data_asset_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(nullable=False)
    mount_name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchComputeJobOutput(Base):
    """A declared, bounded output promoted to a DataAsset only on completion."""

    __tablename__ = "research_compute_job_outputs"
    __table_args__ = (
        UniqueConstraint(
            "compute_job_id", "position", name="uq_research_compute_job_output_position"
        ),
        UniqueConstraint(
            "compute_job_id",
            "mount_name",
            name="uq_research_compute_job_output_mount_name",
        ),
        CheckConstraint(
            "kind IN ('file', 'table', 'image', 'model', 'archive')",
            name="ck_research_compute_job_output_kind",
        ),
        CheckConstraint(
            "max_bytes BETWEEN 1 AND 2147483647",
            name="ck_research_compute_job_output_max_bytes",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    compute_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_compute_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(nullable=False)
    mount_name: Mapped[str] = mapped_column(String(128), nullable=False)
    asset_name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    max_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    data_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version_metadata: Mapped[dict] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    blob_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_file_blobs.id", ondelete="RESTRICT"), index=True
    )
    research_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_files.id", ondelete="RESTRICT"), index=True
    )
    data_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_assets.id", ondelete="RESTRICT"), index=True
    )
    data_asset_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_asset_versions.id", ondelete="RESTRICT"), index=True
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchServiceProvider(Base):
    """Lab-governed identity for an external research-service provider."""

    __tablename__ = "research_service_providers"
    __table_args__ = (
        UniqueConstraint(
            "lab_id", "provider_key", name="uq_research_service_provider_key"
        ),
        Index("ix_research_service_providers_lab_enabled", "lab_id", "enabled"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    contact_email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    website_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
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


class ResearchServiceProviderAudit(Base):
    __tablename__ = "research_service_provider_audits"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "revision",
            name="uq_research_service_provider_audit_revision",
        ),
        Index(
            "ix_research_service_provider_audits_lab_created",
            "lab_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_service_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchServiceOffering(Base):
    """Stable Lab identity whose executable contract lives in immutable revisions."""

    __tablename__ = "research_service_offerings"
    __table_args__ = (
        UniqueConstraint(
            "lab_id", "offering_key", name="uq_research_service_offering_key"
        ),
        Index("ix_research_service_offerings_lab_enabled", "lab_id", "enabled"),
        Index(
            "ix_research_service_offerings_provider_enabled",
            "provider_id",
            "enabled",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_service_providers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    offering_key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
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


class ResearchServiceOfferingRevision(Base):
    """Immutable request, result, price, SLA, sample, and logistics contract."""

    __tablename__ = "research_service_offering_revisions"
    __table_args__ = (
        UniqueConstraint(
            "offering_id",
            "revision",
            name="uq_research_service_offering_revision",
        ),
        UniqueConstraint(
            "offering_id",
            "service_version",
            name="uq_research_service_offering_version",
        ),
        CheckConstraint(
            "((base_price IS NULL AND currency IS NULL) OR "
            "(base_price >= 0 AND currency IS NOT NULL AND length(currency) = 3 "
            "AND currency = upper(currency)))",
            name="ck_research_service_offering_price_pair",
        ),
        CheckConstraint(
            "sla_hours IS NULL OR sla_hours BETWEEN 1 AND 87600",
            name="ck_research_service_offering_sla",
        ),
        CheckConstraint(
            "risk IN ('low', 'medium', 'high')",
            name="ck_research_service_offering_risk",
        ),
        Index(
            "ix_research_service_offering_revisions_offering_created",
            "offering_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    offering_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_service_offerings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    service_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    quote_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    base_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    currency: Mapped[str | None] = mapped_column(String(3))
    sla_hours: Mapped[int | None] = mapped_column()
    sample_requirements: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    logistics_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    terms: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    risk: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchServiceJob(Base):
    """A governed external-service order attached to one Research Action."""

    __tablename__ = "research_service_jobs"
    __table_args__ = (
        UniqueConstraint("action_id", name="uq_research_service_job_action"),
        CheckConstraint(
            "status IN ('blocked', 'awaiting_quote', 'awaiting_approval', 'ordered', "
            "'in_fulfillment', 'completed', 'failed', 'cancelled')",
            name="ck_research_service_job_status",
        ),
        CheckConstraint(
            "length(creation_digest) = 64",
            name="ck_research_service_job_creation_digest",
        ),
        CheckConstraint(
            "risk IN ('low', 'medium', 'high')",
            name="ck_research_service_job_risk",
        ),
        Index(
            "ix_research_service_jobs_offering_status",
            "service_offering_id",
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
    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_service_providers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    service_offering_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_service_offerings.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    service_offering_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_service_offering_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    service_offering_revision: Mapped[int] = mapped_column(nullable=False)
    service_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    offering_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    input_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    risk: Mapped[str] = mapped_column(String(16), nullable=False)
    quote_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    current_quote_revision: Mapped[int | None] = mapped_column()
    external_order_ref: Mapped[str] = mapped_column(
        String(255), nullable=False, default=""
    )
    provider_status: Mapped[str] = mapped_column(
        String(255), nullable=False, default=""
    )
    expected_completion_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actual_amount: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    error: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ResearchServiceJobStatus.AWAITING_QUOTE.value,
    )
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
    quote_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchServiceQuote(Base):
    """An immutable provider or catalog quote for one service job."""

    __tablename__ = "research_service_quotes"
    __table_args__ = (
        UniqueConstraint(
            "service_job_id", "revision", name="uq_research_service_quote_revision"
        ),
        CheckConstraint("amount >= 0", name="ck_research_service_quote_amount"),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_research_service_quote_currency",
        ),
        CheckConstraint(
            "source IN ('catalog', 'provider')",
            name="ck_research_service_quote_source",
        ),
        CheckConstraint(
            "length(quote_digest) = 64",
            name="ck_research_service_quote_digest",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    service_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_service_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    provider_quote_ref: Mapped[str] = mapped_column(
        String(255), nullable=False, default=""
    )
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terms: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    quote_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchServiceCustodyEvent(Base):
    """Append-only sample custody checkpoint for an approved service order."""

    __tablename__ = "research_service_custody_events"
    __table_args__ = (
        UniqueConstraint(
            "service_job_id",
            "sequence",
            name="uq_research_service_custody_sequence",
        ),
        CheckConstraint(
            "kind IN ('prepared', 'released_to_carrier', 'received_by_provider', "
            "'returned_to_lab', 'disposed_by_provider')",
            name="ck_research_service_custody_kind",
        ),
        CheckConstraint(
            "length(event_digest) = 64",
            name="ck_research_service_custody_digest",
        ),
        Index(
            "ix_research_service_custody_resource_created",
            "resource_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    service_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_service_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    container_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resource_containers.id", ondelete="RESTRICT")
    )
    from_party: Mapped[str] = mapped_column(String(255), nullable=False)
    to_party: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    carrier: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    tracking_ref: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    condition: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    event_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchServiceResultAsset(Base):
    __tablename__ = "research_service_result_assets"
    __table_args__ = (
        UniqueConstraint(
            "service_job_id",
            "data_asset_version_id",
            name="uq_research_service_result_asset",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    service_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_service_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    data_asset_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("data_asset_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


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
    source_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="manual"
    )
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
        UniqueConstraint("action_id", name="uq_research_resource_reservation_action"),
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


class ResearchResourceConsumption(Base):
    """Append-only link from an inventory reservation to actual Record use."""

    __tablename__ = "research_resource_consumptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["record_id", "record_version"],
            ["records.id", "records.version"],
            ondelete="RESTRICT",
            name="fk_research_resource_consumption_record",
        ),
        UniqueConstraint(
            "inventory_event_id",
            name="uq_research_resource_consumption_inventory_event",
        ),
        Index(
            "ix_research_resource_consumptions_reservation_created",
            "research_resource_reservation_id",
            "created_at",
        ),
        Index(
            "ix_research_resource_consumptions_record",
            "record_id",
            "record_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    research_resource_reservation_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_resource_reservations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inventory_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("inventory_events.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    record_id: Mapped[UUID] = mapped_column(nullable=False)
    record_version: Mapped[int] = mapped_column(nullable=False)
    field_path: Mapped[str] = mapped_column(String(512), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    remaining_quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    remaining_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
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


class ResearchInstrumentGateway(Base):
    """Lab-owned credential boundary for an on-premises Instrument Gateway."""

    __tablename__ = "research_instrument_gateways"
    __table_args__ = (
        UniqueConstraint("lab_id", "name", name="uq_research_instrument_gateway_name"),
        CheckConstraint(
            "length(token_digest) = 64",
            name="ck_research_instrument_gateway_token_digest",
        ),
        Index(
            "ix_research_instrument_gateways_lab_enabled",
            "lab_id",
            "enabled",
        ),
    )

    json_exclude_fields: ClassVar[list[str]] = ["token_digest"]

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    token_hint: Mapped[str] = mapped_column(String(16), nullable=False)
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
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchInstrumentCommand(Base):
    """One versioned, schema-bounded command allowed on one equipment Resource."""

    __tablename__ = "research_instrument_commands"
    __table_args__ = (
        UniqueConstraint(
            "gateway_id",
            "resource_id",
            "command_key",
            "command_version",
            name="uq_research_instrument_command_identity",
        ),
        CheckConstraint(
            "risk IN ('read_only', 'low', 'medium', 'high')",
            name="ck_research_instrument_command_risk",
        ),
        CheckConstraint(
            "timeout_seconds BETWEEN 1 AND 86400",
            name="ck_research_instrument_command_timeout",
        ),
        Index(
            "ix_research_instrument_commands_gateway_enabled",
            "gateway_id",
            "enabled",
        ),
        Index(
            "ix_research_instrument_commands_resource_enabled",
            "resource_id",
            "enabled",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    gateway_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_instrument_gateways.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    resource_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("resource_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    resource_revision: Mapped[int] = mapped_column(nullable=False)
    command_key: Mapped[str] = mapped_column(String(128), nullable=False)
    command_version: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    risk: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ResearchInstrumentRisk.MEDIUM.value
    )
    device_confirmation_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    timeout_seconds: Mapped[int] = mapped_column(nullable=False, default=3600)
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


class ResearchInstrumentJob(Base):
    """A version-pinned physical command leased to one Instrument Gateway."""

    __tablename__ = "research_instrument_jobs"
    __table_args__ = (
        UniqueConstraint("action_id", name="uq_research_instrument_job_action"),
        CheckConstraint(
            "status IN ('queued', 'leased', 'running', 'stop_requested', "
            "'completed', 'failed', 'cancelled', 'stopped')",
            name="ck_research_instrument_job_status",
        ),
        CheckConstraint(
            "lease_token_digest IS NULL OR length(lease_token_digest) = 64",
            name="ck_research_instrument_job_lease_digest",
        ),
        CheckConstraint(
            "risk IN ('read_only', 'low', 'medium', 'high')",
            name="ck_research_instrument_job_risk",
        ),
        CheckConstraint(
            "timeout_seconds BETWEEN 1 AND 86400",
            name="ck_research_instrument_job_timeout",
        ),
        Index(
            "ix_research_instrument_jobs_gateway_status_created",
            "gateway_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_research_instrument_jobs_booking_status",
            "equipment_booking_id",
            "status",
        ),
        Index(
            "ix_research_instrument_jobs_status_lease",
            "status",
            "lease_expires_at",
        ),
    )

    json_exclude_fields: ClassVar[list[str]] = ["lease_token_digest"]

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_actions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    gateway_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_instrument_gateways.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    command_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_instrument_commands.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    resource_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("resource_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    resource_revision: Mapped[int] = mapped_column(nullable=False)
    equipment_booking_id: Mapped[UUID] = mapped_column(
        ForeignKey("equipment_bookings.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    command_key: Mapped[str] = mapped_column(String(128), nullable=False)
    command_version: Mapped[str] = mapped_column(String(64), nullable=False)
    command_revision: Mapped[int] = mapped_column(nullable=False)
    arguments: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    input_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    risk: Mapped[str] = mapped_column(String(32), nullable=False)
    device_confirmation_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    timeout_seconds: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ResearchInstrumentJobStatus.QUEUED.value
    )
    lease_token_digest: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    device_confirmation: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    stop_reason: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stop_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchInstrumentGatewayAudit(Base):
    """Immutable configuration history without credential material."""

    __tablename__ = "research_instrument_gateway_audits"
    __table_args__ = (
        Index(
            "ix_research_instrument_gateway_audits_gateway_created",
            "gateway_id",
            "created_at",
        ),
        Index(
            "ix_research_instrument_gateway_audits_lab_created",
            "lab_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    gateway_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_instrument_gateways.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    command_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_instrument_commands.id", ondelete="SET NULL"), index=True
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
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
