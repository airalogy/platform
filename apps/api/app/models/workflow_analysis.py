"""Explicit Project method publications and typed links to ordinary analyses."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class WorkflowAnalysisMethod(Base):
    """One immutable, explicitly shared method, never its private input history."""

    __tablename__ = "workflow_analysis_methods"
    __table_args__ = (
        UniqueConstraint(
            "created_by_user_id",
            "idempotency_key",
            name="uq_workflow_analysis_method_request",
        ),
        CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$'", name="ck_workflow_analysis_method_digest"
        ),
        CheckConstraint(
            "source_schema_digest ~ '^[0-9a-f]{64}$'",
            name="ck_workflow_analysis_method_schema",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id", ondelete="RESTRICT")
    )
    protocol_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocol_versions.id", ondelete="RESTRICT")
    )
    source_pipeline_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_pipeline_revisions.id", ondelete="RESTRICT")
    )
    source_method_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    recipe: Mapped[dict] = mapped_column(JSON, nullable=False)
    input_fields: Mapped[list] = mapped_column(JSON, nullable=False)
    compute_contract: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    source_schema_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ResearchAnalysisAction(Base):
    """Governed Workflow occurrence; computation still belongs to AnalysisRun."""

    __tablename__ = "research_analysis_actions"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", name="uq_research_analysis_action_run"),
        UniqueConstraint(
            "analysis_preview_id", name="uq_research_analysis_action_preview"
        ),
        CheckConstraint(
            "source_digest IS NULL OR source_digest ~ '^[0-9a-f]{64}$'",
            name="ck_research_analysis_source_digest",
        ),
        CheckConstraint(
            "resolution_digest IS NULL OR resolution_digest ~ '^[0-9a-f]{64}$'",
            name="ck_research_analysis_resolution_digest",
        ),
        CheckConstraint(
            "preview_digest IS NULL OR preview_digest ~ '^[0-9a-f]{64}$'",
            name="ck_research_analysis_preview_digest",
        ),
    )

    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_actions.id", ondelete="CASCADE"), primary_key=True
    )
    method_publication_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_analysis_methods.id", ondelete="RESTRICT")
    )
    analysis_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="RESTRICT")
    )
    analysis_preview_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_previews.id", ondelete="RESTRICT")
    )
    input_snapshot: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    source_digest: Mapped[str | None] = mapped_column(String(64))
    resolution_digest: Mapped[str | None] = mapped_column(String(64))
    preview_digest: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
