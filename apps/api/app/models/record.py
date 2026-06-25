from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Record(Base):
    __tablename__ = "records"

    id: Mapped[UUID] = mapped_column(
        nullable=False,
        primary_key=True,
        index=True,
        server_default=func.uuid_generate_v7(),
    )
    version: Mapped[int] = mapped_column(nullable=False, default=1, primary_key=True)
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id"), nullable=False, index=True
    )
    protocol_version: Mapped[str] = mapped_column(nullable=False)
    user_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    data: Mapped[dict] = mapped_column(JSON)
    report: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    number: Mapped[int] = mapped_column(nullable=False, default=1)
    hash: Mapped[str] = mapped_column(nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(nullable=True)

    json_include_fields = ["airalogy_id"]

    @property
    def airalogy_id(self):
        return f"airalogy.id.record.{self.id}.v.{self.version}"
