from datetime import datetime
from enum import IntEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import ARRAY, ForeignKey, String, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import config
from app.libs.aes_crypt import aes_decrypt, aes_encrypt

from .base import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.protocol_version import ProtocolVersion


class ProtocolStatus(IntEnum):
    DELETED = 0
    ACTIVE = 1


class Protocol(Base):
    __tablename__ = "protocols"

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
    uid: Mapped[str] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    latest_version: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    encrypted_env_vars: Mapped[str] = mapped_column(nullable=True)
    forks_count: Mapped[int] = mapped_column(nullable=False, default=0)
    stars_count: Mapped[int] = mapped_column(nullable=False, default=0)
    disciplines: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=[]
    )
    keywords: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=[]
    )
    parent_protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id"), nullable=True
    )
    parent_protocol_version: Mapped[str] = mapped_column(nullable=True)
    description: Mapped[str] = mapped_column(nullable=True)
    status: Mapped[int] = mapped_column(
        nullable=False, default=ProtocolStatus.ACTIVE.value
    )
    deleted_at: Mapped[datetime] = mapped_column(nullable=True)
    inherit_permissions: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=true()
    )

    project: Mapped["Project"] = relationship("Project", overlaps="protocols")
    protocol_versions: Mapped[list["ProtocolVersion"]] = relationship(
        "ProtocolVersion",
        back_populates="protocol",
        overlaps="protocol",
    )

    lab_uid = None
    project_uid = None
    version = None
    json_exclude_fields = ["encrypted_env_vars"]
    json_include_fields = ["airalogy_id"]

    @classmethod
    def default_find_scope(cls) -> list[Any]:
        return [cls.deleted_at.is_(None)]

    @property
    def airalogy_id(self):
        if self.lab_uid is None or self.project_uid is None:
            raise ValueError("lab_uid and project_uid are required")
        return f"airalogy.id.lab.{self.lab_uid}.project.{self.project_uid}.protocol.{self.uid}.v.{self.version or self.latest_version}"

    @property
    def env_vars(self):
        if self.encrypted_env_vars is None:
            return None
        return aes_decrypt(self.encrypted_env_vars, config.AES_KEY)

    @env_vars.setter
    def env_vars(self, var: str):
        if var is None or var == "":
            self.encrypted_env_vars = None
        else:
            self.encrypted_env_vars = aes_encrypt(var, config.AES_KEY)
