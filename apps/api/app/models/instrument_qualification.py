"""Immutable, scope-limited human acceptance; never an execution permission."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class InstrumentQualification(Base):
    __tablename__ = "instrument_qualifications"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('simulation','read_only','controlled')",
            name="ck_instrument_qualification_scope",
        ),
        CheckConstraint(
            "outcome IN ('passed','failed')", name="ck_instrument_qualification_outcome"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    binding_id: Mapped[UUID] = mapped_column(
        ForeignKey("instrument_device_bindings.id", ondelete="RESTRICT"), index=True
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(16))
    report: Mapped[dict] = mapped_column(JSON)
    pins: Mapped[dict] = mapped_column(JSON)
    evidence_files: Mapped[list] = mapped_column(JSON)
    confirmation_digest: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    revoke_reason: Mapped[str | None] = mapped_column(Text)
