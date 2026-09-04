"""Derived Capability Registry and Research Environment snapshots.

The registry deliberately does not persist a second copy of scientific methods.
Protocol versions, allowlisted tools, and resource definitions remain the sources
of truth; this module only projects them into one discoverable contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.protocol import Protocol, ProtocolKind
from app.models.protocol_version import ProtocolVersion
from app.models.research_execution import (
    ResearchInstrumentCommand,
    ResearchInstrumentGateway,
)
from app.models.resource import (
    Resource,
    ResourceStatus,
    ResourceType,
    ResourceTypeRevision,
)
from app.services.research_compute import (
    compute_environment_snapshot,
    latest_compute_environment_rows,
)
from app.services.research_human_work import (
    HUMAN_WORK_CAPABILITY_KEY,
    HUMAN_WORK_CAPABILITY_VERSION,
    HumanWorkRequest,
)
from app.services.research_services import (
    latest_service_offering_rows,
    offering_snapshot,
)
from app.services.research_tools import ResearchToolDefinition, research_tool_catalog

CapabilityKind = Literal[
    "protocol", "tool", "human", "resource", "instrument", "service", "compute"
]


@dataclass(frozen=True)
class ResearchCapabilityDescriptor:
    key: str
    version: str
    kind: CapabilityKind
    name: str
    description: str
    source_type: str
    source_id: str
    source_revision_id: str
    executor_types: list[str]
    risk: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    available: bool
    unavailable_reason: str = ""
    metadata: dict[str, Any] | None = None

    def payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metadata"] = payload["metadata"] or {}
        return payload


def tool_capability(definition: ResearchToolDefinition) -> ResearchCapabilityDescriptor:
    return ResearchCapabilityDescriptor(
        key=f"tool:{definition.key}",
        version=definition.version,
        kind="tool",
        name=definition.name,
        description=definition.description,
        source_type="research_tool",
        source_id=definition.key,
        source_revision_id=f"{definition.key}@{definition.version}",
        executor_types=[definition.executor_type],
        risk=definition.risk,
        input_schema=definition.input_schema,
        output_schema=definition.output_schema,
        available=definition.available,
        unavailable_reason=definition.unavailable_reason,
        metadata={"tool_key": definition.key},
    )


def protocol_capability(
    protocol: Protocol,
    version: ProtocolVersion,
) -> ResearchCapabilityDescriptor:
    return ResearchCapabilityDescriptor(
        key=f"protocol:{protocol.id}",
        version=version.version,
        kind="protocol",
        name=protocol.name,
        description=protocol.description or "",
        source_type="protocol_version",
        source_id=str(protocol.id),
        source_revision_id=str(version.id),
        executor_types=["human"],
        risk="physical_or_structured_execution",
        input_schema=version.json_schema or {},
        output_schema=version.json_schema or {},
        available=True,
        metadata={"protocol_uid": protocol.uid},
    )


def human_work_capability() -> ResearchCapabilityDescriptor:
    """Return the built-in contract for bounded non-Protocol human work."""

    return ResearchCapabilityDescriptor(
        key=HUMAN_WORK_CAPABILITY_KEY,
        version=HUMAN_WORK_CAPABILITY_VERSION,
        kind="human",
        name="Structured human work",
        description=(
            "Assign a bounded, schema-validated observation, collection, or review "
            "task that is not a scientific method execution."
        ),
        source_type="platform_human_work_contract",
        source_id=HUMAN_WORK_CAPABILITY_KEY,
        source_revision_id=(
            f"{HUMAN_WORK_CAPABILITY_KEY}@{HUMAN_WORK_CAPABILITY_VERSION}"
        ),
        executor_types=["human"],
        risk="human_execution",
        input_schema=HumanWorkRequest.model_json_schema(),
        output_schema={
            "type": "object",
            "required": ["values", "data_asset_version_ids"],
            "properties": {
                "values": {"type": "object"},
                "data_asset_version_ids": {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                },
            },
            "additionalProperties": False,
        },
        available=True,
        metadata={"submission_schema": "airalogy.human-work-submission.v1"},
    )


def resource_capability(
    resource_type: ResourceType,
    revision: ResourceTypeRevision,
) -> ResearchCapabilityDescriptor:
    return ResearchCapabilityDescriptor(
        key=f"resource:{resource_type.id}",
        version=str(revision.revision),
        kind="resource",
        name=resource_type.name,
        description=resource_type.description or "",
        source_type="resource_type_revision",
        source_id=str(resource_type.id),
        source_revision_id=str(revision.id),
        executor_types=[],
        risk="resource_dependency",
        input_schema={},
        output_schema={},
        available=True,
        metadata={
            "code": resource_type.code,
            "capabilities": revision.capabilities or {},
            "booking_policy": revision.booking_policy,
            "protocol_id": str(revision.protocol_id),
            "protocol_version": revision.protocol_version,
        },
    )


def instrument_command_capability(
    command: ResearchInstrumentCommand,
    gateway: ResearchInstrumentGateway,
    resource: Resource,
) -> ResearchCapabilityDescriptor:
    """Project one allowlisted command into a versioned execution capability."""

    available = bool(
        command.enabled
        and command.archived_at is None
        and gateway.enabled
        and gateway.revoked_at is None
        and resource.archived_at is None
        and resource.status == ResourceStatus.ACTIVE.value
        and resource.current_revision_id == command.resource_revision_id
    )
    return ResearchCapabilityDescriptor(
        key=f"instrument:{command.id}",
        version=str(command.revision),
        kind="instrument",
        name=command.name,
        description=command.description or "",
        source_type="research_instrument_command",
        source_id=str(command.id),
        source_revision_id=f"{command.id}@{command.revision}",
        executor_types=["instrument_gateway"],
        risk=command.risk,
        input_schema=command.input_schema,
        output_schema=command.output_schema,
        available=available,
        unavailable_reason=(
            ""
            if available
            else "Command, Gateway, or equipment revision is unavailable"
        ),
        metadata={
            "lab_id": str(command.lab_id),
            "command_key": command.command_key,
            "command_version": command.command_version,
            "command_revision": command.revision,
            "gateway_id": str(gateway.id),
            "gateway_name": gateway.name,
            "gateway_revision": gateway.revision,
            "resource_id": str(resource.id),
            "resource_type_id": str(resource.resource_type_id),
            "resource_name": resource.name,
            "resource_code": resource.code,
            "resource_revision_id": str(command.resource_revision_id),
            "resource_revision": command.resource_revision,
            "device_confirmation_required": command.device_confirmation_required,
            "safety_contract": getattr(command, "safety_contract", {}),
            "timeout_seconds": command.timeout_seconds,
        },
    )


async def instrument_command_capability_rows(
    db_session: AsyncSession,
    *,
    lab_id: UUID,
) -> list[tuple[ResearchInstrumentCommand, ResearchInstrumentGateway, Resource]]:
    return list(
        (
            await db_session.execute(
                select(ResearchInstrumentCommand, ResearchInstrumentGateway, Resource)
                .join(
                    ResearchInstrumentGateway,
                    ResearchInstrumentGateway.id
                    == ResearchInstrumentCommand.gateway_id,
                )
                .join(Resource, Resource.id == ResearchInstrumentCommand.resource_id)
                .where(
                    ResearchInstrumentCommand.lab_id == lab_id,
                    ResearchInstrumentCommand.enabled.is_(True),
                    ResearchInstrumentCommand.archived_at.is_(None),
                    ResearchInstrumentGateway.enabled.is_(True),
                    ResearchInstrumentGateway.revoked_at.is_(None),
                    Resource.archived_at.is_(None),
                    Resource.status == ResourceStatus.ACTIVE.value,
                    Resource.current_revision_id
                    == ResearchInstrumentCommand.resource_revision_id,
                )
                .order_by(
                    ResearchInstrumentCommand.name,
                    ResearchInstrumentCommand.command_key,
                    ResearchInstrumentCommand.id,
                )
            )
        ).all()
    )


async def research_capability_catalog(
    db_session: AsyncSession,
    *,
    project: Project,
    include_resources: bool = True,
    include_instruments: bool = False,
    include_services: bool = True,
    include_compute: bool = True,
) -> dict[str, list[ResearchCapabilityDescriptor]]:
    protocol_rows = list(
        (
            await db_session.execute(
                select(Protocol, ProtocolVersion)
                .join(
                    ProtocolVersion,
                    (ProtocolVersion.protocol_id == Protocol.id)
                    & (ProtocolVersion.version == Protocol.latest_version),
                )
                .where(
                    Protocol.project_id == project.id,
                    Protocol.deleted_at.is_(None),
                    Protocol.kind == ProtocolKind.EXPERIMENT,
                )
                .order_by(Protocol.name)
            )
        ).all()
    )
    resource_rows = []
    if include_resources:
        resource_rows = list(
            (
                await db_session.execute(
                    select(ResourceType, ResourceTypeRevision)
                    .join(
                        ResourceTypeRevision,
                        ResourceTypeRevision.id == ResourceType.current_revision_id,
                    )
                    .where(
                        ResourceType.lab_id == project.lab_id,
                        ResourceType.archived_at.is_(None),
                    )
                    .order_by(ResourceType.name)
                )
            ).all()
        )
    instrument_rows = []
    if include_instruments:
        instrument_rows = await instrument_command_capability_rows(
            db_session, lab_id=project.lab_id
        )
    service_rows = []
    if include_services:
        service_rows = await latest_service_offering_rows(
            db_session, lab_id=project.lab_id, enabled_only=True
        )
    compute_rows = []
    if include_compute:
        compute_rows = await latest_compute_environment_rows(
            db_session, lab_id=project.lab_id, enabled_only=True
        )
    return {
        "protocols": [
            protocol_capability(protocol, version)
            for protocol, version in protocol_rows
        ],
        "tools": [tool_capability(item) for item in research_tool_catalog().values()],
        "human_work": [human_work_capability()],
        "resources": [
            resource_capability(resource_type, revision)
            for resource_type, revision in resource_rows
        ],
        "instruments": [
            instrument_command_capability(command, gateway, resource)
            for command, gateway, resource in instrument_rows
        ],
        "services": [
            ResearchCapabilityDescriptor(
                **offering_snapshot(provider, offering, revision)
            )
            for provider, offering, revision in service_rows
        ],
        "compute": [
            ResearchCapabilityDescriptor(
                **compute_environment_snapshot(environment, revision)
            )
            for environment, revision in compute_rows
        ],
    }


def pinned_tool_definition(
    environment_snapshot: dict[str, Any],
    tool_key: str,
) -> ResearchToolDefinition:
    pinned = next(
        (
            item
            for item in list(environment_snapshot.get("tools") or [])
            if item.get("key") == tool_key
        ),
        None,
    )
    if pinned is None:
        raise ValueError("Research Tool is not pinned in this Research Environment")
    definition = research_tool_catalog().get(tool_key)
    if definition is None or not definition.available:
        raise ValueError("Pinned Research Tool is currently unavailable")
    if definition.version != str(pinned.get("version") or ""):
        raise ValueError("Pinned Research Tool version is unavailable")
    return definition
