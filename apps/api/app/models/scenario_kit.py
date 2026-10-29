"""Scenario enablement and provenance; scientific assets remain normal assets."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LabScenarioKit(Base):
    __tablename__ = "lab_scenario_kits"
    __table_args__ = (
        UniqueConstraint("lab_id", "kit_id", name="uq_lab_scenario_kit"),
        CheckConstraint("revision > 0", name="ck_lab_scenario_kit_revision"),
    )
    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), index=True
    )
    kit_id: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(default=1)
    manifest: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ScenarioKitApplication(Base):
    __tablename__ = "scenario_kit_applications"
    __table_args__ = (
        UniqueConstraint("project_id", "kit_id", name="uq_project_scenario_kit"),
        CheckConstraint("revision > 0", name="ck_project_scenario_kit_revision"),
    )
    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    installation_id: Mapped[UUID] = mapped_column(
        ForeignKey("lab_scenario_kits.id", ondelete="CASCADE")
    )
    kit_id: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(default=1)
    manifest: Mapped[dict] = mapped_column(JSON)
    assets: Mapped[list] = mapped_column(JSON)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ScenarioSharedComponent(Base):
    __tablename__ = "scenario_shared_components"
    __table_args__ = (
        UniqueConstraint("lab_id", "component_id", name="uq_scenario_shared_component"),
    )
    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), index=True
    )
    component_id: Mapped[str] = mapped_column(String(128))
    resource_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("resource_types.id", ondelete="RESTRICT")
    )
    schema_digest: Mapped[str] = mapped_column(String(64))


class ScenarioKitEvent(Base):
    __tablename__ = "scenario_kit_events"
    __table_args__ = (
        UniqueConstraint("actor_user_id", "request_id", name="uq_scenario_kit_request"),
    )
    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    request_id: Mapped[UUID] = mapped_column()
    operation: Mapped[str] = mapped_column(String(32))
    request_digest: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
