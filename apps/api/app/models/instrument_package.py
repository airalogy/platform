"""Lab-private immutable adapter content; source review is not device qualification."""

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


class InstrumentAdapterRelease(Base):
    __tablename__ = "instrument_adapter_releases"
    __table_args__ = (
        UniqueConstraint(
            "lab_id",
            "package_key",
            "package_version",
            name="uq_instrument_adapter_version",
        ),
        CheckConstraint(
            "state IN ('imported','approved','revoked')",
            name="ck_instrument_adapter_state",
        ),
        CheckConstraint("revision >= 1", name="ck_instrument_adapter_revision"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), index=True
    )
    research_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_files.id", ondelete="RESTRICT")
    )
    package_key: Mapped[str] = mapped_column(String(128))
    package_version: Mapped[str] = mapped_column(String(64))
    archive_digest: Mapped[str] = mapped_column(String(64))
    manifest_digest: Mapped[str] = mapped_column(String(64))
    inspection: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(16), default="imported")
    revision: Mapped[int] = mapped_column(default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InstrumentAdapterReleaseAudit(Base):
    __tablename__ = "instrument_adapter_release_audits"
    __table_args__ = (
        UniqueConstraint(
            "release_id", "revision", name="uq_instrument_adapter_audit_revision"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    release_id: Mapped[UUID] = mapped_column(
        ForeignKey("instrument_adapter_releases.id", ondelete="CASCADE"), index=True
    )
    revision: Mapped[int]
    action: Mapped[str] = mapped_column(String(32))
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reason: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
