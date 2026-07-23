"""Lab resource, inventory, equipment, and schema-governance models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ResourceVisibility(StrEnum):
    LAB = "lab"
    RESTRICTED = "restricted"


class ResourceStatus(StrEnum):
    ACTIVE = "active"
    QUARANTINED = "quarantined"
    DEPLETED = "depleted"
    RETIRED = "retired"
    ARCHIVED = "archived"


class InventoryEventKind(StrEnum):
    RECEIPT = "receipt"
    OUTPUT = "output"
    TRANSFER = "transfer"
    CONSUMPTION = "consumption"
    ADJUSTMENT = "adjustment"
    COUNT = "count"
    DISPOSAL = "disposal"
    RESERVATION = "reservation"
    RESERVATION_RELEASE = "reservation_release"


class BookingStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class RevisionKind(StrEnum):
    INITIAL = "initial"
    CORRECTION = "correction"
    SCHEMA_MIGRATION = "schema_migration"
    IMPORT = "import"
    LEGACY_REVISION = "legacy_revision"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResourceType(Base):
    __tablename__ = "resource_types"
    __table_args__ = (
        UniqueConstraint("lab_id", "code", name="uq_resource_types_lab_code"),
        Index("ix_resource_types_lab_archived", "lab_id", "archived_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    current_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "resource_type_revisions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_resource_types_current_revision",
        ),
        nullable=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResourceTypeRevision(Base):
    __tablename__ = "resource_type_revisions"
    __table_args__ = (
        UniqueConstraint(
            "resource_type_id",
            "revision",
            name="uq_resource_type_revisions_revision",
        ),
        UniqueConstraint(
            "resource_type_id",
            "protocol_version_id",
            name="uq_resource_type_revisions_protocol_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    resource_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("resource_types.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    protocol_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocol_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    capabilities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    booking_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="none"
    )
    schema_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Resource(Base):
    __tablename__ = "resources"
    __table_args__ = (
        UniqueConstraint("lab_id", "code", name="uq_resources_lab_code"),
        Index("ix_resources_lab_type_status", "lab_id", "resource_type_id", "status"),
        Index("ix_resources_lab_visibility", "lab_id", "visibility"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("resource_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    current_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "resource_revisions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_resources_current_revision",
        ),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ResourceStatus.ACTIVE.value
    )
    visibility: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ResourceVisibility.LAB.value
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResourceRevision(Base):
    __tablename__ = "resource_revisions"
    __table_args__ = (
        UniqueConstraint(
            "resource_id", "revision", name="uq_resource_revisions_revision"
        ),
        Index("ix_resource_revisions_type_revision", "resource_type_revision_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_type_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("resource_type_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    revision_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RevisionKind.INITIAL.value
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resource_revisions.id", ondelete="SET NULL")
    )
    migration_run_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResourceFieldIndex(Base):
    __tablename__ = "resource_field_indexes"
    __table_args__ = (
        UniqueConstraint(
            "resource_revision_id",
            "path",
            "ordinal",
            name="uq_resource_field_indexes_value",
        ),
        Index("ix_resource_field_indexes_text", "resource_type_id", "path", "value_text"),
        Index(
            "ix_resource_field_indexes_numeric",
            "resource_type_id",
            "path",
            "value_numeric",
        ),
        Index(
            "ix_resource_field_indexes_timestamp",
            "resource_type_id",
            "path",
            "value_timestamp",
        ),
        Index("ix_resource_field_indexes_ref", "resource_type_id", "path", "ref_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    resource_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("resource_types.id", ondelete="CASCADE"), nullable=False
    )
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("resource_revisions.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    ordinal: Mapped[int] = mapped_column(nullable=False, default=0)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)
    value_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ref_id: Mapped[str | None] = mapped_column(String(255))


class ResourceLocation(Base):
    __tablename__ = "resource_locations"
    __table_args__ = (
        UniqueConstraint("lab_id", "code", name="uq_resource_locations_lab_code"),
        Index("ix_resource_locations_parent", "parent_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resource_locations.id", ondelete="RESTRICT")
    )
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, default="location")
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    visibility: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ResourceVisibility.LAB.value
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResourceLot(Base):
    __tablename__ = "resource_lots"
    __table_args__ = (
        UniqueConstraint("resource_id", "code", name="uq_resource_lots_resource_code"),
        Index("ix_resource_lots_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    supplier: Mapped[str | None] = mapped_column(String(255))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResourceContainer(Base):
    __tablename__ = "resource_containers"
    __table_args__ = (
        UniqueConstraint("lab_id", "code", name="uq_resource_containers_lab_code"),
        Index("ix_resource_containers_resource_lot", "resource_id", "lot_id"),
        Index("ix_resource_containers_location", "location_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resource_lots.id", ondelete="RESTRICT"), index=True
    )
    location_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resource_locations.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InventoryBalance(Base):
    __tablename__ = "inventory_balances"

    container_id: Mapped[UUID] = mapped_column(
        ForeignKey("resource_containers.id", ondelete="CASCADE"), primary_key=True
    )
    on_hand: Mapped[Decimal] = mapped_column(
        Numeric(38, 18), nullable=False, default=Decimal("0")
    )
    reserved: Mapped[Decimal] = mapped_column(
        Numeric(38, 18), nullable=False, default=Decimal("0")
    )
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def available(self) -> Decimal:
        return self.on_hand - self.reserved


class InventoryEvent(Base):
    __tablename__ = "inventory_events"
    __table_args__ = (
        UniqueConstraint("lab_id", "idempotency_key", name="uq_inventory_events_idempotency"),
        Index("ix_inventory_events_resource_created", "resource_id", "created_at"),
        Index("ix_inventory_events_container_created", "container_id", "created_at"),
        Index("ix_inventory_events_record", "record_id", "record_version"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False
    )
    lot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resource_lots.id", ondelete="RESTRICT")
    )
    container_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resource_containers.id", ondelete="RESTRICT")
    )
    from_container_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resource_containers.id", ondelete="RESTRICT")
    )
    to_container_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resource_containers.id", ondelete="RESTRICT")
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    on_hand_before: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    on_hand_after: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    reserved_before: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    reserved_after: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    record_id: Mapped[UUID | None] = mapped_column(nullable=True)
    record_version: Mapped[int | None] = mapped_column(nullable=True)
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    event_metadata: Mapped[dict] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"
    __table_args__ = (
        UniqueConstraint("lab_id", "idempotency_key", name="uq_inventory_reservations_idempotency"),
        Index("ix_inventory_reservations_container_status", "container_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False
    )
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False
    )
    container_id: Mapped[UUID] = mapped_column(
        ForeignKey("resource_containers.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EquipmentBooking(Base):
    __tablename__ = "equipment_bookings"
    __table_args__ = (
        UniqueConstraint("lab_id", "idempotency_key", name="uq_equipment_bookings_idempotency"),
        Index("ix_equipment_bookings_resource_time", "resource_id", "starts_at", "ends_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False
    )
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=BookingStatus.PENDING.value
    )
    approval_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    record_id: Mapped[UUID | None] = mapped_column(nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EquipmentUsage(Base):
    __tablename__ = "equipment_usages"
    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_equipment_usages_booking"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    booking_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("equipment_bookings.id", ondelete="SET NULL")
    )
    reservation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("inventory_reservations.id", ondelete="SET NULL")
    )
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    record_id: Mapped[UUID | None] = mapped_column(nullable=True)
    record_version: Mapped[int | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class EquipmentServiceEvent(Base):
    __tablename__ = "equipment_service_events"
    __table_args__ = (
        Index("ix_equipment_service_resource_time", "resource_id", "starts_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False
    )
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider: Mapped[str | None] = mapped_column(String(255))
    certificate_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("attachments.id", ondelete="SET NULL")
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResourceLineage(Base):
    __tablename__ = "resource_lineage"
    __table_args__ = (
        UniqueConstraint(
            "parent_resource_id",
            "child_resource_id",
            "record_id",
            "record_version",
            name="uq_resource_lineage_edge",
        ),
        Index("ix_resource_lineage_child", "child_resource_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    parent_resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False
    )
    child_resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False
    )
    record_id: Mapped[UUID] = mapped_column(nullable=False)
    record_version: Mapped[int] = mapped_column(nullable=False)
    relationship: Mapped[str] = mapped_column(
        String(32), nullable=False, default="derived_from"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RecordResourceLink(Base):
    __tablename__ = "record_resource_links"
    __table_args__ = (
        UniqueConstraint(
            "record_id",
            "record_version",
            "field_path",
            "resource_id",
            name="uq_record_resource_links_field",
        ),
        Index("ix_record_resource_links_resource", "resource_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    record_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    record_version: Mapped[int] = mapped_column(nullable=False)
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id", ondelete="RESTRICT"), nullable=False
    )
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False
    )
    resource_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resource_revisions.id", ondelete="SET NULL")
    )
    lot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resource_lots.id", ondelete="SET NULL")
    )
    container_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resource_containers.id", ondelete="SET NULL")
    )
    booking_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("equipment_bookings.id", ondelete="SET NULL")
    )
    field_path: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    unit: Mapped[str | None] = mapped_column(String(32))
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResourceNotification(Base):
    __tablename__ = "resource_notifications"
    __table_args__ = (
        Index("ix_resource_notifications_user_read", "user_id", "read_at"),
        UniqueConstraint("user_id", "deduplication_key", name="uq_resource_notifications_dedupe"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(255), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResourceLabel(Base):
    __tablename__ = "resource_labels"
    __table_args__ = (
        UniqueConstraint("lab_id", "code", name="uq_resource_labels_code"),
        Index("ix_resource_labels_target", "target_type", "target_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[UUID] = mapped_column(nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False, default="qr")
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SchemaMigrationRun(Base):
    __tablename__ = "schema_migration_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_schema_migration_runs_idempotency"),
        Index("ix_schema_migration_runs_protocol", "protocol_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id", ondelete="CASCADE"), nullable=False
    )
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    target_version: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    rule_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    code_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RecordProjection(Base):
    __tablename__ = "record_projections"
    __table_args__ = (
        UniqueConstraint(
            "record_id",
            "record_version",
            "target_protocol_version",
            "rule_hash",
            name="uq_record_projections_cache",
        ),
        Index("ix_record_projections_target_status", "target_protocol_version", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    record_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    record_version: Mapped[int] = mapped_column(nullable=False)
    protocol_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocols.id", ondelete="CASCADE"), nullable=False
    )
    source_protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    target_protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    projected_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    not_collected: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PersistentJob(Base):
    __tablename__ = "persistent_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_persistent_jobs_idempotency"),
        Index("ix_persistent_jobs_claim", "status", "available_at", "lease_expires_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    lab_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=JobStatus.PENDING.value
    )
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(nullable=False, default=5)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
