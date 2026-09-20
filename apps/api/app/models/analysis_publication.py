"""Explicit, immutable Evidence publications of selected private analysis output."""

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


class AnalysisEvidencePublication(Base):
    __tablename__ = "analysis_evidence_publications"
    __table_args__ = (
        UniqueConstraint(
            "created_by_user_id",
            "idempotency_key",
            name="uq_analysis_evidence_publication_request",
        ),
        UniqueConstraint(
            "evidence_id", name="uq_analysis_evidence_publication_evidence"
        ),
        CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_publication_digest"
        ),
        CheckConstraint(
            "source_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_publication_source_digest",
        ),
        CheckConstraint(
            "recipe_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_publication_recipe_digest",
        ),
        CheckConstraint(
            "result_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_publication_result_digest",
        ),
        CheckConstraint(
            "request_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_publication_request_digest",
        ),
        CheckConstraint(
            "(interpretation_revision_id IS NULL) = (interpretation_digest IS NULL)",
            name="ck_analysis_publication_interpretation_pair",
        ),
        CheckConstraint(
            "interpretation_digest IS NULL OR interpretation_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_publication_interpretation_digest",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    analysis_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    interpretation_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_interpretation_revisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    evidence_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_evidence.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    selection: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    recipe_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    result_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    interpretation_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
