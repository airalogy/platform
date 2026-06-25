from datetime import datetime
from enum import IntEnum
from uuid import UUID

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.attachment import Attachment

from .base import Base


class LabRole(IntEnum):
    OWNER = 1
    MANAGER = 2
    MEMBER = 3


class Lab(Base):
    __tablename__ = "labs"

    id: Mapped[UUID] = mapped_column(
        nullable=False,
        primary_key=True,
        index=True,
        server_default=func.uuid_generate_v7(),
    )
    name: Mapped[str] = mapped_column(nullable=False)
    uid: Mapped[str] = mapped_column(nullable=False, index=True, unique=True)
    create_user_id: Mapped[UUID] = mapped_column(nullable=False)
    users_count: Mapped[int] = mapped_column(nullable=False, default=1)
    projects_count: Mapped[int] = mapped_column(nullable=False, default=0)
    groups_count: Mapped[int] = mapped_column(nullable=False, default=0)
    description: Mapped[str] = mapped_column(default="")
    logo: Mapped[UUID] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    users: Mapped[list[any]] = relationship(
        "User", secondary="lab_users", back_populates="labs"
    )
    groups: Mapped[list[any]] = relationship("Group", back_populates="lab")
    projects: Mapped[list[any]] = relationship("Project", back_populates="lab")

    logo_attachment: Mapped[any] = relationship(
        "Attachment",
        back_populates="lab",
    )
    logo_url = None
    json_include_fields = ["logo_url"]

    async def load_logo_attachment(self, db_session):
        if self.logo is None:
            return
        if self.logo_attachment is None:
            self.logo_attachment = await Attachment.find_by(
                db_session, [Attachment.id == self.logo]
            )
        if self.logo_attachment is not None:
            self.logo_url = await self.logo_attachment.local_url(expires=24 * 7)


class LabUser(Base):
    __tablename__ = "lab_users"

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[int] = mapped_column(nullable=False)
    alias: Mapped[str] = mapped_column(nullable=True)
    create_user_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )
