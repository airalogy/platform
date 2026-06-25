from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ProtocolFolder(Base):
    __tablename__ = "protocol_folders"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="protocol_folders_project_name_key"),
    )

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(nullable=False, default="")
    create_user_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    protocols: Mapped[list[any]] = relationship(
        "Protocol",
        secondary="protocol_folder_protocols",
        overlaps="protocols",
    )


class ProtocolFolderProtocol(Base):
    __tablename__ = "protocol_folder_protocols"
    __table_args__ = (
        UniqueConstraint(
            "protocol_folder_id",
            "protocol_id",
            name="protocol_folder_protocols_folder_protocol_key",
        ),
    )

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    protocol_folder_id: Mapped[int] = mapped_column(
        ForeignKey("protocol_folders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    create_user_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
