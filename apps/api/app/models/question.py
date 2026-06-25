from datetime import datetime
from uuid import UUID

from sqlalchemy import VARCHAR, ForeignKey, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.protocol import Protocol

from .base import Base


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[UUID] = mapped_column(
        nullable=False,
        primary_key=True,
        index=True,
        server_default=func.uuid_generate_v7(),
    )
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(nullable=False)
    views_count: Mapped[int] = mapped_column(nullable=False, default=0)
    answers_count: Mapped[int] = mapped_column(nullable=False, default=0)
    upvotes_count: Mapped[int] = mapped_column(nullable=False, default=0)
    stars_count: Mapped[int] = mapped_column(nullable=False, default=0)
    tags: Mapped[list[str]] = mapped_column(ARRAY(VARCHAR), nullable=False, default=[])
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    protocol: Mapped[Protocol] = relationship("Protocol", overlaps="questions")
    answers: Mapped[list[any]] = relationship("Answer", back_populates="question")
