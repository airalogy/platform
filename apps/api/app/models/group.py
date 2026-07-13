from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class OrganizationalUnitType(StrEnum):
    DEPARTMENT = "department"
    RESEARCH_GROUP = "research_group"
    CORE_FACILITY = "core_facility"
    PROJECT_TEAM = "project_team"
    COMMITTEE = "committee"
    OTHER = "other"


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (
        CheckConstraint(
            "unit_type IN ('department', 'research_group', 'core_facility', "
            "'project_team', 'committee', 'other')",
            name="ck_groups_unit_type",
        ),
    )

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
    unit_type: Mapped[str] = mapped_column(
        nullable=False,
        default=OrganizationalUnitType.OTHER,
        server_default=text("'other'"),
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


# Keep the established table and relationship name while exposing the generic
# domain term to new access-control code.
OrganizationalUnit = Group


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
