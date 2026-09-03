"""Derived Capability Registry and Research Environment snapshots.

The registry deliberately does not persist a second copy of scientific methods.
Protocol versions, allowlisted tools, and resource definitions remain the sources
of truth; this module only projects them into one discoverable contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.protocol import Protocol, ProtocolKind
from app.models.protocol_version import ProtocolVersion
from app.models.resource import ResourceType, ResourceTypeRevision
from app.services.research_services import (
    latest_service_offering_rows,
    offering_snapshot,
)
from app.services.research_tools import ResearchToolDefinition, research_tool_catalog

CapabilityKind = Literal["protocol", "tool", "resource", "service"]


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


async def research_capability_catalog(
    db_session: AsyncSession,
    *,
    project: Project,
    include_resources: bool = True,
    include_services: bool = True,
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
    service_rows = []
    if include_services:
        service_rows = await latest_service_offering_rows(
            db_session, lab_id=project.lab_id, enabled_only=True
        )
    return {
        "protocols": [
            protocol_capability(protocol, version)
            for protocol, version in protocol_rows
        ],
        "tools": [tool_capability(item) for item in research_tool_catalog().values()],
        "resources": [
            resource_capability(resource_type, revision)
            for resource_type, revision in resource_rows
        ],
        "services": [
            ResearchCapabilityDescriptor(**offering_snapshot(provider, offering, revision))
            for provider, offering, revision in service_rows
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
