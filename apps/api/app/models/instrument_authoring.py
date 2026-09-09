"""Short-lived development grants and immutable model attempts, not device grants."""

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


class InstrumentAuthoringSession(Base):
    __tablename__ = "instrument_authoring_sessions"
    __table_args__ = (
        CheckConstraint("state IN ('open','cancelled')", name="ck_authoring_state"),
        CheckConstraint(
            "purpose IN ('source','interface')", name="ck_authoring_purpose"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    purpose: Mapped[str] = mapped_column(
        String(16), default="source", server_default="source"
    )
    gateway_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_instrument_gateways.id", ondelete="CASCADE"), index=True
    )
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT")
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    request: Mapped[dict] = mapped_column(JSON)
    scope_pin: Mapped[dict] = mapped_column(JSON)
    confirmation_digest: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="open")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InstrumentAuthoringTurn(Base):
    __tablename__ = "instrument_authoring_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "ordinal", name="uq_authoring_turn_ordinal"),
        CheckConstraint("ordinal BETWEEN 1 AND 5", name="ck_authoring_turn_ordinal"),
        CheckConstraint(
            "state IN ('generating','generated','failed')",
            name="ck_authoring_turn_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("instrument_authoring_sessions.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int]
    previous_id: Mapped[UUID | None]
    input: Mapped[dict | None] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(16))
    proposal: Mapped[dict | None] = mapped_column(JSON)
    candidate_digest: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(String(64))
    report: Mapped[dict | None] = mapped_column(JSON)
    operation_id: Mapped[str] = mapped_column(String(128))
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
