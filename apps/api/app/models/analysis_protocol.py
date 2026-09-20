"""Reviewed, revisioned Protocol packages derived from published analysis methods."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AnalysisProtocolDraft(Base):
    __tablename__ = "analysis_protocol_drafts"
    __table_args__ = (
        UniqueConstraint(
            "created_by_user_id",
            "idempotency_key",
            name="uq_analysis_protocol_draft_request",
        ),
        CheckConstraint("revision >= 1", name="ck_analysis_protocol_draft_revision"),
        CheckConstraint(
            "state IN ('draft','reviewed','rejected','applied')",
            name="ck_analysis_protocol_draft_state",
        ),
        CheckConstraint(
            "request_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_protocol_draft_request_digest",
        ),
        CheckConstraint(
            "(target_protocol_id IS NULL) = (base_protocol_version_id IS NULL)",
            name="ck_analysis_protocol_draft_target_pair",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    method_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_analysis_methods.id", ondelete="RESTRICT"), index=True
    )
    target_protocol_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("protocols.id", ondelete="RESTRICT")
    )
    base_protocol_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("protocol_versions.id", ondelete="RESTRICT")
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    state: Mapped[str] = mapped_column(
        String(16), default="draft", server_default="draft"
    )
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnalysisProtocolDraftRevision(Base):
    __tablename__ = "analysis_protocol_draft_revisions"
    __table_args__ = (
        UniqueConstraint(
            "draft_id", "idempotency_key", name="uq_analysis_protocol_revision_request"
        ),
        CheckConstraint("revision >= 1", name="ck_analysis_protocol_revision_number"),
        CheckConstraint(
            "jsonb_typeof(files::jsonb) = 'object'",
            name="ck_analysis_protocol_revision_files",
        ),
        *(
            CheckConstraint(
                f"{field} ~ '^[0-9a-f]{{64}}$'",
                name=f"ck_analysis_protocol_revision_{field}",
            )
            for field in (
                "package_digest",
                "manifest_digest",
                "method_digest",
                "request_digest",
            )
        ),
    )

    draft_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_protocol_drafts.id", ondelete="RESTRICT"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    files: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    method_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnalysisProtocolDraftReview(Base):
    __tablename__ = "analysis_protocol_draft_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_id", "revision"],
            [
                "analysis_protocol_draft_revisions.draft_id",
                "analysis_protocol_draft_revisions.revision",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "draft_id", "revision", name="uq_analysis_protocol_review_revision"
        ),
        CheckConstraint("revision >= 1", name="ck_analysis_protocol_review_revision"),
        CheckConstraint(
            "decision IN ('reviewed','rejected')",
            name="ck_analysis_protocol_review_decision",
        ),
        CheckConstraint(
            "package_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_protocol_review_package_digest",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    draft_id: Mapped[UUID] = mapped_column(nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnalysisProtocolMethodLink(Base):
    __tablename__ = "analysis_protocol_method_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_id", "revision"],
            [
                "analysis_protocol_draft_revisions.draft_id",
                "analysis_protocol_draft_revisions.revision",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("draft_id", name="uq_analysis_protocol_link_draft"),
        CheckConstraint("revision >= 1", name="ck_analysis_protocol_link_revision"),
        CheckConstraint(
            "package_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_protocol_link_package_digest",
        ),
    )

    protocol_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocol_versions.id", ondelete="RESTRICT"), primary_key=True
    )
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id", ondelete="RESTRICT"), index=True
    )
    draft_id: Mapped[UUID] = mapped_column(nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    method_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_analysis_methods.id", ondelete="RESTRICT"), index=True
    )
    package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    applied_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
