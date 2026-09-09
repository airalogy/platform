"""Immutable active-version grants and per-job version pins."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class InstrumentActivation(Base):
    __tablename__ = "instrument_activations"
    __table_args__ = tuple(
        Index(
            f"uq_instrument_activation_current_{scope}",
            f"{scope}_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        )
        for scope in ("gateway", "resource")
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    binding_id: Mapped[UUID] = mapped_column(
        ForeignKey("instrument_device_bindings.id", ondelete="RESTRICT"), index=True
    )
    qualification_id: Mapped[UUID] = mapped_column(
        ForeignKey("instrument_qualifications.id", ondelete="RESTRICT")
    )
    lab_id: Mapped[UUID] = mapped_column(ForeignKey("labs.id", ondelete="CASCADE"))
    gateway_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_instrument_gateways.id", ondelete="RESTRICT")
    )
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT")
    )
    authorization_digest: Mapped[str] = mapped_column(String(64))
    plan: Mapped[dict] = mapped_column(JSON)
    commands: Mapped[list] = mapped_column(JSON)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    revoke_reason: Mapped[str | None] = mapped_column(Text)


class InstrumentJobActivation(Base):
    __tablename__ = "instrument_job_activations"
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_instrument_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    activation_id: Mapped[UUID] = mapped_column(
        ForeignKey("instrument_activations.id", ondelete="RESTRICT"), index=True
    )
    pin: Mapped[dict] = mapped_column(JSON)
