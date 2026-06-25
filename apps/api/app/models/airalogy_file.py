import mimetypes
from datetime import datetime
from enum import IntEnum
from typing import BinaryIO
from uuid import UUID

from sqlalchemy import JSON, BigInteger, String, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.libs.file_storage import (
    copy_file,
    delete_file,
    default_storage_backend,
    default_storage_namespace,
    download_file,
    file_local_url,
    file_object_url,
    get_file_content,
    get_file_with_stream,
    upload_file,
)

from .base import Base


class AiralogyFileType(IntEnum):
    img = 1
    video = 2
    audio = 3
    file = 4


class AiralogyFileStorageBackend:
    external = "external"


class AiralogyFile(Base):
    __tablename__ = "airalogy_files"

    id: Mapped[UUID] = mapped_column(
        nullable=False,
        primary_key=True,
        index=True,
        server_default=func.uuid_generate_v7(),
    )
    filename: Mapped[str] = mapped_column(nullable=False)
    content_type: Mapped[str | None] = mapped_column(nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    type: Mapped[int] = mapped_column(nullable=False)
    protocol_id: Mapped[UUID] = mapped_column(nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    user_id: Mapped[UUID] = mapped_column(nullable=False)
    storage_backend: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=default_storage_backend,
    )
    storage_namespace: Mapped[str | None] = mapped_column(String(256), nullable=True)
    storage_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    external_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    storage_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.content_type:
            self.content_type, _ = AiralogyFile.guess_type(self.filename)
        if not self.type:
            _, self.type = AiralogyFile.guess_type(self.filename)
        if not self.storage_backend:
            self.storage_backend = default_storage_backend()

    @classmethod
    def guess_type(cls, filename: str) -> tuple:
        content_type, _ = mimetypes.guess_type(filename)

        type = AiralogyFileType.file
        if content_type and content_type.startswith("image/"):
            type = AiralogyFileType.img
        elif content_type and content_type.startswith("video/"):
            type = AiralogyFileType.video
        elif content_type and content_type.startswith("audio/"):
            type = AiralogyFileType.audio

        return (content_type, type)

    @classmethod
    async def find(cls, db_session: AsyncSession, id: str | UUID, options=None):
        if isinstance(id, str) and id.startswith("airalogy.id.file"):
            id = id.split(".")[-2]
        return await super().find(db_session, id, options)

    @property
    def ext(self):
        return self.filename.split(".")[-1]

    @property
    def airalogy_id(self):
        return f"airalogy.id.file.{self.id}.{self.ext}"

    @property
    def default_object_key(self):
        return f"protocols/{self.protocol_id}/files/{self.id}.{self.ext}"

    @property
    def object_key(self):
        return self.storage_object_key or self.default_object_key

    @property
    def is_external_reference(self) -> bool:
        return bool(self.external_uri) and not self.storage_object_key

    def set_managed_storage_location(
        self,
        *,
        backend: str | None = None,
        namespace: str | None = None,
        object_key: str | None = None,
    ):
        self.storage_backend = (
            backend or self.storage_backend or default_storage_backend()
        )
        self.storage_namespace = namespace or default_storage_namespace(
            self.storage_backend
        )
        self.storage_object_key = object_key or self.default_object_key
        self.external_uri = None

    def set_external_storage_location(
        self,
        *,
        external_uri: str,
        backend: str = AiralogyFileStorageBackend.external,
        namespace: str | None = None,
        metadata: dict | None = None,
    ):
        self.storage_backend = backend
        self.storage_namespace = namespace
        self.storage_object_key = None
        self.external_uri = external_uri
        self.storage_metadata = metadata

    def storage_location(self) -> dict:
        return {
            "backend": self.storage_backend,
            "namespace": self.storage_namespace,
            "object_key": self.storage_object_key,
            "external_uri": self.external_uri,
            "metadata": self.storage_metadata,
        }

    def reference_payload(self, url: str | None = None) -> dict:
        return {
            "id": self.id,
            "airalogy_file_id": self.airalogy_id,
            "filename": self.filename,
            "url": url,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "sha256": self.checksum_sha256,
            "storage_backend": self.storage_backend,
            "storage_namespace": self.storage_namespace,
        }

    async def file_object_url(self, expires=24):
        if self.external_uri:
            return self.external_uri
        return await file_object_url(
            self.object_key,
            expires=expires,
            backend=self.storage_backend,
        )

    async def local_url(self, expires=24):
        if self.external_uri:
            return self.external_uri
        return await file_local_url(
            self.object_key,
            expires=expires,
            backend=self.storage_backend,
        )

    async def save_file(
        self,
        file: str | BinaryIO,
        content_type="application/octet-stream",
        length=-1,
        *,
        backend: str | None = None,
        namespace: str | None = None,
        checksum_sha256: str | None = None,
    ):
        self.content_type = content_type or self.content_type
        self.size_bytes = (
            length if length is not None and length >= 0 else self.size_bytes
        )
        self.checksum_sha256 = checksum_sha256 or self.checksum_sha256
        self.set_managed_storage_location(backend=backend, namespace=namespace)
        return await upload_file(
            object_key=self.object_key,
            file=file,
            content_type=self.content_type or "application/octet-stream",
            length=length,
            backend=self.storage_backend,
        )

    async def download_file(self, file_path: str):
        if self.external_uri:
            raise ValueError("External file references cannot be downloaded directly.")
        return await download_file(
            self.object_key,
            file_path,
            backend=self.storage_backend,
        )

    async def get_file_content(self):
        if self.external_uri:
            raise ValueError("External file references cannot be read directly.")
        return await get_file_content(self.object_key, backend=self.storage_backend)

    async def get_file_with_stream(self):
        if self.external_uri:
            raise ValueError("External file references cannot be streamed directly.")
        async for chunk in get_file_with_stream(
            self.object_key,
            backend=self.storage_backend,
        ):
            yield chunk

    async def copy_file(self, destination_key: str):
        if self.external_uri:
            raise ValueError("External file references cannot be copied directly.")
        return await copy_file(
            self.object_key,
            destination_key,
            backend=self.storage_backend,
        )

    async def delete_file(self):
        if self.external_uri:
            return None
        return await delete_file(self.object_key, backend=self.storage_backend)
