from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AccessScopeType(StrEnum):
    LAB = "lab"
    PROJECT = "project"
    PROTOCOL = "protocol"


class AccessSubjectType(StrEnum):
    USER = "user"
    ORG_UNIT = "org_unit"


class AccessAuditAction(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    REVOKED = "revoked"


class AccessGrant(Base):
    __tablename__ = "access_grants"
    __table_args__ = (
        CheckConstraint(
            "(subject_type = 'user' AND user_id IS NOT NULL AND group_id IS NULL) "
            "OR (subject_type = 'org_unit' AND group_id IS NOT NULL AND user_id IS NULL)",
            name="ck_access_grants_subject",
        ),
        CheckConstraint(
            "(scope_type = 'lab' AND project_id IS NULL AND protocol_id IS NULL) "
            "OR (scope_type = 'project' AND project_id IS NOT NULL AND protocol_id IS NULL) "
            "OR (scope_type = 'protocol' AND protocol_id IS NOT NULL)",
            name="ck_access_grants_scope",
        ),
        Index("ix_access_grants_lab_active", "lab_id", "revoked_at", "expires_at"),
        Index("ix_access_grants_user_active", "user_id", "revoked_at"),
        Index("ix_access_grants_group_active", "group_id", "revoked_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, index=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_type: Mapped[str] = mapped_column(nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=True, index=True
    )
    scope_type: Mapped[str] = mapped_column(nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    protocol_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("protocols.id", ondelete="CASCADE"), nullable=True, index=True
    )
    role_key: Mapped[str] = mapped_column(nullable=False)
    inherit_to_children: Mapped[bool] = mapped_column(nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    reason: Mapped[str] = mapped_column(nullable=False, default="")
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )


class AccessGrantAudit(Base):
    __tablename__ = "access_grant_audits"
    __table_args__ = (
        Index("ix_access_grant_audits_lab_created", "lab_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, index=True, server_default=func.uuid_generate_v7()
    )
    grant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(nullable=False)
    before_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
