"""Versioned research data, evidence, and scientific claims."""

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


class DataAssetKind(StrEnum):
    FILE = "file"
    TABLE = "table"
    IMAGE = "image"
    MODEL = "model"
    ARCHIVE = "archive"
    EXTERNAL = "external"


class DataAssetStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class EvidenceKind(StrEnum):
    OBSERVATION = "observation"
    MEASUREMENT = "measurement"
    ANALYSIS = "analysis"
    CITATION = "citation"
    VALIDATION = "validation"


class EvidenceQuality(StrEnum):
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"


class ClaimState(StrEnum):
    SUGGESTED = "suggested"
    DRAFT = "draft"
    REVIEWED = "reviewed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class ClaimEvidenceRelation(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXT = "context"


class DataAsset(Base):
    __tablename__ = "data_assets"
    __table_args__ = (
        Index("ix_data_assets_project_status", "project_id", "status"),
        Index("ix_data_assets_task_created", "task_id", "created_at"),
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
    task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DataAssetStatus.DRAFT.value
    )
    current_version: Mapped[int] = mapped_column(nullable=False, default=1)
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


class DataAssetVersion(Base):
    __tablename__ = "data_asset_versions"
    __table_args__ = (
        UniqueConstraint("data_asset_id", "version", name="uq_data_asset_version"),
        CheckConstraint(
            "(research_file_id IS NOT NULL AND external_uri = '') OR "
            "(research_file_id IS NULL AND external_uri <> '')",
            name="ck_data_asset_version_source",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    data_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(nullable=False)
    research_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_files.id", ondelete="RESTRICT"), index=True
    )
    external_uri: Mapped[str] = mapped_column(Text, nullable=False, default="")
    media_type: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    checksum: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    byte_size: Mapped[int | None] = mapped_column()
    data_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version_metadata: Mapped[dict] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    source: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchEvidence(Base):
    __tablename__ = "research_evidence"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "artifact_type",
            "artifact_id",
            "artifact_version",
            "kind",
            name="uq_research_evidence_artifact",
        ),
        Index("ix_research_evidence_task_quality", "task_id", "quality_state"),
        Index("ix_research_evidence_action", "action_id"),
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
        ForeignKey("research_actions.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    quality_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EvidenceQuality.PENDING.value
    )
    validation_report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchClaim(Base):
    __tablename__ = "research_claims"
    __table_args__ = (Index("ix_research_claims_task_state", "task_id", "state"),)

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ClaimState.DRAFT.value
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    uncertainty: Mapped[str] = mapped_column(Text, nullable=False, default="")
    generated_by: Mapped[str] = mapped_column(
        String(32), nullable=False, default="human"
    )
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_claims.id", ondelete="SET NULL")
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


class ResearchClaimRevision(Base):
    __tablename__ = "research_claim_revisions"
    __table_args__ = (
        UniqueConstraint("claim_id", "revision", name="uq_research_claim_revision"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    claim_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchClaimEvidence(Base):
    __tablename__ = "research_claim_evidence"
    __table_args__ = (
        UniqueConstraint("claim_id", "evidence_id", name="uq_research_claim_evidence"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    claim_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
