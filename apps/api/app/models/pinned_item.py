from datetime import datetime
from enum import IntEnum
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class PinnedResourceType(IntEnum):
    LAB = 1
    PROJECT = 2
    PROTOCOL = 3


class PinnedItem(Base):
    __tablename__ = "pinned_items"

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    resource_type: Mapped[int] = mapped_column(nullable=False)
    resource_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    user: Mapped[Any] = relationship("User", overlaps="pinned_items")
