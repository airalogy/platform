from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LabForceDeleteJob(Base):
    __tablename__ = "lab_force_delete_jobs"

    id: Mapped[int] = mapped_column(
        nullable=False,
        primary_key=True,
        autoincrement=True,
        index=True,
    )
    lab_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    lab_uid_snapshot: Mapped[str] = mapped_column(nullable=False)
    lab_name_snapshot: Mapped[str] = mapped_column(nullable=False)
    requested_by_user_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    status: Mapped[str] = mapped_column(nullable=False, index=True)
    impact_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
