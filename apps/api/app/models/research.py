"""Durable research-task orchestration models.

The shared action table owns orchestration state. Typed tables keep scientific,
human, approval, and artifact semantics out of an unbounded JSON blob.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
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


class ResearchTaskStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    REVIEW_REQUIRED = "review_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class ResearchRunStatus(StrEnum):
    DRAFT = "draft"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_FOR_HUMAN = "waiting_for_human"
    WAITING_FOR_TOOL = "waiting_for_tool"
    WAITING_FOR_INSTRUMENT = "waiting_for_instrument"
    WAITING_FOR_COMPUTE = "waiting_for_compute"
    WAITING_FOR_EVENT = "waiting_for_event"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    VALIDATING = "validating"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchActionKind(StrEnum):
    PROTOCOL_RUN = "protocol_run"
    TOOL_JOB = "tool_job"
    HUMAN_WORK_ITEM = "human_work_item"
    INSTRUMENT_JOB = "instrument_job"
    COMPUTE_JOB = "compute_job"
    EXTERNAL_SERVICE_JOB = "external_service_job"
    APPROVAL_REQUEST = "approval_request"
    RESOURCE_RESERVATION = "resource_reservation"
    WAIT_EVENT = "wait_event"


class ResearchActionStatus(StrEnum):
    BLOCKED = "blocked"
    PROPOSED = "proposed"
    APPROVED = "approved"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    SUBMITTED = "submitted"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class HumanWorkItemStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    CHANGES_REQUESTED = "changes_requested"
    CANCELLED = "cancelled"


class ResearchApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ScientificOutcome(StrEnum):
    SUPPORTS_HYPOTHESIS = "supports_hypothesis"
    CONTRADICTS_HYPOTHESIS = "contradicts_hypothesis"
    INCONCLUSIVE = "inconclusive"
    UNEXPECTED = "unexpected"
    NOT_APPLICABLE = "not_applicable"


class ResearchTaskOutcome(StrEnum):
    GOAL_MET = "goal_met"
    GOAL_NOT_MET_BUT_CONCLUSIVE = "goal_not_met_but_conclusive"
    INCONCLUSIVE = "inconclusive"
    BLOCKED_MISSING_CAPABILITY = "blocked_missing_capability"
    STOPPED_BUDGET = "stopped_budget"
    STOPPED_TIME = "stopped_time"
    STOPPED_SAFETY = "stopped_safety"
    CANCELLED = "cancelled"
    EXECUTION_FAILED = "execution_failed"


class ResearchTask(Base):
    __tablename__ = "research_tasks"
    __table_args__ = (
        CheckConstraint(
            "((budget_limit IS NULL AND budget_currency IS NULL) OR "
            "(budget_limit > 0 AND budget_currency IS NOT NULL AND "
            "length(budget_currency) = 3 AND "
            "budget_currency = upper(budget_currency)))",
            name="ck_research_tasks_budget_pair",
        ),
        Index("ix_research_tasks_project_status", "project_id", "status"),
        Index("ix_research_tasks_owner_status", "owner_user_id", "status"),
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
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    success_criteria: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    stop_conditions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    autonomy_level: Mapped[str] = mapped_column(
        String(32), nullable=False, default="assisted"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ResearchTaskStatus.DRAFT.value
    )
    outcome: Mapped[str | None] = mapped_column(String(64))
    scientific_outcome: Mapped[str | None] = mapped_column(String(64))
    conclusion: Mapped[str] = mapped_column(Text, nullable=False, default="")
    result_package: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ai_model: Mapped[str | None] = mapped_column(String(128))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    budget_limit: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    budget_currency: Mapped[str | None] = mapped_column(String(3))
    owner_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
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
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchTaskProtocol(Base):
    __tablename__ = "research_task_protocols"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "position", name="uq_research_task_protocol_position"
        ),
        UniqueConstraint(
            "task_id", "protocol_version_id", name="uq_research_task_protocol_version"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    protocol_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocol_versions.id", ondelete="RESTRICT"), nullable=False
    )
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchTaskKnowledge(Base):
    __tablename__ = "research_task_knowledge"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "position", name="uq_research_task_knowledge_position"
        ),
        UniqueConstraint(
            "task_id", "knowledge_item_id", name="uq_research_task_knowledge_item"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    knowledge_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    knowledge_revision: Mapped[int] = mapped_column(nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchTaskResourceRequirement(Base):
    __tablename__ = "research_task_resource_requirements"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "position",
            name="uq_research_task_resource_requirement_position",
        ),
        UniqueConstraint(
            "task_id",
            "resource_type_id",
            name="uq_research_task_resource_requirement_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("resource_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    resource_type_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("resource_type_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    resource_type_revision: Mapped[int] = mapped_column(nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchTaskServiceOffering(Base):
    """An immutable external-service contract pinned into a Research Environment."""

    __tablename__ = "research_task_service_offerings"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "position", name="uq_research_task_service_offering_position"
        ),
        UniqueConstraint(
            "task_id",
            "service_offering_id",
            name="uq_research_task_service_offering",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False, index=True
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
    position: Mapped[int] = mapped_column(nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchTaskComputeEnvironment(Base):
    """An exact compute-environment revision pinned into a Research Task."""

    __tablename__ = "research_task_compute_environments"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "position", name="uq_research_task_compute_environment_position"
        ),
        UniqueConstraint(
            "task_id",
            "compute_environment_id",
            name="uq_research_task_compute_environment",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    compute_environment_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_compute_environments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    compute_environment_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_compute_environment_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    compute_environment_revision: Mapped[int] = mapped_column(nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchRun(Base):
    __tablename__ = "research_runs"
    __table_args__ = (
        UniqueConstraint("task_id", "run_number", name="uq_research_run_number"),
        Index("ix_research_runs_task_status", "task_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ResearchRunStatus.DRAFT.value
    )
    plan_version: Mapped[int] = mapped_column(nullable=False, default=0)
    advance_generation: Mapped[int] = mapped_column(nullable=False, default=0)
    environment_snapshot: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    aira_state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_package: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    legacy_workflow_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("protocol_workflows.id", ondelete="SET NULL"), unique=True
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requested_by_user_id: Mapped[UUID] = mapped_column(
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
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchResultPackageSnapshot(Base):
    """Append-only, human-finalized result package for one Research Run."""

    __tablename__ = "research_result_package_snapshots"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_research_result_package_snapshot_run"),
        CheckConstraint(
            "task_revision > 0", name="ck_research_result_package_task_revision"
        ),
        CheckConstraint(
            "length(digest) = 64", name="ck_research_result_package_digest"
        ),
        Index(
            "ix_research_result_package_task_finalized",
            "task_id",
            "finalized_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    task_revision: Mapped[int] = mapped_column(nullable=False)
    schema_version: Mapped[str] = mapped_column(String(96), nullable=False)
    package: Mapped[dict] = mapped_column(JSON, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    finalized_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    finalized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchPlanVersion(Base):
    __tablename__ = "research_plan_versions"
    __table_args__ = (
        UniqueConstraint("run_id", "version", name="uq_research_plan_version"),
        Index("ix_research_plan_versions_run_created", "run_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    plan: Mapped[dict] = mapped_column(JSON, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchReviewRecommendation(Base):
    """Immutable advisory review of one exact Research Task result context."""

    __tablename__ = "research_review_recommendations"
    __table_args__ = (
        CheckConstraint(
            "recommendation IN ('accept', 'revise', 'collect_more_evidence')",
            name="ck_research_review_recommendation",
        ),
        CheckConstraint(
            "recommended_task_outcome IN "
            "('goal_met', 'goal_not_met_but_conclusive', 'inconclusive', "
            "'blocked_missing_capability', 'stopped_budget', 'stopped_time', "
            "'stopped_safety', 'cancelled')",
            name="ck_research_review_task_outcome",
        ),
        CheckConstraint(
            "recommended_scientific_outcome IN "
            "('supports_hypothesis', 'contradicts_hypothesis', 'inconclusive', "
            "'unexpected', 'not_applicable')",
            name="ck_research_review_scientific_outcome",
        ),
        UniqueConstraint(
            "task_id",
            "context_digest",
            "model_name",
            name="uq_research_review_context_model",
        ),
        Index(
            "ix_research_review_task_created",
            "task_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_runs.id", ondelete="SET NULL"), index=True
    )
    task_revision: Mapped[int] = mapped_column(nullable=False)
    context_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    recommendation: Mapped[str] = mapped_column(String(32), nullable=False)
    recommended_task_outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    recommended_scientific_outcome: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_evidence_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    contradicting_evidence_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    uncertainties: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing_checks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risk_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchAction(Base):
    __tablename__ = "research_actions"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_research_action_sequence"),
        UniqueConstraint(
            "run_id", "idempotency_key", name="uq_research_action_idempotency"
        ),
        Index("ix_research_actions_run_status", "run_id", "status"),
        Index("ix_research_actions_assignee_status", "assignee_user_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(nullable=False)
    plan_version: Mapped[int] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ResearchActionStatus.PROPOSED.value
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    executor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    assignee_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    input_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    requirements: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    policy_decision: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ask"
    )
    preview_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchActionDependency(Base):
    __tablename__ = "research_action_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "action_id", "depends_on_action_id", name="uq_research_action_dependency"
        ),
        CheckConstraint(
            "action_id <> depends_on_action_id",
            name="ck_research_action_dependency_not_self",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_actions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    depends_on_action_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_actions.id", ondelete="CASCADE"), nullable=False
    )
    condition: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ResearchProtocolRun(Base):
    __tablename__ = "research_protocol_runs"
    __table_args__ = (
        UniqueConstraint("action_id", name="uq_research_protocol_run_action"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_actions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    protocol_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocol_versions.id", ondelete="RESTRICT"), nullable=False
    )
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    initial_values: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    record_id: Mapped[UUID | None] = mapped_column(index=True)
    record_version: Mapped[int | None] = mapped_column()
    validation_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    validation_report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ResearchHumanWorkItem(Base):
    __tablename__ = "research_human_work_items"
    __table_args__ = (
        UniqueConstraint("action_id", name="uq_research_human_work_item_action"),
        Index("ix_research_work_items_assignee_status", "assignee_user_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_actions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assignee_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=HumanWorkItemStatus.OPEN.value
    )
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    submission_contract: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    submission: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    record_id: Mapped[UUID | None] = mapped_column(index=True)
    record_version: Mapped[int | None] = mapped_column()
    validation_issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchApproval(Base):
    __tablename__ = "research_approvals"
    __table_args__ = (
        Index("ix_research_approvals_action_status", "action_id", "status"),
        Index("ix_research_approvals_approver_status", "approver_user_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_actions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approver_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ResearchApprovalStatus.PENDING.value
    )
    preview_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decision_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchEvent(Base):
    __tablename__ = "research_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_research_event_idempotency"),
        Index("ix_research_events_task_created", "task_id", "created_at"),
        Index("ix_research_events_run_created", "run_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), index=True
    )
    action_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_actions.id", ondelete="CASCADE"), index=True
    )
    work_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_human_work_items.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(96), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchArtifactLink(Base):
    __tablename__ = "research_artifact_links"
    __table_args__ = (
        UniqueConstraint(
            "action_id",
            "artifact_type",
            "artifact_id",
            "artifact_version",
            "relation",
            name="uq_research_artifact_link",
        ),
        Index("ix_research_artifact_links_task_type", "task_id", "artifact_type"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), index=True
    )
    action_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_actions.id", ondelete="CASCADE"), index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    relation: Mapped[str] = mapped_column(
        String(64), nullable=False, default="produced"
    )
    link_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
