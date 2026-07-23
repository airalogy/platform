"""Lab resource library, inventory, equipment, label, and resolver APIs."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, UploadFile
from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.database import DBSession
from app.models.project import Project
from app.models.protocol import Protocol, ProtocolKind
from app.models.protocol_version import ProtocolVersion
from app.models.resource import (
    BookingStatus,
    EquipmentBooking,
    EquipmentServiceEvent,
    EquipmentUsage,
    InventoryBalance,
    InventoryEvent,
    InventoryReservation,
    RecordResourceLink,
    Resource,
    ResourceContainer,
    ResourceFieldIndex,
    ResourceLabel,
    ResourceLineage,
    ResourceLocation,
    ResourceLot,
    ResourceNotification,
    ResourceRevision,
    ResourceStatus,
    ResourceType,
    ResourceTypeRevision,
    ResourceVisibility,
)
from app.services.access_control import resolve_resource_access
from app.services.resource_index import build_resource_indexes
from app.services.resource_inventory import (
    InventoryError,
    apply_inventory_event,
    release_inventory_reservation,
    reserve_inventory,
    set_inventory_on_hand,
    transfer_inventory,
)
from app.services.resource_units import UnitError, normalize_ucum_unit

from .depends import CurrentUser

router = APIRouter(
    prefix="/labs/{lab_id}/resource-library",
    tags=["resource-library"],
)

RESOURCE_CAPABILITIES = {
    "inventory",
    "lots",
    "containers",
    "expiry",
    "serial_number",
    "booking",
    "maintenance",
    "calibration",
}
BOOKING_POLICIES = {"none", "auto", "approval", "authorized"}
RESOURCE_STATUSES = {item.value for item in ResourceStatus}


def _now() -> datetime:
    return datetime.now(UTC)


async def _refresh_user_notifications(
    db_session: DBSession,
    *,
    lab_id: UUID,
    user_id: UUID,
) -> bool:
    """Materialize deterministic expiry and service reminders idempotently."""
    horizon = _now() + timedelta(days=30)
    pending: list[dict[str, Any]] = []
    lots = (
        await db_session.execute(
            select(ResourceLot, Resource)
            .join(Resource, Resource.id == ResourceLot.resource_id)
            .where(
                Resource.lab_id == lab_id,
                Resource.archived_at.is_(None),
                ResourceLot.status == "active",
                ResourceLot.expires_at.is_not(None),
                ResourceLot.expires_at <= horizon,
            )
        )
    ).all()
    for lot, resource in lots:
        pending.append(
            {
                "kind": "lot_expiry",
                "title": f"{resource.name} lot expires soon",
                "message": f"Lot {lot.code} expires at {lot.expires_at.isoformat()}",
                "target_type": "lot",
                "target_id": str(lot.id),
                "deduplication_key": f"lot-expiry:{lot.id}:{lot.expires_at.date()}",
                "due_at": lot.expires_at,
            }
        )
    service_events = (
        await db_session.scalars(
            select(EquipmentServiceEvent).where(
                EquipmentServiceEvent.lab_id == lab_id,
                EquipmentServiceEvent.due_at.is_not(None),
                EquipmentServiceEvent.due_at <= horizon,
                EquipmentServiceEvent.status.not_in(["completed", "closed"]),
            )
        )
    ).all()
    for event in service_events:
        pending.append(
            {
                "kind": f"equipment_{event.kind}_due",
                "title": f"Equipment {event.kind} is due",
                "message": f"Service is due at {event.due_at.isoformat()}",
                "target_type": "resource",
                "target_id": str(event.resource_id),
                "deduplication_key": (
                    f"equipment-service:{event.id}:{event.due_at.date()}"
                ),
                "due_at": event.due_at,
            }
        )
    if not pending:
        return False
    keys = [item["deduplication_key"] for item in pending]
    existing = set(
        (
            await db_session.scalars(
                select(ResourceNotification.deduplication_key).where(
                    ResourceNotification.user_id == user_id,
                    ResourceNotification.deduplication_key.in_(keys),
                )
            )
        ).all()
    )
    created = False
    for item in pending:
        if item["deduplication_key"] in existing:
            continue
        db_session.add(
            ResourceNotification(
                lab_id=lab_id,
                user_id=user_id,
                **item,
            )
        )
        created = True
    if created:
        await db_session.flush()
    return created


def _json_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _model_data(model, **extra) -> dict[str, Any]:
    return model.as_dict(**extra)


def _validation_issues(schema: dict, data: dict) -> list[dict[str, str]]:
    try:
        validator = Draft202012Validator(schema)
    except Exception as error:
        raise HTTPException(
            status_code=409,
            detail=f"Registered resource Schema is invalid: {error}",
        ) from error
    return [
        {
            "path": ".".join(str(item) for item in error.absolute_path),
            "message": error.message,
        }
        for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path))
    ]


def _validate_data(schema: dict, data: dict) -> None:
    issues = _validation_issues(schema, data)
    if issues:
        raise HTTPException(
            status_code=422,
            detail={"message": "Resource data does not match its AIMD Schema", "issues": issues},
        )


def _set_import_path(target: dict[str, Any], path: str, value: Any) -> None:
    current = target
    segments = [segment for segment in path.split(".") if segment]
    for segment in segments[:-1]:
        child = current.get(segment)
        if not isinstance(child, dict):
            child = {}
            current[segment] = child
        current = child
    if segments:
        current[segments[-1]] = value


def _map_import_row(
    row: dict[str, Any],
    *,
    name_field: str,
    code_field: str,
    field_mapping: dict[str, str],
) -> dict[str, Any]:
    if isinstance(row.get("data"), dict) and not field_mapping:
        data = row["data"]
    elif field_mapping:
        data = {}
        for source, target in field_mapping.items():
            if source in row:
                _set_import_path(data, target, row[source])
    else:
        data = {
            key: value
            for key, value in row.items()
            if key not in {name_field, code_field, "visibility"}
        }
    return {
        "name": str(row.get(name_field) or "").strip(),
        "code": str(row.get(code_field) or "").strip(),
        "visibility": (
            "restricted"
            if row.get("visibility") == "restricted"
            else "lab"
        ),
        "data": data,
    }


async def _read_import_rows(file: UploadFile) -> list[dict[str, Any]]:
    raw = await file.read()
    filename = (file.filename or "").lower()
    try:
        if filename.endswith(".json"):
            parsed = json.loads(raw)
            rows = parsed if isinstance(parsed, list) else [parsed]
        else:
            dialect = "\t" if filename.endswith(".tsv") else ","
            rows = list(
                csv.DictReader(
                    io.StringIO(raw.decode("utf-8-sig")), delimiter=dialect
                )
            )
    except (UnicodeDecodeError, json.JSONDecodeError, csv.Error) as error:
        raise HTTPException(
            status_code=422, detail=f"Invalid import file: {error}"
        ) from error
    if not all(isinstance(row, dict) for row in rows):
        raise HTTPException(
            status_code=422, detail="Every import row must be an object"
        )
    return rows


def _parse_field_mapping(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=422, detail=f"Invalid field_mapping JSON: {error}"
        ) from error
    if not isinstance(parsed, dict) or not all(
        isinstance(source, str) and isinstance(target, str)
        for source, target in parsed.items()
    ):
        raise HTTPException(
            status_code=422,
            detail="field_mapping must be a JSON object of source and target paths",
        )
    return parsed


async def _decision(
    db_session: DBSession,
    *,
    user_id: UUID,
    lab_id: UUID,
    resource_type_id: UUID | None = None,
    resource_id: UUID | None = None,
    location_id: UUID | None = None,
):
    return await resolve_resource_access(
        db_session,
        user_id,
        lab_id,
        resource_type_id=resource_type_id,
        resource_id=resource_id,
        location_id=location_id,
    )


async def _require(
    db_session: DBSession,
    *,
    user_id: UUID,
    lab_id: UUID,
    capability: str,
    resource_type_id: UUID | None = None,
    resource_id: UUID | None = None,
    location_id: UUID | None = None,
):
    decision = await _decision(
        db_session,
        user_id=user_id,
        lab_id=lab_id,
        resource_type_id=resource_type_id,
        resource_id=resource_id,
        location_id=location_id,
    )
    if capability not in decision.capabilities:
        raise HTTPException(status_code=403, detail="Permission denied")
    return decision


async def _resource(
    db_session: DBSession,
    lab_id: UUID,
    resource_id: UUID,
    *,
    archived: bool = False,
) -> Resource:
    value = await db_session.get(Resource, resource_id)
    if (
        value is None
        or value.lab_id != lab_id
        or (not archived and value.archived_at is not None)
    ):
        raise HTTPException(status_code=404, detail="Resource not found")
    return value


async def _resource_type(
    db_session: DBSession,
    lab_id: UUID,
    resource_type_id: UUID,
) -> ResourceType:
    value = await db_session.get(ResourceType, resource_type_id)
    if value is None or value.lab_id != lab_id or value.archived_at is not None:
        raise HTTPException(status_code=404, detail="Resource type not found")
    return value


async def _current_type_revision(
    db_session: DBSession, resource_type: ResourceType
) -> ResourceTypeRevision:
    if resource_type.current_revision_id is None:
        raise HTTPException(status_code=409, detail="Resource type is not active")
    value = await db_session.get(
        ResourceTypeRevision, resource_type.current_revision_id
    )
    if value is None:
        raise HTTPException(status_code=409, detail="Resource type revision is missing")
    return value


async def _can_read_resource(
    db_session: DBSession, user_id: UUID, resource: Resource
) -> bool:
    decision = await _decision(
        db_session,
        user_id=user_id,
        lab_id=resource.lab_id,
        resource_type_id=resource.resource_type_id,
        resource_id=resource.id,
    )
    if "resource.read" not in decision.capabilities:
        return False
    if resource.visibility == ResourceVisibility.LAB.value:
        return True
    return any(
        source.scope_type in {"resource", "resource_type"}
        or source.role_key in {"lab_owner", "lab_admin"}
        for source in decision.sources
    )


class ResourceTypeParams(BaseModel):
    protocol_version_id: UUID
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    capabilities: dict[str, bool] = Field(default_factory=dict)
    booking_policy: Literal["none", "auto", "approval", "authorized"] = "none"

    @model_validator(mode="after")
    def validate_capabilities(self):
        unknown = set(self.capabilities) - RESOURCE_CAPABILITIES
        if unknown:
            raise ValueError(f"Unknown resource capabilities: {sorted(unknown)}")
        if self.booking_policy != "none" and not self.capabilities.get("booking"):
            raise ValueError("booking_policy requires the booking capability")
        return self


class ResourceParams(BaseModel):
    resource_type_id: UUID
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=128)
    data: dict[str, Any] = Field(default_factory=dict)
    status: str = ResourceStatus.ACTIVE.value
    visibility: Literal["lab", "restricted"] = "lab"
    reason: str = ""


class ResourceRevisionParams(BaseModel):
    data: dict[str, Any]
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = None
    visibility: Literal["lab", "restricted"] | None = None
    reason: str = Field(min_length=1)


class LocationParams(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    parent_id: UUID | None = None
    kind: str = Field(default="location", max_length=64)
    visibility: Literal["lab", "restricted"] = "lab"


class ContainerParams(BaseModel):
    id: UUID | None = None
    code: str = Field(min_length=1, max_length=128)
    lot_id: UUID | None = None
    location_id: UUID | None = None
    unit: str
    data: dict[str, Any] = Field(default_factory=dict)


class LotParams(BaseModel):
    id: UUID | None = None
    code: str = Field(min_length=1, max_length=128)
    supplier: str | None = None
    received_at: datetime | None = None
    expires_at: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class InventoryOperationParams(BaseModel):
    container_id: UUID
    quantity: Decimal
    unit: str
    idempotency_key: str = Field(min_length=1, max_length=255)
    reason: str = ""


class TransferParams(BaseModel):
    from_container_id: UUID
    to_container_id: UUID
    quantity: Decimal
    unit: str
    idempotency_key: str = Field(min_length=1, max_length=255)
    reason: str = ""


class ReservationParams(InventoryOperationParams):
    resource_id: UUID
    expires_at: datetime | None = None


class BookingParams(BaseModel):
    resource_id: UUID
    starts_at: datetime
    ends_at: datetime
    purpose: str = ""
    record_id: UUID | None = None
    idempotency_key: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_interval(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class BookingDecisionParams(BaseModel):
    action: Literal["approve", "reject", "cancel", "complete"]


class UsageParams(BaseModel):
    booking_id: UUID | None = None
    resource_id: UUID
    record_id: UUID | None = None
    record_version: int | None = None
    started_at: datetime
    ended_at: datetime | None = None
    notes: str = ""


class ServiceParams(BaseModel):
    resource_id: UUID
    kind: Literal["calibration", "maintenance", "fault", "decommission"]
    status: str
    starts_at: datetime
    ends_at: datetime | None = None
    due_at: datetime | None = None
    provider: str | None = None
    certificate_file_id: UUID | None = None
    notes: str = ""


class LabelParams(BaseModel):
    target_type: Literal["resource", "container", "location", "equipment"]
    target_id: UUID
    format: Literal["qr", "barcode"] = "qr"


class PrepareOutputParams(BaseModel):
    id: UUID
    resource_type_id: UUID
    name: str = Field(min_length=1)
    code: str = Field(min_length=1)
    data: dict[str, Any] = Field(default_factory=dict)
    visibility: Literal["lab", "restricted"] = "lab"
    lot: dict[str, Any] | None = None
    container: dict[str, Any] | None = None


BUILTIN_TEMPLATES = [
    {
        "id": "plasmid",
        "name": "质粒",
        "name_en": "Plasmid",
        "capabilities": {
            "inventory": True,
            "lots": True,
            "containers": True,
            "expiry": True,
        },
        "aimd": """---
id = "plasmid_resource"
name = "质粒"
version = "1.0.0"
kind = "resource_definition"
---

# 质粒

质粒名称：{{**var**|plasmid_name: str|required=true, title="质粒名称"}}

骨架：{{**var**|backbone: str | None|title="载体骨架"}}

抗性：{{**var**|resistance: str | None|title="抗性"}}

序列文件：{{**var**|sequence_file: File | None|title="序列文件"}}
""",
    },
    {
        "id": "general",
        "name": "通用资源",
        "name_en": "General resource",
        "capabilities": {"inventory": True, "containers": True},
        "aimd": """---
id = "general_resource"
name = "通用资源"
version = "1.0.0"
kind = "resource_definition"
---

# 通用资源

名称：{{**var**|resource_name: str|required=true, title="名称"}}

分类：{{**var**|category: str | None|title="分类"}}

描述：{{**var**|description: str | None|title="描述"}}
""",
    },
]


@router.get("/templates")
async def resource_templates(
    lab_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.read",
    )
    return {"templates": BUILTIN_TEMPLATES}


@router.get("/definition-versions")
async def resource_definition_versions(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    """List published resource-definition versions eligible for registration."""
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.read",
    )
    rows = (
        await db_session.execute(
            select(ProtocolVersion, Protocol, Project)
            .join(Protocol, Protocol.id == ProtocolVersion.protocol_id)
            .join(Project, Project.id == Protocol.project_id)
            .where(
                Project.lab_id == lab_id,
                Project.deleted_at.is_(None),
                Protocol.deleted_at.is_(None),
                Protocol.kind == ProtocolKind.RESOURCE_DEFINITION,
            )
            .order_by(Protocol.name, ProtocolVersion.created_at.desc())
        )
    ).all()
    registered = set(
        (
            await db_session.scalars(
                select(ResourceTypeRevision.protocol_version_id)
                .join(
                    ResourceType,
                    ResourceType.id
                    == ResourceTypeRevision.resource_type_id,
                )
                .where(ResourceType.lab_id == lab_id)
            )
        ).all()
    )
    return {
        "items": [
            {
                "id": version.id,
                "protocol_id": protocol.id,
                "protocol_uid": protocol.uid,
                "protocol_name": protocol.name,
                "project_id": project.id,
                "project_name": project.name,
                "version": version.version,
                "is_latest": version.version == protocol.latest_version,
                "registered": version.id in registered,
                "created_at": version.created_at,
            }
            for version, protocol, project in rows
        ]
    }


@router.get("/overview")
async def resource_overview(
    lab_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.read",
    )
    if await _refresh_user_notifications(
        db_session, lab_id=lab_id, user_id=current_user.id
    ):
        await db_session.commit()
    resources = await db_session.scalar(
        select(func.count(Resource.id)).where(
            Resource.lab_id == lab_id, Resource.archived_at.is_(None)
        )
    )
    depleted = await db_session.scalar(
        select(func.count(Resource.id)).where(
            Resource.lab_id == lab_id,
            Resource.status == ResourceStatus.DEPLETED.value,
            Resource.archived_at.is_(None),
        )
    )
    expiring = await db_session.scalar(
        select(func.count(ResourceLot.id))
        .join(Resource, Resource.id == ResourceLot.resource_id)
        .where(
            Resource.lab_id == lab_id,
            ResourceLot.expires_at.is_not(None),
            ResourceLot.expires_at <= _now() + timedelta(days=30),
        )
    )
    unread = await db_session.scalar(
        select(func.count(ResourceNotification.id)).where(
            ResourceNotification.lab_id == lab_id,
            ResourceNotification.user_id == current_user.id,
            ResourceNotification.read_at.is_(None),
        )
    )
    active_bookings = await db_session.scalar(
        select(func.count(EquipmentBooking.id)).where(
            EquipmentBooking.lab_id == lab_id,
            EquipmentBooking.ends_at >= func.now(),
            EquipmentBooking.status.in_(
                [BookingStatus.PENDING.value, BookingStatus.APPROVED.value]
            ),
        )
    )
    return {
        "resources": resources or 0,
        "depleted": depleted or 0,
        "expiring_within_30_days": expiring or 0,
        "unread_notifications": unread or 0,
        "active_bookings": active_bookings or 0,
    }


@router.get("/types")
async def list_resource_types(
    lab_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.read",
    )
    rows = (
        await db_session.scalars(
            select(ResourceType)
            .where(ResourceType.lab_id == lab_id, ResourceType.archived_at.is_(None))
            .order_by(ResourceType.name)
        )
    ).all()
    result = []
    for item in rows:
        revision = (
            await db_session.get(ResourceTypeRevision, item.current_revision_id)
            if item.current_revision_id
            else None
        )
        result.append(
            _model_data(
                item,
                current_revision=_model_data(revision) if revision else None,
            )
        )
    return {"items": result}


async def _register_type_revision(
    db_session: DBSession,
    *,
    lab_id: UUID,
    resource_type: ResourceType,
    params: ResourceTypeParams,
    user_id: UUID,
) -> ResourceTypeRevision:
    protocol_version = await db_session.get(
        ProtocolVersion, params.protocol_version_id
    )
    if protocol_version is None:
        raise HTTPException(status_code=404, detail="Protocol version not found")
    protocol = await db_session.get(Protocol, protocol_version.protocol_id)
    project = (
        await db_session.get(Project, protocol.project_id) if protocol else None
    )
    if (
        protocol is None
        or project is None
        or project.lab_id != lab_id
        or protocol.kind != ProtocolKind.RESOURCE_DEFINITION
    ):
        raise HTTPException(
            status_code=422,
            detail="Only a resource_definition Protocol in this Lab can be registered",
        )
    previous_revision = (
        await db_session.get(
            ResourceTypeRevision, resource_type.current_revision_id
        )
        if resource_type.current_revision_id
        else None
    )
    if previous_revision is not None:
        if previous_revision.protocol_id != protocol.id:
            raise HTTPException(
                status_code=409,
                detail=(
                    "A resource type revision must use a newer version of "
                    "the same resource-definition Protocol"
                ),
            )
        previous_semver = tuple(
            int(part) for part in previous_revision.protocol_version.split(".")
        )
        target_semver = tuple(
            int(part) for part in protocol_version.version.split(".")
        )
        if target_semver <= previous_semver:
            raise HTTPException(
                status_code=409,
                detail="Resource type revision must use a newer Protocol version",
            )
    latest_revision = await db_session.scalar(
        select(func.max(ResourceTypeRevision.revision)).where(
            ResourceTypeRevision.resource_type_id == resource_type.id
        )
    )
    revision = ResourceTypeRevision(
        resource_type_id=resource_type.id,
        protocol_id=protocol.id,
        protocol_version_id=protocol_version.id,
        protocol_version=protocol_version.version,
        revision=(latest_revision or 0) + 1,
        capabilities={
            key: bool(params.capabilities.get(key, False))
            for key in sorted(RESOURCE_CAPABILITIES)
        },
        booking_policy=params.booking_policy,
        schema_hash=_json_hash(protocol_version.json_schema),
        created_by_user_id=user_id,
    )
    db_session.add(revision)
    await db_session.flush()
    resource_type.current_revision_id = revision.id
    return revision


@router.post("/types")
async def register_resource_type(
    lab_id: UUID,
    params: ResourceTypeParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.manage",
    )
    resource_type = ResourceType(
        lab_id=lab_id,
        code=params.code,
        name=params.name,
        description=params.description,
        created_by_user_id=current_user.id,
    )
    db_session.add(resource_type)
    try:
        await db_session.flush()
        revision = await _register_type_revision(
            db_session,
            lab_id=lab_id,
            resource_type=resource_type,
            params=params,
            user_id=current_user.id,
        )
        await db_session.commit()
    except IntegrityError as error:
        await db_session.rollback()
        raise HTTPException(
            status_code=409, detail="Resource type code already exists"
        ) from error
    return _model_data(resource_type, current_revision=_model_data(revision))


@router.post("/types/{resource_type_id}/revisions")
async def revise_resource_type(
    lab_id: UUID,
    resource_type_id: UUID,
    params: ResourceTypeParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    resource_type = await _resource_type(db_session, lab_id, resource_type_id)
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.manage",
        resource_type_id=resource_type.id,
    )
    resource_type.name = params.name
    resource_type.description = params.description
    revision = await _register_type_revision(
        db_session,
        lab_id=lab_id,
        resource_type=resource_type,
        params=params,
        user_id=current_user.id,
    )
    await db_session.commit()
    return _model_data(resource_type, current_revision=_model_data(revision))


@router.delete("/types/{resource_type_id}")
async def archive_resource_type(
    lab_id: UUID,
    resource_type_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    resource_type = await _resource_type(db_session, lab_id, resource_type_id)
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.manage",
        resource_type_id=resource_type.id,
    )
    resource_type.archived_at = _now()
    await db_session.commit()
    return {"archived": True}


@router.get("/resources")
async def list_resources(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    q: str = "",
    resource_type_id: UUID | None = None,
    status: str | None = None,
    field_path: str | None = None,
    field_value: str | None = None,
    numeric_min: Decimal | None = None,
    numeric_max: Decimal | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.read",
        resource_type_id=resource_type_id,
    )
    conditions = [Resource.lab_id == lab_id, Resource.archived_at.is_(None)]
    if resource_type_id:
        conditions.append(Resource.resource_type_id == resource_type_id)
    if status:
        conditions.append(Resource.status == status)
    if q:
        conditions.append(
            or_(
                Resource.name.ilike(f"%{q}%"),
                Resource.code.ilike(f"%{q}%"),
            )
        )
    statement = select(Resource).where(*conditions)
    if field_path:
        index_conditions = [
            ResourceFieldIndex.resource_id == Resource.id,
            ResourceFieldIndex.resource_revision_id == Resource.current_revision_id,
            ResourceFieldIndex.path == field_path,
        ]
        if field_value is not None:
            index_conditions.append(ResourceFieldIndex.value_text.ilike(f"%{field_value}%"))
        if numeric_min is not None:
            index_conditions.append(ResourceFieldIndex.value_numeric >= numeric_min)
        if numeric_max is not None:
            index_conditions.append(ResourceFieldIndex.value_numeric <= numeric_max)
        statement = statement.where(
            select(ResourceFieldIndex.id).where(*index_conditions).exists()
        )
    candidates = (
        await db_session.scalars(
            statement.order_by(Resource.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = []
    for item in candidates:
        if not await _can_read_resource(db_session, current_user.id, item):
            continue
        revision = await db_session.get(ResourceRevision, item.current_revision_id)
        items.append(
            _model_data(
                item,
                data=revision.data if revision else {},
                revision=revision.revision if revision else None,
            )
        )
    return {"items": items, "page": page, "page_size": page_size}


@router.post("/resources")
async def create_resource(
    lab_id: UUID,
    params: ResourceParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    if params.status not in RESOURCE_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid resource status")
    resource_type = await _resource_type(
        db_session, lab_id, params.resource_type_id
    )
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.operate",
        resource_type_id=resource_type.id,
    )
    type_revision = await _current_type_revision(db_session, resource_type)
    protocol_version = await db_session.get(
        ProtocolVersion, type_revision.protocol_version_id
    )
    if protocol_version is None:
        raise HTTPException(status_code=409, detail="Resource Schema was not found")
    _validate_data(protocol_version.json_schema, params.data)
    resource = Resource(
        lab_id=lab_id,
        resource_type_id=resource_type.id,
        name=params.name,
        code=params.code,
        status=params.status,
        visibility=params.visibility,
        created_by_user_id=current_user.id,
    )
    db_session.add(resource)
    try:
        await db_session.flush()
        revision = ResourceRevision(
            resource_id=resource.id,
            resource_type_revision_id=type_revision.id,
            revision=1,
            data=params.data,
            revision_kind="initial",
            reason=params.reason or "Resource registered",
            created_by_user_id=current_user.id,
        )
        db_session.add(revision)
        await db_session.flush()
        resource.current_revision_id = revision.id
        db_session.add_all(
            build_resource_indexes(
                resource_type_id=resource.resource_type_id,
                resource_id=resource.id,
                revision=revision,
            )
        )
        await db_session.commit()
    except IntegrityError as error:
        await db_session.rollback()
        raise HTTPException(
            status_code=409, detail="Resource stable code already exists"
        ) from error
    return _model_data(resource, data=revision.data, revision=revision.revision)


@router.get("/resources/{resource_id}")
async def get_resource(
    lab_id: UUID,
    resource_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    resource = await _resource(db_session, lab_id, resource_id, archived=True)
    if not await _can_read_resource(db_session, current_user.id, resource):
        raise HTTPException(status_code=403, detail="Permission denied")
    revisions = (
        await db_session.scalars(
            select(ResourceRevision)
            .where(ResourceRevision.resource_id == resource.id)
            .order_by(ResourceRevision.revision.desc())
        )
    ).all()
    containers = (
        await db_session.execute(
            select(ResourceContainer, InventoryBalance)
            .outerjoin(
                InventoryBalance,
                InventoryBalance.container_id == ResourceContainer.id,
            )
            .where(
                ResourceContainer.resource_id == resource.id,
                ResourceContainer.archived_at.is_(None),
            )
            .order_by(ResourceContainer.code)
        )
    ).all()
    lots = (
        await db_session.scalars(
            select(ResourceLot)
            .where(ResourceLot.resource_id == resource.id)
            .order_by(ResourceLot.created_at.desc())
        )
    ).all()
    events = (
        await db_session.scalars(
            select(InventoryEvent)
            .where(InventoryEvent.resource_id == resource.id)
            .order_by(InventoryEvent.created_at.desc())
            .limit(100)
        )
    ).all()
    links = (
        await db_session.scalars(
            select(RecordResourceLink)
            .where(RecordResourceLink.resource_id == resource.id)
            .order_by(RecordResourceLink.created_at.desc())
        )
    ).all()
    lineage = (
        await db_session.scalars(
            select(ResourceLineage).where(
                or_(
                    ResourceLineage.parent_resource_id == resource.id,
                    ResourceLineage.child_resource_id == resource.id,
                )
            )
        )
    ).all()
    service_events = (
        await db_session.scalars(
            select(EquipmentServiceEvent)
            .where(EquipmentServiceEvent.resource_id == resource.id)
            .order_by(EquipmentServiceEvent.starts_at.desc())
        )
    ).all()
    return _model_data(
        resource,
        current_revision=(
            _model_data(revisions[0]) if revisions else None
        ),
        revisions=[_model_data(item) for item in revisions],
        data=revisions[0].data if revisions else {},
        revision=revisions[0].revision if revisions else None,
        lots=[_model_data(item) for item in lots],
        containers=[
            _model_data(
                container,
                balance=(
                    {
                        **_model_data(balance),
                        "available": balance.available,
                    }
                    if balance
                    else None
                ),
            )
            for container, balance in containers
        ],
        inventory_events=[_model_data(item) for item in events],
        record_links=[_model_data(item) for item in links],
        lineage=[_model_data(item) for item in lineage],
        equipment_service_events=[
            _model_data(item) for item in service_events
        ],
    )


@router.post("/resources/{resource_id}/revisions")
async def revise_resource(
    lab_id: UUID,
    resource_id: UUID,
    params: ResourceRevisionParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    resource = await _resource(db_session, lab_id, resource_id)
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.operate",
        resource_type_id=resource.resource_type_id,
        resource_id=resource.id,
    )
    type_revision = await db_session.get(
        ResourceTypeRevision,
        (
            await db_session.get(ResourceRevision, resource.current_revision_id)
        ).resource_type_revision_id,
    )
    protocol_version = await db_session.get(
        ProtocolVersion, type_revision.protocol_version_id
    )
    _validate_data(protocol_version.json_schema, params.data)
    latest_revision = await db_session.scalar(
        select(func.max(ResourceRevision.revision))
        .where(ResourceRevision.resource_id == resource.id)
        .with_for_update()
    )
    revision = ResourceRevision(
        resource_id=resource.id,
        resource_type_revision_id=type_revision.id,
        revision=(latest_revision or 0) + 1,
        data=params.data,
        revision_kind="correction",
        reason=params.reason,
        source_revision_id=resource.current_revision_id,
        created_by_user_id=current_user.id,
    )
    db_session.add(revision)
    await db_session.flush()
    resource.current_revision_id = revision.id
    if params.name:
        resource.name = params.name
    if params.status:
        if params.status not in RESOURCE_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid resource status")
        resource.status = params.status
    if params.visibility:
        resource.visibility = params.visibility
    db_session.add_all(
        build_resource_indexes(
            resource_type_id=resource.resource_type_id,
            resource_id=resource.id,
            revision=revision,
        )
    )
    await db_session.commit()
    return _model_data(resource, current_revision=_model_data(revision))


@router.delete("/resources/{resource_id}")
async def archive_resource(
    lab_id: UUID,
    resource_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    resource = await _resource(db_session, lab_id, resource_id)
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.manage",
        resource_id=resource.id,
        resource_type_id=resource.resource_type_id,
    )
    resource.archived_at = _now()
    resource.status = ResourceStatus.ARCHIVED.value
    await db_session.commit()
    return {"archived": True}


@router.post("/resources/{resource_id}/lots")
async def create_lot(
    lab_id: UUID,
    resource_id: UUID,
    params: LotParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    resource = await _resource(db_session, lab_id, resource_id)
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="inventory.operate",
        resource_id=resource.id,
        resource_type_id=resource.resource_type_id,
    )
    lot = ResourceLot(
        id=params.id,
        resource_id=resource.id,
        code=params.code,
        supplier=params.supplier,
        received_at=params.received_at,
        expires_at=params.expires_at,
        data=params.data,
    )
    db_session.add(lot)
    await db_session.commit()
    return _model_data(lot)


@router.post("/resources/{resource_id}/containers")
async def create_container(
    lab_id: UUID,
    resource_id: UUID,
    params: ContainerParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    resource = await _resource(db_session, lab_id, resource_id)
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="inventory.operate",
        resource_id=resource.id,
        resource_type_id=resource.resource_type_id,
        location_id=params.location_id,
    )
    if params.lot_id:
        lot = await db_session.get(ResourceLot, params.lot_id)
        if lot is None or lot.resource_id != resource.id:
            raise HTTPException(status_code=422, detail="Lot belongs to another resource")
    if params.location_id:
        location = await db_session.get(ResourceLocation, params.location_id)
        if location is None or location.lab_id != lab_id:
            raise HTTPException(status_code=422, detail="Location belongs to another Lab")
    try:
        unit = normalize_ucum_unit(params.unit)
    except UnitError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    container = ResourceContainer(
        id=params.id,
        lab_id=lab_id,
        resource_id=resource.id,
        lot_id=params.lot_id,
        location_id=params.location_id,
        code=params.code,
        unit=unit,
        data=params.data,
    )
    db_session.add(container)
    await db_session.flush()
    db_session.add(
        InventoryBalance(
            container_id=container.id,
            on_hand=Decimal("0"),
            reserved=Decimal("0"),
            unit=unit,
            version=0,
        )
    )
    await db_session.commit()
    return _model_data(container)


@router.post("/inventory/operations/{kind}")
async def inventory_operation(
    lab_id: UUID,
    kind: Literal["receipt", "consumption", "adjustment", "count", "disposal"],
    params: InventoryOperationParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    container = await db_session.get(ResourceContainer, params.container_id)
    if container is None or container.lab_id != lab_id:
        raise HTTPException(status_code=404, detail="Container not found")
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="inventory.operate",
        resource_id=container.resource_id,
        location_id=container.location_id,
    )
    try:
        if kind == "count":
            event = await set_inventory_on_hand(
                db_session,
                lab_id=lab_id,
                actor_user_id=current_user.id,
                container_id=params.container_id,
                quantity=params.quantity,
                unit=params.unit,
                idempotency_key=params.idempotency_key,
                reason=params.reason,
            )
        else:
            if params.quantity == 0:
                raise InventoryError(
                    "inventory operation quantity cannot be zero"
                )
            if kind != "adjustment" and params.quantity < 0:
                raise InventoryError(
                    f"{kind} quantity must be greater than zero"
                )
            signed_quantity = params.quantity
            direction = (
                1
                if kind == "receipt"
                or (kind == "adjustment" and signed_quantity > 0)
                else -1
            )
            event = await apply_inventory_event(
                db_session,
                lab_id=lab_id,
                actor_user_id=current_user.id,
                container_id=params.container_id,
                kind=kind,
                quantity=abs(signed_quantity),
                unit=params.unit,
                idempotency_key=params.idempotency_key,
                on_hand_direction=direction,
                reason=params.reason,
            )
        await db_session.commit()
    except InventoryError as error:
        await db_session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _model_data(event)


@router.post("/inventory/transfers")
async def inventory_transfer(
    lab_id: UUID,
    params: TransferParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="inventory.operate",
    )
    try:
        event = await transfer_inventory(
            db_session,
            lab_id=lab_id,
            actor_user_id=current_user.id,
            from_container_id=params.from_container_id,
            to_container_id=params.to_container_id,
            quantity=params.quantity,
            unit=params.unit,
            idempotency_key=params.idempotency_key,
            reason=params.reason,
        )
        await db_session.commit()
    except InventoryError as error:
        await db_session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _model_data(event)


@router.post("/inventory/reservations")
async def create_reservation(
    lab_id: UUID,
    params: ReservationParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="inventory.operate",
        resource_id=params.resource_id,
    )
    try:
        reservation = await reserve_inventory(
            db_session,
            lab_id=lab_id,
            resource_id=params.resource_id,
            container_id=params.container_id,
            quantity=params.quantity,
            unit=params.unit,
            actor_user_id=current_user.id,
            idempotency_key=params.idempotency_key,
            expires_at=params.expires_at,
            reason=params.reason,
        )
        await db_session.commit()
    except InventoryError as error:
        await db_session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _model_data(reservation)


@router.get("/inventory/reservations")
async def list_reservations(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    resource_id: UUID | None = None,
    status: str | None = None,
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="inventory.read",
        resource_id=resource_id,
    )
    conditions = [InventoryReservation.lab_id == lab_id]
    if resource_id:
        conditions.append(InventoryReservation.resource_id == resource_id)
    if status:
        conditions.append(InventoryReservation.status == status)
    rows = (
        await db_session.scalars(
            select(InventoryReservation)
            .where(*conditions)
            .order_by(InventoryReservation.created_at.desc())
        )
    ).all()
    return {"items": [_model_data(item) for item in rows]}


@router.post("/inventory/reservations/{reservation_id}/release")
async def release_reservation(
    lab_id: UUID,
    reservation_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    idempotency_key: str,
    reason: str = "",
):
    reservation = await db_session.get(InventoryReservation, reservation_id)
    if reservation is None or reservation.lab_id != lab_id:
        raise HTTPException(status_code=404, detail="Reservation not found")
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="inventory.operate",
        resource_id=reservation.resource_id,
    )
    try:
        event = await release_inventory_reservation(
            db_session,
            reservation=reservation,
            actor_user_id=current_user.id,
            idempotency_key=idempotency_key,
            reason=reason,
        )
        await db_session.commit()
    except InventoryError as error:
        await db_session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _model_data(event)


@router.get("/inventory/events")
async def inventory_events(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    resource_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="inventory.read",
        resource_id=resource_id,
    )
    conditions = [InventoryEvent.lab_id == lab_id]
    if resource_id:
        conditions.append(InventoryEvent.resource_id == resource_id)
    rows = (
        await db_session.scalars(
            select(InventoryEvent)
            .where(*conditions)
            .order_by(InventoryEvent.created_at.desc())
            .limit(limit)
        )
    ).all()
    return {"items": [_model_data(item) for item in rows]}


@router.get("/locations")
async def list_locations(
    lab_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.read",
    )
    rows = (
        await db_session.scalars(
            select(ResourceLocation)
            .where(
                ResourceLocation.lab_id == lab_id,
                ResourceLocation.archived_at.is_(None),
            )
            .order_by(ResourceLocation.path)
        )
    ).all()
    return {"items": [_model_data(item) for item in rows]}


@router.post("/locations")
async def create_location(
    lab_id: UUID,
    params: LocationParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.manage",
        location_id=params.parent_id,
    )
    parent = (
        await db_session.get(ResourceLocation, params.parent_id)
        if params.parent_id
        else None
    )
    if parent is not None and parent.lab_id != lab_id:
        raise HTTPException(status_code=422, detail="Parent location is in another Lab")
    path = f"{parent.path}/{params.code}" if parent else f"/{params.code}"
    location = ResourceLocation(
        lab_id=lab_id,
        parent_id=params.parent_id,
        code=params.code,
        name=params.name,
        kind=params.kind,
        path=path,
        visibility=params.visibility,
    )
    db_session.add(location)
    await db_session.commit()
    return _model_data(location)


@router.post("/bookings")
async def create_booking(
    lab_id: UUID,
    params: BookingParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    resource = await _resource(db_session, lab_id, params.resource_id)
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="equipment.book",
        resource_id=resource.id,
        resource_type_id=resource.resource_type_id,
    )
    resource_type = await _resource_type(
        db_session, lab_id, resource.resource_type_id
    )
    type_revision = await _current_type_revision(db_session, resource_type)
    if not type_revision.capabilities.get("booking"):
        raise HTTPException(status_code=422, detail="Resource is not bookable equipment")
    policy = type_revision.booking_policy
    status = (
        BookingStatus.APPROVED.value
        if policy in {"none", "auto"}
        else BookingStatus.PENDING.value
    )
    existing = await db_session.scalar(
        select(EquipmentBooking).where(
            EquipmentBooking.lab_id == lab_id,
            EquipmentBooking.idempotency_key == params.idempotency_key,
        )
    )
    if existing:
        return _model_data(existing)
    booking = EquipmentBooking(
        lab_id=lab_id,
        resource_id=resource.id,
        user_id=current_user.id,
        starts_at=params.starts_at,
        ends_at=params.ends_at,
        status=status,
        approval_policy=policy,
        purpose=params.purpose,
        record_id=params.record_id,
        idempotency_key=params.idempotency_key,
    )
    db_session.add(booking)
    try:
        await db_session.commit()
    except IntegrityError as error:
        await db_session.rollback()
        raise HTTPException(
            status_code=409, detail="Equipment is already booked in that time range"
        ) from error
    return _model_data(booking)


@router.get("/bookings")
async def list_bookings(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    resource_id: UUID | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.read",
        resource_id=resource_id,
    )
    conditions = [EquipmentBooking.lab_id == lab_id]
    if resource_id:
        conditions.append(EquipmentBooking.resource_id == resource_id)
    if starts_at:
        conditions.append(EquipmentBooking.ends_at > starts_at)
    if ends_at:
        conditions.append(EquipmentBooking.starts_at < ends_at)
    rows = (
        await db_session.scalars(
            select(EquipmentBooking)
            .where(*conditions)
            .order_by(EquipmentBooking.starts_at)
        )
    ).all()
    return {"items": [_model_data(item) for item in rows]}


@router.post("/bookings/{booking_id}/decision")
async def decide_booking(
    lab_id: UUID,
    booking_id: UUID,
    params: BookingDecisionParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    booking = await db_session.get(EquipmentBooking, booking_id)
    if booking is None or booking.lab_id != lab_id:
        raise HTTPException(status_code=404, detail="Booking not found")
    if params.action == "cancel" and booking.user_id == current_user.id:
        pass
    else:
        await _require(
            db_session,
            user_id=current_user.id,
            lab_id=lab_id,
            capability="resource.custody",
            resource_id=booking.resource_id,
        )
    mapping = {
        "approve": BookingStatus.APPROVED.value,
        "reject": BookingStatus.REJECTED.value,
        "cancel": BookingStatus.CANCELLED.value,
        "complete": BookingStatus.COMPLETED.value,
    }
    booking.status = mapping[params.action]
    if params.action == "approve":
        booking.approved_by_user_id = current_user.id
    await db_session.commit()
    return _model_data(booking)


@router.post("/equipment/usages")
async def create_equipment_usage(
    lab_id: UUID,
    params: UsageParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    resource = await _resource(db_session, lab_id, params.resource_id)
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.operate",
        resource_id=resource.id,
    )
    usage = EquipmentUsage(
        booking_id=params.booking_id,
        resource_id=params.resource_id,
        user_id=current_user.id,
        record_id=params.record_id,
        record_version=params.record_version,
        started_at=params.started_at,
        ended_at=params.ended_at,
        notes=params.notes,
    )
    db_session.add(usage)
    await db_session.commit()
    return _model_data(usage)


@router.post("/equipment/service-events")
async def create_service_event(
    lab_id: UUID,
    params: ServiceParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    resource = await _resource(db_session, lab_id, params.resource_id)
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="equipment.service",
        resource_id=resource.id,
    )
    event = EquipmentServiceEvent(
        lab_id=lab_id,
        resource_id=params.resource_id,
        kind=params.kind,
        status=params.status,
        starts_at=params.starts_at,
        ends_at=params.ends_at,
        due_at=params.due_at,
        provider=params.provider,
        certificate_file_id=params.certificate_file_id,
        notes=params.notes,
        actor_user_id=current_user.id,
    )
    db_session.add(event)
    if params.kind == "fault" and params.status not in {"resolved", "closed"}:
        resource.status = ResourceStatus.QUARANTINED.value
    if params.kind == "decommission":
        resource.status = ResourceStatus.RETIRED.value
    await db_session.commit()
    return _model_data(event)


@router.get("/equipment/service-events")
async def list_service_events(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    resource_id: UUID | None = None,
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.read",
        resource_id=resource_id,
    )
    conditions = [EquipmentServiceEvent.lab_id == lab_id]
    if resource_id:
        conditions.append(EquipmentServiceEvent.resource_id == resource_id)
    rows = (
        await db_session.scalars(
            select(EquipmentServiceEvent)
            .where(*conditions)
            .order_by(EquipmentServiceEvent.starts_at.desc())
        )
    ).all()
    return {"items": [_model_data(item) for item in rows]}


@router.get("/notifications")
async def list_notifications(
    lab_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.read",
    )
    if await _refresh_user_notifications(
        db_session, lab_id=lab_id, user_id=current_user.id
    ):
        await db_session.commit()
    rows = (
        await db_session.scalars(
            select(ResourceNotification)
            .where(
                ResourceNotification.lab_id == lab_id,
                ResourceNotification.user_id == current_user.id,
            )
            .order_by(ResourceNotification.created_at.desc())
        )
    ).all()
    return {"items": [_model_data(item) for item in rows]}


@router.post("/notifications/{notification_id}/read")
async def read_notification(
    lab_id: UUID,
    notification_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    item = await db_session.get(ResourceNotification, notification_id)
    if (
        item is None
        or item.lab_id != lab_id
        or item.user_id != current_user.id
    ):
        raise HTTPException(status_code=404, detail="Notification not found")
    item.read_at = _now()
    await db_session.commit()
    return {"read": True}


@router.post("/labels")
async def create_label(
    lab_id: UUID,
    params: LabelParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.operate",
    )
    label = ResourceLabel(
        lab_id=lab_id,
        code=f"AR-{uuid4().hex.upper()}",
        target_type=params.target_type,
        target_id=params.target_id,
        format=params.format,
        created_by_user_id=current_user.id,
    )
    db_session.add(label)
    await db_session.commit()
    return _model_data(
        label,
        payload=f"airalogy://resource-label/{label.code}",
    )


@router.get("/labels/resolve/{code}")
async def resolve_label(
    lab_id: UUID,
    code: str,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.read",
    )
    label = await db_session.scalar(
        select(ResourceLabel).where(
            ResourceLabel.lab_id == lab_id,
            ResourceLabel.code == code,
            ResourceLabel.archived_at.is_(None),
        )
    )
    if label is None:
        raise HTTPException(status_code=404, detail="Label not found")
    return _model_data(label)


@router.get("/resolver/search")
async def resolver_search(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    q: str = "",
    resource_type_id: UUID | None = None,
    resource_type: str | None = None,
    role: Literal["input", "output", "reference", "equipment"] = "reference",
    limit: int = Query(default=20, ge=1, le=100),
):
    if role == "output":
        return {"items": []}
    if resource_type_id is None and resource_type:
        resource_type_id = await db_session.scalar(
            select(ResourceType.id).where(
                ResourceType.lab_id == lab_id,
                func.lower(ResourceType.code) == resource_type.strip().lower(),
                ResourceType.archived_at.is_(None),
            )
        )
        if resource_type_id is None:
            return {"items": []}
    response = await list_resources(
        lab_id,
        current_user,
        db_session,
        q=q,
        resource_type_id=resource_type_id,
        page=1,
        page_size=limit,
    )
    return {
        "items": [
            {
                "id": item["id"],
                "label": item["name"],
                "entity": "resource",
                "snapshot": {
                    "name": item["name"],
                    "code": item["code"],
                    "status": item["status"],
                },
            }
            for item in response["items"]
        ]
    }


@router.get("/resolver/resources/{resource_id}/availability")
async def resolver_availability(
    lab_id: UUID,
    resource_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    resource = await _resource(db_session, lab_id, resource_id)
    if not await _can_read_resource(db_session, current_user.id, resource):
        raise HTTPException(status_code=403, detail="Permission denied")
    rows = (
        await db_session.execute(
            select(ResourceContainer, ResourceLot, InventoryBalance)
            .outerjoin(ResourceLot, ResourceLot.id == ResourceContainer.lot_id)
            .outerjoin(
                InventoryBalance,
                InventoryBalance.container_id == ResourceContainer.id,
            )
            .where(
                ResourceContainer.resource_id == resource.id,
                ResourceContainer.archived_at.is_(None),
            )
            .order_by(ResourceContainer.code)
        )
    ).all()
    bookings = (
        await db_session.scalars(
            select(EquipmentBooking)
            .where(
                EquipmentBooking.lab_id == lab_id,
                EquipmentBooking.resource_id == resource.id,
                EquipmentBooking.user_id == current_user.id,
                EquipmentBooking.status.in_(
                    [BookingStatus.PENDING.value, BookingStatus.APPROVED.value]
                ),
                EquipmentBooking.ends_at > _now(),
            )
            .order_by(EquipmentBooking.starts_at)
            .limit(50)
        )
    ).all()
    return {
        "resource": {
            "id": resource.id,
            "name": resource.name,
            "code": resource.code,
            "status": resource.status,
        },
        "containers": [
            {
                **_model_data(container),
                "lot": _model_data(lot) if lot else None,
                "balance": (
                    {
                        "on_hand": balance.on_hand,
                        "reserved": balance.reserved,
                        "available": balance.available,
                        "unit": balance.unit,
                    }
                    if balance
                    else None
                ),
            }
            for container, lot, balance in rows
        ],
        "equipment_bookings": [
            {
                "id": booking.id,
                "starts_at": booking.starts_at,
                "ends_at": booking.ends_at,
                "status": booking.status,
                "label": (
                    f"{booking.starts_at.isoformat()} – "
                    f"{booking.ends_at.isoformat()}"
                ),
                "available": booking.status == BookingStatus.APPROVED.value,
            }
            for booking in bookings
        ],
    }


@router.get("/resolver/equipment/{resource_id}/slots")
async def resolver_equipment_slots(
    lab_id: UUID,
    resource_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _resource(db_session, lab_id, resource_id)
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="equipment.book",
        resource_id=resource_id,
    )
    bookings = (
        await db_session.scalars(
            select(EquipmentBooking)
            .where(
                EquipmentBooking.resource_id == resource_id,
                EquipmentBooking.status.in_(
                    [BookingStatus.PENDING.value, BookingStatus.APPROVED.value]
                ),
                EquipmentBooking.starts_at < ends_at,
                EquipmentBooking.ends_at > starts_at,
            )
            .order_by(EquipmentBooking.starts_at)
        )
    ).all()
    return {
        "window": {"starts_at": starts_at, "ends_at": ends_at},
        "busy": [
            {"starts_at": item.starts_at, "ends_at": item.ends_at}
            for item in bookings
        ],
    }


@router.post("/resolver/prepare-output")
async def prepare_output(
    lab_id: UUID,
    params: PrepareOutputParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    resource_type = await _resource_type(
        db_session, lab_id, params.resource_type_id
    )
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.operate",
        resource_type_id=resource_type.id,
    )
    revision = await _current_type_revision(db_session, resource_type)
    protocol_version = await db_session.get(
        ProtocolVersion, revision.protocol_version_id
    )
    _validate_data(protocol_version.json_schema, params.data)
    prepared = params.model_dump(mode="json")
    if prepared.get("lot") and not prepared["lot"].get("id"):
        prepared["lot"]["id"] = str(uuid4())
    if prepared.get("container") and not prepared["container"].get("id"):
        prepared["container"]["id"] = str(uuid4())
    return {
        "resource_ref": {
            "id": str(params.id),
            "entity": "resource",
            "label": params.name,
            "snapshot": {"name": params.name, "code": params.code},
            "prepared_output": prepared,
        }
    }


@router.post("/imports/dry-run")
async def dry_run_import(
    lab_id: UUID,
    resource_type_id: UUID,
    file: UploadFile,
    current_user: CurrentUser,
    db_session: DBSession,
    name_field: str = "name",
    code_field: str = "code",
    field_mapping: str | None = None,
):
    resource_type = await _resource_type(db_session, lab_id, resource_type_id)
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.operate",
        resource_type_id=resource_type.id,
    )
    revision = await _current_type_revision(db_session, resource_type)
    protocol_version = await db_session.get(
        ProtocolVersion, revision.protocol_version_id
    )
    rows = await _read_import_rows(file)
    mapping = _parse_field_mapping(field_mapping)
    results = []
    for index, row in enumerate(rows):
        mapped = _map_import_row(
            row,
            name_field=name_field,
            code_field=code_field,
            field_mapping=mapping,
        )
        issues = _validation_issues(
            protocol_version.json_schema, mapped["data"]
        )
        if not mapped["name"]:
            issues.append({"path": name_field, "message": "Resource name is required"})
        if not mapped["code"]:
            issues.append({"path": code_field, "message": "Stable code is required"})
        results.append(
            {
                "row": index + 1,
                "valid": not issues,
                "issues": issues,
                "mapped": mapped,
            }
        )
    return {
        "rows": results,
        "valid": sum(1 for item in results if item["valid"]),
        "invalid": sum(1 for item in results if not item["valid"]),
        "dry_run": True,
    }


@router.post("/imports")
async def commit_import(
    lab_id: UUID,
    resource_type_id: UUID,
    file: UploadFile,
    current_user: CurrentUser,
    db_session: DBSession,
    name_field: str = "name",
    code_field: str = "code",
    field_mapping: str | None = None,
):
    resource_type = await _resource_type(
        db_session, lab_id, resource_type_id
    )
    await _require(
        db_session,
        user_id=current_user.id,
        lab_id=lab_id,
        capability="resource.operate",
        resource_type_id=resource_type.id,
    )
    revision = await _current_type_revision(db_session, resource_type)
    protocol_version = await db_session.get(
        ProtocolVersion, revision.protocol_version_id
    )
    rows = await _read_import_rows(file)
    mapping = _parse_field_mapping(field_mapping)
    mapped_rows = [
        _map_import_row(
            row,
            name_field=name_field,
            code_field=code_field,
            field_mapping=mapping,
        )
        for row in rows
    ]
    errors = []
    for index, mapped in enumerate(mapped_rows):
        issues = _validation_issues(
            protocol_version.json_schema, mapped["data"]
        )
        if not mapped["name"]:
            issues.append({"path": name_field, "message": "Resource name is required"})
        if not mapped["code"]:
            issues.append({"path": code_field, "message": "Stable code is required"})
        if issues:
            errors.append({"row": index + 1, "issues": issues})
    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Import contains invalid rows",
                "rows": errors,
            },
        )

    created: list[Resource] = []
    for mapped in mapped_rows:
        resource = Resource(
            lab_id=lab_id,
            resource_type_id=resource_type.id,
            name=mapped["name"],
            code=mapped["code"],
            status=ResourceStatus.ACTIVE.value,
            visibility=mapped["visibility"],
            created_by_user_id=current_user.id,
        )
        db_session.add(resource)
        await db_session.flush()
        resource_revision = ResourceRevision(
            resource_id=resource.id,
            resource_type_revision_id=revision.id,
            revision=1,
            data=mapped["data"],
            revision_kind="import",
            reason=f"Imported from {file.filename or 'file'}",
            created_by_user_id=current_user.id,
        )
        db_session.add(resource_revision)
        await db_session.flush()
        resource.current_revision_id = resource_revision.id
        db_session.add_all(
            build_resource_indexes(
                resource_type_id=resource_type.id,
                resource_id=resource.id,
                revision=resource_revision,
            )
        )
        created.append(resource)
    try:
        await db_session.commit()
    except IntegrityError as error:
        await db_session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Import conflicts with an existing stable resource code",
        ) from error
    return {
        "created": len(created),
        "items": [_model_data(item) for item in created],
        "dry_run": False,
    }
