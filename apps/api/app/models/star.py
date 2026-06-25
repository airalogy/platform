from datetime import datetime
from enum import IntEnum
from uuid import UUID

from sqlalchemy import BOOLEAN, ForeignKey, text
from sqlalchemy.dialects.postgresql import ARRAY, INTEGER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class StarResourceType(IntEnum):
    QUESTION = 1
    ANSWER = 2
    PROTOCOL = 3


class StarFolder(Base):
    __tablename__ = "star_folders"

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(nullable=False)
    is_default: Mapped[bool] = mapped_column(
        BOOLEAN,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    user: Mapped[any] = relationship("User", overlaps="star_folders")


class Star(Base):
    __tablename__ = "stars"

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    resource_type: Mapped[StarResourceType] = mapped_column(INTEGER, nullable=False)
    resource_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    folder_ids: Mapped[list[int]] = mapped_column(ARRAY(INTEGER), nullable=False)

    user: Mapped[any] = relationship("User", overlaps="stars")
