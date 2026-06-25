from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ProjectGroup(Base):
    """Group scoped to a project for protocol-level permissions"""

    __tablename__ = "project_groups"

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    uid: Mapped[str] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(default="")
    create_user_id: Mapped[UUID] = mapped_column(nullable=False)
    users_count: Mapped[int] = mapped_column(nullable=False, default=0)
    protocols_count: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    project: Mapped[any] = relationship("Project", overlaps="project_groups")
    users: Mapped[list[any]] = relationship(
        "User",
        secondary="project_group_users",
        back_populates="project_groups",
        overlaps="project_groups",
    )
    protocols: Mapped[list[any]] = relationship(
        "Protocol",
        secondary="project_group_protocols",
        overlaps="project_groups",
    )


class ProjectGroupUser(Base):
    """User membership in a project group"""

    __tablename__ = "project_group_users"

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    project_group_id: Mapped[int] = mapped_column(
        ForeignKey("project_groups.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    create_user_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)


class ProjectGroupProtocol(Base):
    """Protocol assignment to a project group with role"""

    __tablename__ = "project_group_protocols"

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    project_group_id: Mapped[int] = mapped_column(
        ForeignKey("project_groups.id"), nullable=False, index=True
    )
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id"), nullable=False
    )
    role: Mapped[int] = mapped_column(nullable=False)
    create_user_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )


class ProtocolUser(Base):
    """Direct user-protocol permission assignment"""

    __tablename__ = "protocol_users"

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[int] = mapped_column(nullable=False)
    create_user_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )
