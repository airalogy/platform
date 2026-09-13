"""Private, reproducible Record analyses and independently versioned recipes.

Scope columns identify the source; they do not grant read access. Services must
authorize the owner and all source Records before returning or executing data.
Recipe revisions, previews, and confirmed source snapshots are immutable through
the service boundary; analysis state and results are persisted by the job worker.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
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


class AnalysisRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisPipeline(Base):
    __tablename__ = "analysis_pipelines"
    __table_args__ = (
        CheckConstraint("current_revision >= 1", name="ck_analysis_pipeline_revision"),
        Index(
            "ix_analysis_pipelines_owner_protocol_created",
            "created_by_user_id",
            "protocol_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    current_revision: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AnalysisPipelineRevision(Base):
    __tablename__ = "analysis_pipeline_revisions"
    __table_args__ = (
        UniqueConstraint(
            "pipeline_id", "revision", name="uq_analysis_pipeline_revision"
        ),
        CheckConstraint("revision >= 1", name="ck_analysis_recipe_revision"),
        CheckConstraint(
            "recipe_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_recipe_digest"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    pipeline_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_pipelines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    recipe: Mapped[dict] = mapped_column(JSON, nullable=False)
    recipe_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_selection: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        UniqueConstraint(
            "created_by_user_id",
            "client_idempotency_key",
            name="uq_analysis_run_owner_idempotency",
        ),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','cancelled')",
            name="ck_analysis_run_status",
        ),
        CheckConstraint(
            "rerun_of_id IS NULL OR rerun_of_id <> id", name="ck_analysis_run_not_self"
        ),
        CheckConstraint(
            "source_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_run_source_digest"
        ),
        CheckConstraint(
            "recipe_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_run_recipe_digest"
        ),
        CheckConstraint(
            "preview_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_run_preview_digest"
        ),
        CheckConstraint(
            "result_digest IS NULL OR result_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_run_result_digest",
        ),
        CheckConstraint(
            "(result IS NULL) = (result_digest IS NULL)",
            name="ck_analysis_run_result_pair",
        ),
        Index(
            "ix_analysis_runs_owner_protocol_created",
            "created_by_user_id",
            "protocol_id",
            "created_at",
        ),
        Index("ix_analysis_runs_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    pipeline_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_pipeline_revisions.id", ondelete="RESTRICT"), index=True
    )
    rerun_of_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="RESTRICT"), index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recipe: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_selection: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    ai_provenance: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    recipe_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    preview_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    client_idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AnalysisRunStatus.PENDING.value
    )
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    result_digest: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("persistent_jobs.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalysisPreview(Base):
    __tablename__ = "analysis_previews"
    __table_args__ = (
        CheckConstraint(
            "source_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_preview_source_digest"
        ),
        CheckConstraint(
            "recipe_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_preview_recipe_digest"
        ),
        CheckConstraint(
            "preview_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_preview_digest"
        ),
        Index("ix_analysis_previews_owner_expires", "created_by_user_id", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    pipeline_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_pipeline_revisions.id", ondelete="RESTRICT"), index=True
    )
    rerun_of_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="RESTRICT"), index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recipe: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_selection: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    recipe_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    preview_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    ai_provenance: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
