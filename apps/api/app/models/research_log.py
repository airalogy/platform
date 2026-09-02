"""Revisioned human Research Log entries.

System activity is projected from its authoritative domain tables and is never
stored as editable prose in this model.
"""

from datetime import datetime
from enum import StrEnum
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
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ResearchLogScope(StrEnum):
    PERSONAL = "personal"
    LAB = "lab"
    PROJECT = "project"


class ResearchLogEntryKind(StrEnum):
    PROGRESS = "progress"
    MEETING = "meeting"
    REFLECTION = "reflection"
    BLOCKER = "blocker"
    MILESTONE = "milestone"


LOG_SCOPE_CHECK = (
    "(scope_type = 'personal' AND owner_user_id IS NOT NULL "
    "AND lab_id IS NULL AND project_id IS NULL) OR "
    "(scope_type = 'lab' AND owner_user_id IS NULL "
    "AND lab_id IS NOT NULL AND project_id IS NULL) OR "
    "(scope_type = 'project' AND owner_user_id IS NULL "
    "AND lab_id IS NOT NULL AND project_id IS NOT NULL)"
)


class ResearchLogEntry(Base):
    __tablename__ = "research_log_entries"
    __table_args__ = (
        CheckConstraint(LOG_SCOPE_CHECK, name="ck_research_log_entries_scope"),
        Index(
            "ix_research_log_entries_scope_time",
            "scope_type",
            "lab_id",
            "project_id",
            "occurred_at",
        ),
        Index(
            "ix_research_log_entries_owner_time", "owner_user_id", "occurred_at"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    lab_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    goal: Mapped[str] = mapped_column(Text, nullable=False, default="")
    completed_items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    next_steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    asset_links: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchLogRevision(Base):
    __tablename__ = "research_log_revisions"
    __table_args__ = (
        UniqueConstraint(
            "log_entry_id", "revision", name="uq_research_log_revision"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    log_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_log_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
