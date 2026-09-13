"""Private, digest-bound model requests; generation never grants execution."""

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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AnalysisAIRequestKind(StrEnum):
    DRAFT = "draft"
    COMPUTE_DRAFT = "compute_draft"
    INTERPRETATION = "interpretation"


class AnalysisAIRequestState(StrEnum):
    GENERATING = "generating"
    GENERATED = "generated"
    FAILED = "failed"


class AnalysisAIRequest(Base):
    __tablename__ = "analysis_ai_requests"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('draft','compute_draft','interpretation')",
            name="ck_analysis_ai_kind",
        ),
        CheckConstraint(
            "(kind IN ('draft','compute_draft') AND analysis_run_id IS NULL) OR "
            "(kind = 'interpretation' AND analysis_run_id IS NOT NULL)",
            name="ck_analysis_ai_run_kind",
        ),
        CheckConstraint(
            "state IN ('generating','generated','failed')",
            name="ck_analysis_ai_state",
        ),
        CheckConstraint(
            "state <> 'generated' OR output IS NOT NULL",
            name="ck_analysis_ai_generated_output",
        ),
        CheckConstraint(
            "(output IS NULL) = (output_digest IS NULL)",
            name="ck_analysis_ai_output_pair",
        ),
        CheckConstraint(
            "previous_request_id IS NULL OR previous_request_id <> id",
            name="ck_analysis_ai_not_self",
        ),
        CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_ai_request_fingerprint",
        ),
        CheckConstraint(
            "input_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_ai_input_digest"
        ),
        CheckConstraint(
            "source_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_ai_source_digest"
        ),
        CheckConstraint(
            "output_digest IS NULL OR output_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_ai_output_digest",
        ),
        Index(
            "ix_analysis_ai_requests_owner_protocol_created",
            "created_by_user_id",
            "protocol_id",
            "created_at",
        ),
        Index("ix_analysis_ai_requests_state_deadline", "state", "deadline"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="RESTRICT"), index=True
    )
    previous_request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_ai_requests.id", ondelete="RESTRICT"), index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    operation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    source_selection: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_manifest: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    input_context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AnalysisAIRequestState.GENERATING.value
    )
    output: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    output_digest: Mapped[str | None] = mapped_column(String(64))
    # Only service-defined safe error codes; never a provider exception/payload.
    error: Mapped[str | None] = mapped_column(String(64))
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
