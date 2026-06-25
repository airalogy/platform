from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ProtocolWorkflow(Base):
    __tablename__ = "protocol_workflows"

    id: Mapped[UUID] = mapped_column(
        nullable=False,
        primary_key=True,
        index=True,
        server_default=func.uuid_generate_v7(),
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    root_protocol_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("protocols.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="Workflow")
    workflow_info: Mapped[dict] = mapped_column(JSON, nullable=False)
    path_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    @classmethod
    def default_find_scope(cls):
        return [cls.deleted_at.is_(None)]
