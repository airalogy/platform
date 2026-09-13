"""Project-scoped Workflow definitions, immutable revisions and runtime lineage."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_workflow_definition_revision"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkflowRevision(Base):
    __tablename__ = "workflow_revisions"
    __table_args__ = (
        UniqueConstraint("definition_id", "revision", name="uq_workflow_revision"),
        UniqueConstraint(
            "created_by_user_id", "idempotency_key", name="uq_workflow_revision_request"
        ),
        CheckConstraint("revision >= 1", name="ck_workflow_revision_number"),
        CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$'", name="ck_workflow_revision_digest"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), index=True
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    graph: Mapped[dict] = mapped_column(JSON, nullable=False)
    pins: Mapped[list] = mapped_column(JSON, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WorkflowRunBinding(Base):
    """An execution is an ordinary ResearchRun, never another Workflow engine."""

    __tablename__ = "workflow_run_bindings"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_workflow_run_binding"),
        UniqueConstraint(
            "created_by_user_id", "idempotency_key", name="uq_workflow_run_request"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    workflow_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_revisions.id", ondelete="RESTRICT"), index=True
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE")
    )
    environment_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WorkflowNodeResolution(Base):
    """Immutable decisions and resolved inputs before downstream approval."""

    __tablename__ = "workflow_node_resolutions"
    __table_args__ = (
        UniqueConstraint("action_id", name="uq_workflow_node_resolution_action"),
        UniqueConstraint("run_id", "node_id", name="uq_workflow_node_resolution_node"),
        CheckConstraint(
            "state IN ('ready', 'branch_not_selected', 'blocked', 'failed')",
            name="ck_workflow_node_resolution_state",
        ),
        CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$'", name="ck_workflow_node_resolution_digest"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    workflow_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_revisions.id", ondelete="RESTRICT")
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), index=True
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_actions.id", ondelete="CASCADE")
    )
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    initial_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    receipt: Mapped[dict] = mapped_column(JSON, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
