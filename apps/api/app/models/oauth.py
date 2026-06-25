from datetime import datetime
from typing import Any
from uuid import UUID

import bcrypt
from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class OAuthClient(Base):
    __tablename__ = "oauth_clients"

    id: Mapped[UUID] = mapped_column(
        nullable=False,
        primary_key=True,
        index=True,
        server_default=func.uuid_generate_v7(),
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    client_secret_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    redirect_uris: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    create_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    create_user: Mapped[Any] = relationship("User", lazy="selectin")

    json_exclude_fields = ["client_secret_hash"]

    @property
    def client_secret(self):
        raise AttributeError("client_secret is not readable attribute")

    @client_secret.setter
    def client_secret(self, client_secret: str):
        self.client_secret_hash = bcrypt.hashpw(
            password=client_secret.encode("utf-8"),
            salt=bcrypt.gensalt(),
        ).decode("utf-8")

    def verify_client_secret(self, client_secret: str) -> bool:
        return bcrypt.checkpw(
            password=client_secret.encode("utf-8"),
            hashed_password=self.client_secret_hash.encode("utf-8"),
        )


class OAuthAuthorizationCode(Base):
    __tablename__ = "oauth_authorization_codes"

    id: Mapped[UUID] = mapped_column(
        nullable=False,
        primary_key=True,
        index=True,
        server_default=func.uuid_generate_v7(),
    )
    client_id: Mapped[UUID] = mapped_column(ForeignKey("oauth_clients.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    redirect_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    scope: Mapped[str] = mapped_column(String(256), nullable=False, default="basic")
    state: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    client: Mapped[Any] = relationship("OAuthClient", lazy="selectin")
    user: Mapped[Any] = relationship("User", lazy="selectin")


class OAuthAccessToken(Base):
    __tablename__ = "oauth_access_tokens"

    id: Mapped[UUID] = mapped_column(
        nullable=False,
        primary_key=True,
        index=True,
        server_default=func.uuid_generate_v7(),
    )
    client_id: Mapped[UUID] = mapped_column(ForeignKey("oauth_clients.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    access_token: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    scope: Mapped[str] = mapped_column(String(256), nullable=False, default="basic")
    expires_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    client: Mapped[Any] = relationship("OAuthClient", lazy="selectin")
    user: Mapped[Any] = relationship("User", lazy="selectin")
