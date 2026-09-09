"""Persisted integration work, deliberately separate from execution authority."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class InstrumentIntegrationDraft(Base):
    __tablename__ = "instrument_integration_drafts"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_integration_revision"),
        CheckConstraint("length(content_digest) = 64", name="ck_integration_digest"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    gateway_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_instrument_gateways.id", ondelete="CASCADE"), index=True
    )
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT")
    )
    resource_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("resource_revisions.id", ondelete="RESTRICT")
    )
    goal: Mapped[str] = mapped_column(Text)
    bundle: Mapped[dict] = mapped_column(JSON)
    report: Mapped[dict] = mapped_column(JSON)
    content_digest: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(default=1)
    updated_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
