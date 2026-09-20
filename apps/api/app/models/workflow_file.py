"""Immutable, source-authorized logical file references for fixed Workflows."""

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


class WorkflowFileBinding(Base):
    __tablename__ = "workflow_file_bindings"
    __table_args__ = (
        UniqueConstraint("action_id", "binding_id", name="uq_workflow_file_binding"),
        CheckConstraint(
            "(source_kind IN ('record', 'compute') AND source_action_id IS NOT NULL AND asset_input_id IS NULL) OR "
            "(source_kind = 'data_asset' AND source_action_id IS NULL AND asset_input_id IS NOT NULL AND source_file_id IS NULL)",
            name="ck_workflow_file_source",
        ),
        CheckConstraint("digest ~ '^[0-9a-f]{64}$'", name="ck_workflow_file_digest"),
    )

    file_id: Mapped[UUID] = mapped_column(
        ForeignKey("airalogy_files.id", ondelete="RESTRICT"), primary_key=True
    )
    workflow_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_revisions.id", ondelete="RESTRICT")
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="RESTRICT"), index=True
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="RESTRICT"), index=True
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_actions.id", ondelete="RESTRICT"), index=True
    )
    binding_id: Mapped[str] = mapped_column(String(64))
    source_action_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_actions.id", ondelete="RESTRICT")
    )
    asset_input_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workflow_run_asset_inputs.id", ondelete="RESTRICT"), index=True
    )
    source_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("airalogy_files.id", ondelete="RESTRICT"), index=True
    )
    blob_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_file_blobs.id", ondelete="RESTRICT")
    )
    source_kind: Mapped[str] = mapped_column(String(16))
    source_ref: Mapped[dict] = mapped_column(JSON)
    snapshot: Mapped[dict] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WorkflowFileExportReference(Base):
    """The exact protected attachments in a generated export, even after revisions."""

    __tablename__ = "workflow_file_export_references"
    export_id: Mapped[UUID] = mapped_column(
        ForeignKey("record_exports.id", ondelete="CASCADE"), primary_key=True
    )
    file_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_file_bindings.file_id", ondelete="RESTRICT"),
        primary_key=True,
    )
