from datetime import datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.libs.file_storage import (
    delete_file,
    file_local_url,
    file_object_url,
    upload_file,
)

from .base import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[UUID] = mapped_column(
        nullable=False,
        primary_key=True,
        index=True,
        server_default=func.uuid_generate_v7(),
    )
    filename: Mapped[str] = mapped_column(nullable=False)
    content_type: Mapped[str] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    user_id: Mapped[UUID] = mapped_column(nullable=True)

    user: Mapped[any] = relationship("User", back_populates="avatar_attachment")
    lab: Mapped[any] = relationship("Lab", back_populates="logo_attachment")

    @property
    def object_key(self):
        id_str = str(self.id)
        return f"{id_str[:6]}/{id_str}/{self.filename}"

    async def url(self, expires=24):
        return await file_object_url(self.object_key, expires=expires)

    async def local_url(self, expires=24):
        return await file_local_url(self.object_key, expires=expires)

    async def save_file(self, file, length=-1):
        return await upload_file(
            object_key=self.object_key,
            file=file,
            content_type=self.content_type,
            length=length,
        )

    async def delete_file(self):
        return await delete_file(self.object_key)
