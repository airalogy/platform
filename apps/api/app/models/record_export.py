from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RecordExportScope(StrEnum):
    LAB = "lab"
    PROJECT = "project"
    PROTOCOL = "protocol"


class RecordExportFormat(StrEnum):
    AIRA = "aira"
    JSONL = "jsonl"
    CSV = "csv"


class RecordExportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class RecordExportAuditAction(StrEnum):
    REQUESTED = "requested"
    STARTED = "started"
    COMPLETED = "completed"
    DOWNLOADED = "downloaded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class RecordExport(Base):
    __tablename__ = "record_exports"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('lab', 'project', 'protocol')",
            name="ck_record_exports_scope_type",
        ),
        CheckConstraint(
            "export_format IN ('aira', 'jsonl', 'csv')",
            name="ck_record_exports_format",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', "
            "'cancelled', 'expired')",
            name="ck_record_exports_status",
        ),
        CheckConstraint(
            "(scope_type = 'lab' AND project_id IS NULL AND protocol_id IS NULL) "
            "OR (scope_type = 'project' AND project_id IS NOT NULL "
            "AND protocol_id IS NULL) "
            "OR (scope_type = 'protocol' AND project_id IS NOT NULL "
            "AND protocol_id IS NOT NULL)",
            name="ck_record_exports_scope_target",
        ),
        Index("ix_record_exports_user_created", "requested_by_user_id", "created_at"),
        Index("ix_record_exports_lab_created", "lab_id", "created_at"),
        Index("ix_record_exports_status_expires", "status", "expires_at"),
        UniqueConstraint(
            "requested_by_user_id",
            "client_idempotency_key",
            name="uq_record_exports_user_idempotency",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
        index=True,
    )
    protocol_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
        index=True,
    )
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    export_format: Mapped[str] = mapped_column(String(16), nullable=False)
    include_revision_history: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    include_attachments: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    options: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    client_idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RecordExportStatus.PENDING.value
    )
    progress_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    protocol_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attachment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attachment_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_backend: Mapped[str | None] = mapped_column(String(32), nullable=True)
    output_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    output_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    output_content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    output_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RecordExportAudit(Base):
    __tablename__ = "record_export_audits"
    __table_args__ = (
        UniqueConstraint(
            "export_id", "sequence", name="uq_record_export_audit_sequence"
        ),
        Index("ix_record_export_audits_lab_created", "lab_id", "created_at"),
        Index("ix_record_export_audits_export_created", "export_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    export_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
