from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[UUID] = mapped_column(
        nullable=False,
        primary_key=True,
        index=True,
        server_default=func.uuid_generate_v7(),
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(nullable=False)
    parent_id: Mapped[UUID]
    content: Mapped[str] = mapped_column(nullable=False)
    comments_count: Mapped[int] = mapped_column(nullable=False, default=0)
    upvotes_count: Mapped[int] = mapped_column(nullable=False, default=0)
    stars_count: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    question: Mapped[any] = relationship("Question", overlaps="answers")
