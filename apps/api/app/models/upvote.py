from datetime import datetime
from enum import IntEnum
from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UpvoteResourceType(IntEnum):
    QUESTION = 1
    ANSWER = 2


class Upvote(Base):
    __tablename__ = "upvotes"

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    resource_type: Mapped[UpvoteResourceType] = mapped_column(INTEGER, nullable=False)
    resource_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
