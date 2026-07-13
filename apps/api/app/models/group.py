from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    uid: Mapped[str] = mapped_column(nullable=False)
    create_user_id: Mapped[UUID] = mapped_column(nullable=False)
    users_count: Mapped[int] = mapped_column(nullable=False, default=1)
    projects_count: Mapped[int] = mapped_column(nullable=False, default=0)
    description: Mapped[str] = mapped_column(default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )
    name: Mapped[str] = mapped_column(nullable=False)
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id"), nullable=False, index=True
    )
    parent_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("groups.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    lab: Mapped[any] = relationship("Lab", overlaps="groups")
    users: Mapped[list[any]] = relationship(
        "User", secondary="group_users", back_populates="groups", overlaps="groups"
    )
    projects: Mapped[list[any]] = relationship(
        "Project",
        secondary="group_projects",
        back_populates="groups",
        overlaps="groups",
    )


class GroupUser(Base):
    __tablename__ = "group_users"

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    create_user_id: Mapped[UUID] = mapped_column(nullable=False)
    membership_role: Mapped[str] = mapped_column(
        nullable=False, default="member", server_default=text("'member'")
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)


class GroupProject(Base):
    __tablename__ = "group_projects"

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id"), nullable=False, index=True
    )
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    create_user_id: Mapped[UUID] = mapped_column(nullable=False)
    role: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )
