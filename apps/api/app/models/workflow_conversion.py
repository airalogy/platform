"""Private, immutable receipts for explicitly copying legacy Workflow structure."""

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


class WorkflowLegacyConversion(Base):
    __tablename__ = "workflow_legacy_conversions"
    __table_args__ = (
        UniqueConstraint(
            "created_by_user_id", "idempotency_key", name="uq_workflow_legacy_request"
        ),
        UniqueConstraint("workflow_revision_id", name="uq_workflow_legacy_revision"),
        CheckConstraint(
            "source_digest ~ '^[0-9a-f]{64}$'", name="ck_workflow_legacy_source_digest"
        ),
        CheckConstraint(
            "request_digest ~ '^[0-9a-f]{64}$'",
            name="ck_workflow_legacy_request_digest",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    source_workflow_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocol_workflows.id", ondelete="RESTRICT"), index=True
    )
    definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE")
    )
    workflow_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_revisions.id", ondelete="CASCADE")
    )
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    node_mapping: Mapped[list] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
