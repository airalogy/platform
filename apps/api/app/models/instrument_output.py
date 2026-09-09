"""Pinned, private instrument file intake and immutable Record associations."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class InstrumentOutputBatch(Base):
    __tablename__ = "instrument_output_batches"

    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_instrument_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    plan: Mapped[dict] = mapped_column(JSON)
    lineage: Mapped[dict] = mapped_column(JSON)
    capture: Mapped[dict | None] = mapped_column(JSON)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InstrumentOutput(Base):
    __tablename__ = "instrument_outputs"
    __table_args__ = (
        UniqueConstraint("job_id", "name", name="uq_instrument_output_name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("instrument_output_batches.job_id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(240))
    research_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_files.id", ondelete="RESTRICT"), index=True
    )
    data_asset_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_asset_versions.id", ondelete="RESTRICT")
    )
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InstrumentOutputAssociation(Base):
    __tablename__ = "instrument_output_associations"
    __table_args__ = (
        UniqueConstraint(
            "output_id", "revision", name="uq_instrument_output_association_revision"
        ),
        CheckConstraint(
            "revision > 0", name="ck_instrument_output_association_revision"
        ),
        ForeignKeyConstraint(
            ["record_id", "record_version"],
            ["records.id", "records.version"],
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column()
    output_id: Mapped[UUID] = mapped_column(
        ForeignKey("instrument_outputs.id", ondelete="CASCADE"), index=True
    )
    record_id: Mapped[UUID] = mapped_column()
    record_version: Mapped[int] = mapped_column()
    record_hash: Mapped[str] = mapped_column(String(128))
    sample_reference: Mapped[str] = mapped_column(String(1024))
    confirmation_digest: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
