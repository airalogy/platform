"""Resolution and lifecycle helpers for Research resource commitments."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import (
    ResearchAction,
    ResearchActionStatus,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
)
from app.models.research_execution import (
    ResearchResourceReservation,
    ResearchResourceReservationStatus,
)
from app.models.resource import (
    BookingStatus,
    EquipmentBooking,
    InventoryBalance,
    InventoryReservation,
    Resource,
    ResourceContainer,
    ResourceLot,
    ResourceRevision,
    ResourceStatus,
    ResourceTypeRevision,
    ResourceVisibility,
)
from app.services.access_control import resolve_resource_access
from app.services.resource_inventory import (
    InventoryError,
    release_inventory_reservation,
    reserve_inventory,
)
from app.services.resource_units import UnitError, convert_quantity


class ResearchResourceError(ValueError):
    """A resource proposal cannot be resolved or safely activated."""


def _requirement(run: ResearchRun, resource_type_key: str) -> dict[str, Any]:
    requirement = next(
        (
            item
            for item in list((run.environment_snapshot or {}).get("resources") or [])
            if item.get("key") == resource_type_key
        ),
        None,
    )
    if requirement is None:
        raise ResearchResourceError(
            "Aira proposed a Resource type outside the Research Environment"
        )
    return requirement


def _restricted_resource_allowed(resource: Resource, access) -> bool:
    if resource.visibility == ResourceVisibility.LAB.value:
        return True
    return any(
        source.scope_type in {"resource", "resource_type"}
        or source.role_key in {"lab_owner", "lab_admin"}
        for source in access.sources
    )


async def _can_operate_resource(
    db_session: AsyncSession,
    *,
    user_id: UUID,
    task: ResearchTask,
    resource: Resource,
    capability: str,
) -> bool:
    access = await resolve_resource_access(
        db_session,
        user_id,
        task.lab_id,
        resource_type_id=resource.resource_type_id,
        resource_id=resource.id,
    )
    return access.allows(capability) and _restricted_resource_allowed(resource, access)


async def resolve_aira_resource_request(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    user_id: UUID,
    request: dict[str, Any],
) -> dict[str, Any]:
    """Resolve an abstract AI request to one deterministic, permissioned candidate."""

    requirement = _requirement(run, str(request["resource_type_key"]))
    capabilities = dict((requirement.get("metadata") or {}).get("capabilities") or {})
    kind = str(request["kind"])
    required_capability = "inventory.operate" if kind == "inventory" else "equipment.book"
    if kind == "inventory" and not capabilities.get("inventory"):
        raise ResearchResourceError("Pinned Resource type does not support inventory")
    if kind == "equipment" and not capabilities.get("booking"):
        raise ResearchResourceError("Pinned Resource type is not bookable equipment")
    try:
        resource_type_id = UUID(str(requirement["source_id"]))
        type_revision_id = UUID(str(requirement["source_revision_id"]))
    except (KeyError, ValueError) as error:
        raise ResearchResourceError("Pinned Resource requirement is invalid") from error

    resources = list(
        (
            await db_session.scalars(
                select(Resource)
                .where(
                    Resource.lab_id == task.lab_id,
                    Resource.resource_type_id == resource_type_id,
                    Resource.status == ResourceStatus.ACTIVE.value,
                    Resource.archived_at.is_(None),
                )
                .order_by(Resource.code, Resource.id)
            )
        ).all()
    )
    for resource in resources:
        if resource.current_revision_id is None:
            continue
        revision = await db_session.get(ResourceRevision, resource.current_revision_id)
        if revision is None or revision.resource_type_revision_id != type_revision_id:
            continue
        if not await _can_operate_resource(
            db_session,
            user_id=user_id,
            task=task,
            resource=resource,
            capability=required_capability,
        ):
            continue
        common = {
            "kind": kind,
            "resource_id": str(resource.id),
            "resource_name": resource.name,
            "resource_code": resource.code,
            "resource_revision_id": str(revision.id),
            "resource_revision": revision.revision,
            "resource_type_requirement": {
                "key": requirement["key"],
                "version": requirement["version"],
                "source_id": requirement["source_id"],
                "source_revision_id": requirement["source_revision_id"],
            },
            "purpose": str(request["purpose"]),
        }
        if kind == "inventory":
            rows = list(
                (
                    await db_session.execute(
                        select(ResourceContainer, InventoryBalance, ResourceLot)
                        .join(
                            InventoryBalance,
                            InventoryBalance.container_id == ResourceContainer.id,
                        )
                        .outerjoin(ResourceLot, ResourceLot.id == ResourceContainer.lot_id)
                        .where(
                            ResourceContainer.resource_id == resource.id,
                            ResourceContainer.status == "active",
                            ResourceContainer.archived_at.is_(None),
                            or_(
                                ResourceContainer.lot_id.is_(None),
                                and_(
                                    ResourceLot.status == "active",
                                    or_(
                                        ResourceLot.expires_at.is_(None),
                                        ResourceLot.expires_at > datetime.now(UTC),
                                    ),
                                ),
                            ),
                        )
                        .order_by(
                            ResourceLot.expires_at.asc().nulls_last(),
                            ResourceContainer.code,
                            ResourceContainer.id,
                        )
                    )
                ).all()
            )
            for container, balance, lot in rows:
                try:
                    reserved_quantity = convert_quantity(
                        request["quantity"], request["unit"], balance.unit
                    )
                except UnitError:
                    continue
                if reserved_quantity > balance.available:
                    continue
                return {
                    **common,
                    "inventory": {
                        "container_id": str(container.id),
                        "lot_id": str(lot.id) if lot is not None else None,
                        "lot_expires_at": (
                            lot.expires_at.isoformat()
                            if lot is not None and lot.expires_at is not None
                            else None
                        ),
                        "quantity": str(request["quantity"]),
                        "unit": str(request["unit"]),
                        "balance_version": balance.version,
                        "available": str(balance.available),
                        "balance_unit": balance.unit,
                        "reserved_quantity": str(reserved_quantity),
                    },
                }
        else:
            starts_at: datetime = request["starts_at"]
            ends_at: datetime = request["ends_at"]
            conflict = await db_session.scalar(
                select(EquipmentBooking.id)
                .where(
                    EquipmentBooking.resource_id == resource.id,
                    EquipmentBooking.status.in_(
                        [BookingStatus.PENDING.value, BookingStatus.APPROVED.value]
                    ),
                    EquipmentBooking.starts_at < ends_at,
                    EquipmentBooking.ends_at > starts_at,
                )
                .limit(1)
            )
            if conflict is not None:
                continue
            return {
                **common,
                "equipment": {
                    "starts_at": starts_at.isoformat(),
                    "ends_at": ends_at.isoformat(),
                    "booking_policy": (requirement.get("metadata") or {}).get(
                        "booking_policy", "none"
                    ),
                },
            }
    raise ResearchResourceError(
        "No accessible Resource currently satisfies the Aira request"
    )


async def activate_aira_resource_action(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    action: ResearchAction,
    actor_user_id: UUID,
) -> tuple[str, dict[str, Any]]:
    """Revalidate and commit an approved AI Resource Reservation Action."""

    reservation = await ResearchResourceReservation.find_by(
        db_session, [ResearchResourceReservation.action_id == action.id]
    )
    if reservation is None:
        raise ResearchResourceError("Research Resource Reservation is missing")
    if reservation.status != ResearchResourceReservationStatus.PROPOSED.value:
        raise ResearchResourceError("Research Resource Reservation is not proposed")
    resolved = dict((action.input_data or {}).get("resolved") or {})
    requirement = _requirement(
        run, str((resolved.get("resource_type_requirement") or {}).get("key") or "")
    )
    if str(requirement.get("source_revision_id")) != str(
        (resolved.get("resource_type_requirement") or {}).get("source_revision_id")
    ):
        raise ResearchResourceError("Pinned Resource requirement changed")
    resource = await db_session.get(Resource, reservation.resource_id)
    if (
        resource is None
        or resource.lab_id != task.lab_id
        or resource.status != ResourceStatus.ACTIVE.value
        or resource.archived_at is not None
        or resource.current_revision_id != reservation.resource_revision_id
    ):
        raise ResearchResourceError("Resolved Resource is no longer available")
    revision = await db_session.get(ResourceRevision, reservation.resource_revision_id)
    if (
        revision is None
        or revision.revision != reservation.resource_revision
        or str(revision.id) != str(resolved.get("resource_revision_id"))
        or str(revision.resource_type_revision_id)
        != str(requirement.get("source_revision_id"))
    ):
        raise ResearchResourceError("Resolved Resource revision changed")
    type_revision = await db_session.get(
        ResourceTypeRevision, revision.resource_type_revision_id
    )
    if type_revision is None:
        raise ResearchResourceError("Resource type revision is unavailable")
    required_capability = (
        "inventory.operate" if reservation.kind == "inventory" else "equipment.book"
    )
    if not await _can_operate_resource(
        db_session,
        user_id=actor_user_id,
        task=task,
        resource=resource,
        capability=required_capability,
    ):
        raise ResearchResourceError("Resource execution access is no longer available")

    if reservation.kind == "inventory":
        inventory_data = dict(resolved.get("inventory") or {})
        balance = (
            await db_session.execute(
                select(InventoryBalance)
                .where(InventoryBalance.container_id == reservation.container_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        container = await db_session.get(ResourceContainer, reservation.container_id)
        if (
            balance is None
            or container is None
            or container.resource_id != resource.id
            or container.status != "active"
            or container.archived_at is not None
        ):
            raise ResearchResourceError("Resolved inventory container is unavailable")
        if getattr(container, "lot_id", None) is not None:
            lot = await db_session.get(ResourceLot, container.lot_id)
            if (
                lot is None
                or lot.status != "active"
                or (lot.expires_at is not None and lot.expires_at <= datetime.now(UTC))
                or str(lot.id) != str(inventory_data.get("lot_id"))
            ):
                raise ResearchResourceError("Resolved inventory lot is unavailable")
        if balance.version != int(inventory_data.get("balance_version", -1)):
            raise ResearchResourceError(
                "Inventory changed after Aira proposed the reservation"
            )
        try:
            requested = convert_quantity(
                reservation.quantity,
                reservation.unit or "",
                balance.unit,
            )
        except UnitError as error:
            raise ResearchResourceError(str(error)) from error
        if requested > balance.available:
            raise ResearchResourceError("Insufficient available inventory")
        try:
            inventory = await reserve_inventory(
                db_session,
                lab_id=task.lab_id,
                resource_id=resource.id,
                container_id=container.id,
                quantity=reservation.quantity,
                unit=reservation.unit or "",
                actor_user_id=actor_user_id,
                idempotency_key=f"research-action:{action.id}:inventory",
                reason=reservation.purpose,
            )
        except InventoryError as error:
            raise ResearchResourceError(str(error)) from error
        reservation.inventory_reservation_id = inventory.id
        reservation.status = ResearchResourceReservationStatus.ACTIVE.value
        action.status = ResearchActionStatus.COMPLETED.value
        action.output_data = {
            "inventory_reservation_id": str(inventory.id),
            "status": inventory.status,
            "quantity": str(inventory.quantity),
            "unit": inventory.unit,
        }
        event_kind = "resource.inventory_reserved"
    else:
        equipment_data = dict(resolved.get("equipment") or {})
        starts_at = datetime.fromisoformat(str(equipment_data["starts_at"]))
        ends_at = datetime.fromisoformat(str(equipment_data["ends_at"]))
        conflict = await db_session.scalar(
            select(EquipmentBooking.id)
            .where(
                EquipmentBooking.resource_id == resource.id,
                EquipmentBooking.status.in_(
                    [BookingStatus.PENDING.value, BookingStatus.APPROVED.value]
                ),
                EquipmentBooking.starts_at < ends_at,
                EquipmentBooking.ends_at > starts_at,
            )
            .limit(1)
        )
        if conflict is not None:
            raise ResearchResourceError(
                "Equipment became unavailable after Aira proposed the booking"
            )
        if type_revision.booking_policy != equipment_data.get("booking_policy"):
            raise ResearchResourceError("Equipment booking policy changed")
        booking_status = (
            BookingStatus.APPROVED.value
            if type_revision.booking_policy in {"none", "auto"}
            else BookingStatus.PENDING.value
        )
        booking = EquipmentBooking(
            lab_id=task.lab_id,
            resource_id=resource.id,
            user_id=actor_user_id,
            starts_at=starts_at,
            ends_at=ends_at,
            status=booking_status,
            approval_policy=type_revision.booking_policy,
            purpose=reservation.purpose,
            idempotency_key=f"research-action:{action.id}:equipment",
        )
        db_session.add(booking)
        await db_session.flush()
        reservation.equipment_booking_id = booking.id
        reservation.status = (
            ResearchResourceReservationStatus.APPROVED.value
            if booking_status == BookingStatus.APPROVED.value
            else ResearchResourceReservationStatus.PENDING_APPROVAL.value
        )
        action.status = (
            ResearchActionStatus.COMPLETED.value
            if booking_status == BookingStatus.APPROVED.value
            else ResearchActionStatus.WAITING.value
        )
        action.output_data = {
            "equipment_booking_id": str(booking.id),
            "status": booking.status,
            "approval_policy": type_revision.booking_policy,
        }
        event_kind = "resource.equipment_booking_requested"

    reservation.revision += 1
    action.revision += 1
    if action.status == ResearchActionStatus.COMPLETED.value:
        action.completed_at = datetime.now(UTC)
        run.status = ResearchRunStatus.RUNNING.value
        from app.services.research_runtime import append_aira_result

        append_aira_result(
            run,
            "resource_results",
            {
                "action_id": str(action.id),
                "kind": reservation.kind,
                "resource_id": str(resource.id),
                "status": reservation.status,
                "result": action.output_data,
                "completed_at": action.completed_at.isoformat(),
            },
        )
    else:
        run.status = ResearchRunStatus.WAITING_FOR_EVENT.value
    return event_kind, {
        "resource_id": str(resource.id),
        "reservation_id": str(reservation.id),
        "status": reservation.status,
    }


async def release_research_run_reservations(
    db_session: AsyncSession,
    *,
    run_id: UUID,
    actor_user_id: UUID,
    reason: str,
) -> list[UUID]:
    """Release still-active commitments when a Run reaches a terminal boundary."""

    rows = list(
        (
            await db_session.execute(
                select(ResearchResourceReservation, ResearchAction)
                .join(
                    ResearchAction,
                    ResearchAction.id == ResearchResourceReservation.action_id,
                )
                .where(ResearchAction.run_id == run_id)
                .with_for_update()
            )
        ).all()
    )
    released: list[UUID] = []
    for reservation, action in rows:
        if (
            reservation.kind == "inventory"
            and reservation.status == ResearchResourceReservationStatus.ACTIVE.value
            and reservation.inventory_reservation_id is not None
        ):
            inventory = await db_session.get(
                InventoryReservation, reservation.inventory_reservation_id
            )
            if inventory is not None and inventory.status == "active":
                await release_inventory_reservation(
                    db_session,
                    reservation=inventory,
                    actor_user_id=actor_user_id,
                    idempotency_key=f"research-resource:{reservation.id}:terminal-release",
                    reason=reason,
                )
            reservation.status = ResearchResourceReservationStatus.RELEASED.value
        elif (
            reservation.kind == "equipment"
            and reservation.status
            in {
                ResearchResourceReservationStatus.PENDING_APPROVAL.value,
                ResearchResourceReservationStatus.APPROVED.value,
            }
            and reservation.equipment_booking_id is not None
        ):
            booking = await db_session.get(
                EquipmentBooking, reservation.equipment_booking_id
            )
            if booking is not None and booking.status in {
                BookingStatus.PENDING.value,
                BookingStatus.APPROVED.value,
            }:
                booking.status = BookingStatus.CANCELLED.value
            reservation.status = ResearchResourceReservationStatus.CANCELLED.value
        else:
            continue
        reservation.revision += 1
        action.output_data = {
            **(action.output_data or {}),
            "status": reservation.status,
            "terminal_release_reason": reason,
        }
        action.revision += 1
        released.append(reservation.id)
    return released
