"""Exact immutable DataAsset file inputs; an input is not an executed Action."""

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


class WorkflowRunAssetInput(Base):
    __tablename__ = "workflow_run_asset_inputs"
    __table_args__ = (
        UniqueConstraint("run_id", "input_id", name="uq_workflow_run_asset_input"),
        CheckConstraint(
            "input_id ~ '^[a-z][a-z0-9_-]{0,63}$'", name="ck_workflow_asset_input_id"
        ),
        CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$'", name="ck_workflow_asset_input_digest"
        ),
        CheckConstraint(
            "source_digest ~ '^[0-9a-f]{64}$'", name="ck_workflow_asset_source_digest"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    input_id: Mapped[str] = mapped_column(String(64))
    workflow_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_revisions.id", ondelete="RESTRICT")
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="RESTRICT"), index=True
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="RESTRICT"), index=True
    )
    data_asset_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("data_asset_versions.id", ondelete="RESTRICT"), index=True
    )
    research_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_files.id", ondelete="RESTRICT"), index=True
    )
    blob_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_file_blobs.id", ondelete="RESTRICT"), index=True
    )
    snapshot: Mapped[dict] = mapped_column(JSON)
    source_digest: Mapped[str] = mapped_column(String(64))
    digest: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
