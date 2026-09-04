"""Validation helpers for immutable governed Sample lineage."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select

from app.database import DBSession
from app.models.resource import (
    Resource,
    ResourceLineage,
    ResourceLineageRelationship,
    ResourceRevision,
    ResourceTypeRevision,
)


class ResourceLineageError(ValueError):
    pass


CONTROLLED_RELATIONSHIPS = {
    item.value for item in ResourceLineageRelationship
}
SINGLE_PARENT_RELATIONSHIPS = {
    ResourceLineageRelationship.ALIQUOT_OF.value,
    ResourceLineageRelationship.SPLIT_FROM.value,
}


async def resource_has_sample_semantics(
    db_session: DBSession,
    resource: Resource,
) -> bool:
    if resource.current_revision_id is None:
        return False
    revision = await db_session.get(ResourceRevision, resource.current_revision_id)
    if revision is None:
        return False
    type_revision = await db_session.get(
        ResourceTypeRevision, revision.resource_type_revision_id
    )
    return bool(type_revision and type_revision.capabilities.get("sample"))


async def _outgoing_children(
    db_session: DBSession,
    parent_ids: Iterable[UUID],
) -> set[UUID]:
    values = tuple(parent_ids)
    if not values:
        return set()
    return set(
        (
            await db_session.scalars(
                select(ResourceLineage.child_resource_id).where(
                    ResourceLineage.parent_resource_id.in_(values)
                )
            )
        ).all()
    )


async def ensure_lineage_is_acyclic(
    db_session: DBSession,
    *,
    parent_resource_id: UUID,
    child_resource_id: UUID,
) -> None:
    """Reject an edge when the proposed child already reaches its parent."""
    if parent_resource_id == child_resource_id:
        raise ResourceLineageError("A Sample cannot be its own lineage parent")

    visited = {child_resource_id}
    frontier = {child_resource_id}
    while frontier:
        children = await _outgoing_children(db_session, frontier)
        if parent_resource_id in children:
            raise ResourceLineageError("Sample lineage must remain acyclic")
        frontier = children - visited
        visited.update(frontier)


async def validate_sample_lineage(
    db_session: DBSession,
    *,
    parent: Resource,
    child: Resource,
    relationship: str,
) -> None:
    if relationship not in CONTROLLED_RELATIONSHIPS:
        raise ResourceLineageError("Unsupported Sample lineage relationship")
    if parent.lab_id != child.lab_id:
        raise ResourceLineageError("Sample lineage cannot cross Lab boundaries")
    if not await resource_has_sample_semantics(db_session, parent):
        raise ResourceLineageError("The parent Resource is not a Sample")
    if not await resource_has_sample_semantics(db_session, child):
        raise ResourceLineageError("The child Resource is not a Sample")

    await ensure_lineage_is_acyclic(
        db_session,
        parent_resource_id=parent.id,
        child_resource_id=child.id,
    )
    if relationship in SINGLE_PARENT_RELATIONSHIPS:
        existing_parent = await db_session.scalar(
            select(ResourceLineage.id).where(
                ResourceLineage.child_resource_id == child.id,
                ResourceLineage.relationship.in_(SINGLE_PARENT_RELATIONSHIPS),
            )
        )
        if existing_parent is not None:
            raise ResourceLineageError(
                "An aliquot or split Sample can have only one direct origin"
            )
