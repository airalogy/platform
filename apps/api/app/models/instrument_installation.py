"""Version-pinned Device Bindings and independent installation authorizations."""

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class InstrumentDeviceBinding(Base):
    __tablename__ = "instrument_device_bindings"
    __table_args__ = (
        CheckConstraint(
            "state IN ('authorized','installing','installed','expired','revoked')",
            name="ck_instrument_binding_state",
        ),
        CheckConstraint("revision >= 1", name="ck_instrument_binding_revision"),
        Index(
            "uq_instrument_binding_pending_gateway",
            "gateway_id",
            unique=True,
            postgresql_where=text("state IN ('authorized','installing')"),
        ),
    )
    json_exclude_fields: ClassVar[list[str]] = [
        "installer_token_digest",
        "gateway_credential_pin",
        "creator_auth_version",
    ]

    id: Mapped[UUID] = mapped_column(primary_key=True)
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), index=True
    )
    gateway_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_instrument_gateways.id", ondelete="RESTRICT"), index=True
    )
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), index=True
    )
    resource_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("resource_revisions.id", ondelete="RESTRICT")
    )
    resource_revision: Mapped[int]
    release_id: Mapped[UUID] = mapped_column(
        ForeignKey("instrument_adapter_releases.id", ondelete="RESTRICT"), index=True
    )
    release_revision: Mapped[int]
    gateway_credential_pin: Mapped[str] = mapped_column(String(64))
    installer_token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    installer_fingerprint: Mapped[str] = mapped_column(String(64))
    descriptor: Mapped[dict] = mapped_column(JSON)
    authorization_digest: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="authorized")
    revision: Mapped[int] = mapped_column(default=1)
    reason: Mapped[str] = mapped_column(Text)
    receipt: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    creator_auth_version: Mapped[int]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InstrumentDeviceBindingAudit(Base):
    __tablename__ = "instrument_device_binding_audits"
    __table_args__ = (
        UniqueConstraint(
            "binding_id", "revision", name="uq_instrument_binding_audit_revision"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    binding_id: Mapped[UUID] = mapped_column(
        ForeignKey("instrument_device_bindings.id", ondelete="CASCADE"), index=True
    )
    revision: Mapped[int]
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
