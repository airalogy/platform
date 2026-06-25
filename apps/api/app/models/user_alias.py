from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class UserAlias(Base):
    """用户别名模型：当前用户给其他用户设置的备注名"""

    __tablename__ = "user_aliases"
    __table_args__ = (
        # 确保一个用户对另一个用户只能有一个别名
        UniqueConstraint("user_id", "target_user_id", name="uq_user_target_alias"),
    )

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    # Relationships
    user: Mapped[Any] = relationship(
        "User", foreign_keys=[user_id], back_populates="created_aliases"
    )
    target_user: Mapped[Any] = relationship(
        "User", foreign_keys=[target_user_id], back_populates="received_aliases"
    )

    json_exclude_fields = ["created_at", "updated_at"]
