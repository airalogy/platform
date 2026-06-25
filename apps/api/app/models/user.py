from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import bcrypt
from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import config
from app.libs.aes_crypt import aes_encrypt
from app.models.attachment import Attachment

from .base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        nullable=False,
        primary_key=True,
        index=True,
        server_default=func.uuid_generate_v7(),
    )
    username: Mapped[str] = mapped_column(nullable=False, index=True, unique=True)
    email: Mapped[str] = mapped_column(
        nullable=True, default="", index=True, unique=True
    )
    country_code: Mapped[str] = mapped_column(nullable=False, default="")
    phone: Mapped[str] = mapped_column(nullable=False, default="")
    password_hash: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )
    name: Mapped[str] = mapped_column(nullable=False, default="")
    bio: Mapped[str] = mapped_column(nullable=False, default="")
    avatar: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("attachments.id"), nullable=True
    )
    api_key_iv: Mapped[str] = mapped_column(nullable=False)
    level: Mapped[int] = mapped_column(nullable=False, default=1)
    avatar_attachment: Mapped[Attachment] = relationship(
        "Attachment",
        back_populates="user",
        lazy="selectin",
    )

    labs: Mapped[list[Any]] = relationship(
        "Lab", secondary="lab_users", back_populates="users", overlaps="users"
    )

    groups: Mapped[list[Any]] = relationship(
        "Group", secondary="group_users", back_populates="users", overlaps="users"
    )

    projects: Mapped[list[Any]] = relationship(
        "Project", secondary="project_users", back_populates="users", overlaps="users"
    )

    project_groups: Mapped[list[Any]] = relationship(
        "ProjectGroup",
        secondary="project_group_users",
        back_populates="users",
        overlaps="users",
    )

    star_folders: Mapped[list[Any]] = relationship(
        "StarFolder", back_populates="user", overlaps="user"
    )
    stars: Mapped[list[Any]] = relationship(
        "Star", back_populates="user", overlaps="user"
    )

    pinned_items: Mapped[list[Any]] = relationship(
        "PinnedItem", back_populates="user", overlaps="user"
    )

    # User alias relationships
    created_aliases: Mapped[list[Any]] = relationship(
        "UserAlias", foreign_keys="UserAlias.user_id", back_populates="user"
    )
    received_aliases: Mapped[list[Any]] = relationship(
        "UserAlias",
        foreign_keys="UserAlias.target_user_id",
        back_populates="target_user",
    )

    avatar_url = None
    json_exclude_fields = ["password_hash", "phone", "created_at", "api_key_iv"]
    json_include_fields = ["avatar_url"]

    @property
    def api_key(self):
        if self.api_key_iv is None:
            return None
        return aes_encrypt(
            f"{self.id},{self.api_key_iv}", config.AES_KEY, self.api_key_iv
        )

    @property
    def full_phone_number(self):
        return f"{self.country_code}{self.phone}"

    async def load_avatar_attachment(self):
        if self.avatar is None:
            return
        if self.avatar_attachment is not None:
            self.avatar_url = await self.avatar_attachment.url(expires=24 * 7)

    @property
    def password(self):
        raise AttributeError("password is not readable attribute")

    @password.setter
    def password(self, password: str):
        self.password_hash = bcrypt.hashpw(
            password=password.encode("utf-8"), salt=bcrypt.gensalt()
        ).decode("utf-8")

    def verify_password(self, plain_password: str) -> bool:
        return bcrypt.checkpw(
            password=plain_password.encode("utf-8"),
            hashed_password=self.password_hash.encode("utf-8"),
        )
