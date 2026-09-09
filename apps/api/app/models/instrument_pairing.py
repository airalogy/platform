"""One-use enrollment proposals; never serialize credential material."""

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class InstrumentPairing(Base):
    __tablename__ = "instrument_pairings"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending','claimed','confirmed','cancelled')",
            name="ck_instrument_pairing_state",
        ),
    )
    json_exclude_fields: ClassVar[list[str]] = ["code_digest", "credential_digest"]

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    gateway_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_instrument_gateways.id", ondelete="CASCADE"), index=True
    )
    gateway_revision: Mapped[int]
    code_digest: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(16), default="pending")
    client_name: Mapped[str | None] = mapped_column(String(128))
    credential_digest: Mapped[str | None] = mapped_column(String(64))
    credential_hint: Mapped[str | None] = mapped_column(String(8))
    reason: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
