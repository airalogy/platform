from datetime import datetime
from typing import Annotated, BinaryIO, Literal
from uuid import UUID

from pydantic import BaseModel, StringConstraints
from sqlalchemy import JSON, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.libs.file_storage import (
    copy_file,
    download_file,
    file_object_url,
    get_file_with_stream,
    upload_file,
)

from .base import Base


class ProtocolMetadataUser(BaseModel):
    name: str | None = None
    email: str | None = None
    airalogy_user_id: str | None = None


class ProtocolMetadata(BaseModel):
    id: Annotated[
        str,
        StringConstraints(
            pattern=r"^[a-z][a-z0-9_]*$",
            min_length=4,
            strip_whitespace=True,
        ),
    ]
    version: Annotated[
        str,
        StringConstraints(
            pattern=r"^\d{1,3}(\.\d{1,3}){2}$",
            strip_whitespace=True,
        ),
    ] = "0.0.1"
    name: str = ""
    kind: Literal["experiment", "resource_definition"] = "experiment"
    authors: list[ProtocolMetadataUser] | None = None
    maintainers: list[ProtocolMetadataUser] | None = None
    disciplines: list[str] | None = None
    keywords: list[str] | None = None
    description: str | None = None
    readme: str | None = None
    license: str | None = None


class ProtocolVersion(Base):
    __tablename__ = "protocol_versions"

    id: Mapped[UUID] = mapped_column(
        nullable=False,
        primary_key=True,
        index=True,
        server_default=func.uuid_generate_v7(),
    )
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id"), nullable=False, index=True
    )
    meta_data: Mapped[dict] = mapped_column(JSON, nullable=True, default={})
    json_schema: Mapped[dict] = mapped_column(JSON)
    assigners: Mapped[dict] = mapped_column(JSON)
    fields: Mapped[dict] = mapped_column(JSON)
    aimd: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    version: Mapped[str] = mapped_column(nullable=False, default="0.0.1")
    assigner_graph: Mapped[dict] = mapped_column(JSON)
    compatibility_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    migration_manifest: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    protocol: Mapped[any] = relationship("Protocol", overlaps="protocol_versions")

    lab_uid = None
    project_uid = None
    json_include_fields = ["airalogy_id"]

    @property
    def package_name(self):
        return f"protocol_{self.id}"

    @property
    def uid(self):
        return self.meta_data["id"]

    @property
    def airalogy_id(self):
        if self.lab_uid is None or self.project_uid is None:
            raise ValueError("lab_uid and project_uid are required")
        return f"airalogy.id.lab.{self.lab_uid}.project.{self.project_uid}.protocol.{self.uid}.v.{self.version}"

    @property
    def package_object_key(self):
        return f"protocols/{self.protocol_id}/packages/v{self.version}/{self.uid}-v{self.version}.zip"

    @property
    def package_dir_object_key(self):
        return f"protocols/{self.protocol_id}/packages/v{self.version}/files"

    async def download_url(self):
        return await file_object_url(self.package_object_key)

    async def upload_package_file(
        self, filename: str, package_file_path: str | BinaryIO, content_type: str
    ):
        return await upload_file(
            object_key=f"{self.package_dir_object_key}/{filename}",
            file=package_file_path,
            content_type=content_type,
        )

    async def upload_package(self, package_file: str | BinaryIO, length: int = -1):
        return await upload_file(
            object_key=self.package_object_key,
            file=package_file,
            content_type="application/zip",
            length=length,
        )

    async def download_package(self, local_file_path: str):
        return await download_file(self.package_object_key, local_file_path)

    async def download_package_with_stream(self):
        async for chunk in get_file_with_stream(self.package_object_key):
            yield chunk

    async def copy_package(self, dest_object_key: str):
        return await copy_file(self.package_object_key, dest_object_key)
