from datetime import datetime
from enum import IntEnum
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ProjectRole(IntEnum):
    OWNER = 1
    MANAGER = 20
    COLLABORATOR = 30
    PROTOCOL_OWNER = 35
    RECORDER = 40
    RECORDER_SELF_ONLY = 45
    EXPLORER = 50
    EXPLORER_SELF_ONLY = 55
    VIEWER = 60
    VIEWER_SELF_ONLY = 65


class ProjectType(IntEnum):
    PRIVATE = 1
    PUBLIC = 2


class ProjectStatus(IntEnum):
    DELETED = 0
    ACTIVE = 1


class PermissionType(IntEnum):
    INHERIT = 1  # Project permission = protocol permission (default)
    PROTOCOL_LEVEL = 2  # Requires explicit protocol permission


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(
        nullable=False,
        primary_key=True,
        index=True,
        server_default=func.uuid_generate_v7(),
    )
    name: Mapped[str] = mapped_column(nullable=False)
    lab_id: Mapped[UUID] = mapped_column(ForeignKey("labs.id"), nullable=False)
    parent_project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    create_user_id: Mapped[UUID] = mapped_column(nullable=False)

    description: Mapped[str] = mapped_column(default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )
    uid: Mapped[str] = mapped_column(nullable=False)
    type: Mapped[int] = mapped_column(nullable=False)
    public_access_role: Mapped[int] = mapped_column(
        nullable=False, default=ProjectRole.EXPLORER.value
    )
    status: Mapped[int] = mapped_column(
        nullable=False, default=ProjectStatus.ACTIVE.value
    )
    deleted_at: Mapped[datetime] = mapped_column(nullable=True)
    permission_type: Mapped[int] = mapped_column(
        nullable=False, default=PermissionType.INHERIT.value
    )

    lab: Mapped[any] = relationship("Lab", overlaps="projects")
    users: Mapped[list[any]] = relationship(
        "User",
        secondary="project_users",
        back_populates="projects",
        overlaps="projects",
    )
    groups: Mapped[list[any]] = relationship(
        "Group",
        secondary="group_projects",
        back_populates="projects",
        overlaps="projects",
    )
    protocols: Mapped[list[any]] = relationship(
        "Protocol",
        back_populates="project",
        overlaps="project",
    )

    @classmethod
    def default_find_scope(cls) -> list[Any]:
        return [cls.deleted_at.is_(None)]

    @property
    def is_public(self) -> bool:
        return self.type == ProjectType.PUBLIC

    @property
    def is_private(self) -> bool:
        return self.type == ProjectType.PRIVATE


class ProjectUser(Base):
    __tablename__ = "project_users"

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[int] = mapped_column(nullable=False)
    create_user_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )
