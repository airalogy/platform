"""Transactional resource linking, inventory events, and output creation."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.record import Record
from app.models.resource import (
    EquipmentBooking,
    InventoryBalance,
    InventoryEvent,
    InventoryEventKind,
    InventoryReservation,
    RecordResourceLink,
    Resource,
    ResourceContainer,
    ResourceLineage,
    ResourceLot,
    ResourceRevision,
    ResourceType,
    ResourceTypeRevision,
)

from .resource_bindings import ResourceBinding
from .resource_index import build_resource_indexes
from .resource_units import UnitError, convert_quantity, normalize_ucum_unit


class InventoryError(ValueError):
    pass


def _uuid(value: object, label: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as error:
        raise InventoryError(f"{label} must be a Platform UUID") from error


async def _lock_container_balance(
    db_session: AsyncSession,
    container_id: UUID,
) -> tuple[ResourceContainer, InventoryBalance]:
    container = (
        await db_session.execute(
            select(ResourceContainer)
            .where(
                ResourceContainer.id == container_id,
                ResourceContainer.archived_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if container is None:
        raise InventoryError("inventory container was not found")
    balance = (
        await db_session.execute(
            select(InventoryBalance)
            .where(InventoryBalance.container_id == container_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if balance is None:
        balance = InventoryBalance(
            container_id=container.id,
            on_hand=Decimal("0"),
            reserved=Decimal("0"),
            unit=container.unit,
            version=0,
        )
        db_session.add(balance)
        await db_session.flush()
    return container, balance


async def apply_inventory_event(
    db_session: AsyncSession,
    *,
    lab_id: UUID,
    actor_user_id: UUID,
    container_id: UUID,
    kind: str,
    quantity: object,
    unit: str,
    idempotency_key: str,
    on_hand_direction: int = 0,
    reserved_direction: int = 0,
    record_id: UUID | None = None,
    record_version: int | None = None,
    reason: str = "",
    metadata: dict | None = None,
) -> InventoryEvent:
    existing = (
        await db_session.execute(
            select(InventoryEvent).where(
                InventoryEvent.lab_id == lab_id,
                InventoryEvent.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    container, balance = await _lock_container_balance(db_session, container_id)
    if container.lab_id != lab_id:
        raise InventoryError("container belongs to another Lab")
    try:
        converted = convert_quantity(quantity, unit, balance.unit)
    except UnitError as error:
        raise InventoryError(str(error)) from error
    if converted <= 0:
        raise InventoryError("inventory event quantity must be greater than zero")

    before_on_hand = Decimal(balance.on_hand)
    before_reserved = Decimal(balance.reserved)
    after_on_hand = before_on_hand + converted * on_hand_direction
    after_reserved = before_reserved + converted * reserved_direction
    if after_on_hand < 0:
        raise InventoryError("inventory quantity would become negative")
    if after_reserved < 0:
        raise InventoryError("reserved quantity would become negative")
    if after_reserved > after_on_hand:
        raise InventoryError("reserved quantity cannot exceed on-hand quantity")

    balance.on_hand = after_on_hand
    balance.reserved = after_reserved
    balance.version += 1
    event = InventoryEvent(
        lab_id=lab_id,
        kind=kind,
        resource_id=container.resource_id,
        lot_id=container.lot_id,
        container_id=container.id,
        quantity=converted,
        unit=balance.unit,
        on_hand_before=before_on_hand,
        on_hand_after=after_on_hand,
        reserved_before=before_reserved,
        reserved_after=after_reserved,
        record_id=record_id,
        record_version=record_version,
        actor_user_id=actor_user_id,
        reason=reason,
        idempotency_key=idempotency_key,
        event_metadata=metadata or {},
    )
    db_session.add(event)
    await db_session.flush()
    return event


async def set_inventory_on_hand(
    db_session: AsyncSession,
    *,
    lab_id: UUID,
    actor_user_id: UUID,
    container_id: UUID,
    quantity: object,
    unit: str,
    idempotency_key: str,
    reason: str = "",
) -> InventoryEvent:
    """Record a physical count whose quantity is the new on-hand balance."""
    existing = (
        await db_session.execute(
            select(InventoryEvent).where(
                InventoryEvent.lab_id == lab_id,
                InventoryEvent.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    container, balance = await _lock_container_balance(
        db_session, container_id
    )
    if container.lab_id != lab_id:
        raise InventoryError("container belongs to another Lab")
    try:
        counted = convert_quantity(quantity, unit, balance.unit)
    except UnitError as error:
        raise InventoryError(str(error)) from error
    if counted < 0:
        raise InventoryError("counted inventory quantity cannot be negative")
    before = Decimal(balance.on_hand)
    reserved = Decimal(balance.reserved)
    if counted < reserved:
        raise InventoryError(
            "counted inventory cannot be lower than reserved quantity"
        )
    balance.on_hand = counted
    balance.version += 1
    event = InventoryEvent(
        lab_id=lab_id,
        kind=InventoryEventKind.COUNT.value,
        resource_id=container.resource_id,
        lot_id=container.lot_id,
        container_id=container.id,
        quantity=abs(counted - before),
        unit=balance.unit,
        on_hand_before=before,
        on_hand_after=counted,
        reserved_before=reserved,
        reserved_after=reserved,
        actor_user_id=actor_user_id,
        reason=reason,
        idempotency_key=idempotency_key,
        event_metadata={
            "counted_quantity": str(counted),
            "counted_unit": balance.unit,
        },
    )
    db_session.add(event)
    await db_session.flush()
    return event


async def reserve_inventory(
    db_session: AsyncSession,
    *,
    lab_id: UUID,
    resource_id: UUID,
    container_id: UUID,
    quantity: object,
    unit: str,
    actor_user_id: UUID,
    idempotency_key: str,
    expires_at=None,
    record_id: UUID | None = None,
    reason: str = "",
) -> InventoryReservation:
    existing = (
        await db_session.execute(
            select(InventoryReservation).where(
                InventoryReservation.lab_id == lab_id,
                InventoryReservation.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    event = await apply_inventory_event(
        db_session,
        lab_id=lab_id,
        actor_user_id=actor_user_id,
        container_id=container_id,
        kind=InventoryEventKind.RESERVATION.value,
        quantity=quantity,
        unit=unit,
        idempotency_key=f"{idempotency_key}:event",
        reserved_direction=1,
        record_id=record_id,
        reason=reason or "Inventory reserved",
    )
    if event.resource_id != resource_id:
        raise InventoryError("inventory container belongs to another resource")
    reservation = InventoryReservation(
        lab_id=lab_id,
        resource_id=resource_id,
        container_id=container_id,
        quantity=event.quantity,
        unit=event.unit,
        expires_at=expires_at,
        record_id=record_id,
        created_by_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db_session.add(reservation)
    await db_session.flush()
    return reservation


async def release_inventory_reservation(
    db_session: AsyncSession,
    *,
    reservation: InventoryReservation,
    actor_user_id: UUID,
    idempotency_key: str,
    reason: str = "",
) -> InventoryEvent:
    reservation = (
        await db_session.execute(
            select(InventoryReservation)
            .where(InventoryReservation.id == reservation.id)
            .with_for_update()
        )
    ).scalar_one()
    if reservation.status != "active":
        existing = (
            await db_session.execute(
                select(InventoryEvent).where(
                    InventoryEvent.lab_id == reservation.lab_id,
                    InventoryEvent.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        raise InventoryError("inventory reservation is not active")
    event = await apply_inventory_event(
        db_session,
        lab_id=reservation.lab_id,
        actor_user_id=actor_user_id,
        container_id=reservation.container_id,
        kind=InventoryEventKind.RESERVATION_RELEASE.value,
        quantity=reservation.quantity,
        unit=reservation.unit,
        idempotency_key=idempotency_key,
        reserved_direction=-1,
        record_id=reservation.record_id,
        reason=reason or "Inventory reservation released",
    )
    reservation.status = "released"
    await db_session.flush()
    return event


async def release_expired_inventory_reservations(
    db_session: AsyncSession,
    *,
    limit: int = 100,
) -> int:
    """Release expired reservations with stable idempotency keys."""
    reservations = (
        await db_session.scalars(
            select(InventoryReservation)
            .where(
                InventoryReservation.status == "active",
                InventoryReservation.expires_at.is_not(None),
                InventoryReservation.expires_at <= datetime.now(UTC),
            )
            .order_by(InventoryReservation.expires_at)
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
    ).all()
    for reservation in reservations:
        await release_inventory_reservation(
            db_session,
            reservation=reservation,
            actor_user_id=reservation.created_by_user_id,
            idempotency_key=f"reservation:{reservation.id}:expired",
            reason="Inventory reservation expired",
        )
        reservation.status = "expired"
    return len(reservations)


async def transfer_inventory(
    db_session: AsyncSession,
    *,
    lab_id: UUID,
    actor_user_id: UUID,
    from_container_id: UUID,
    to_container_id: UUID,
    quantity: object,
    unit: str,
    idempotency_key: str,
    reason: str = "",
) -> InventoryEvent:
    if from_container_id == to_container_id:
        raise InventoryError("source and destination containers must differ")
    existing = (
        await db_session.execute(
            select(InventoryEvent).where(
                InventoryEvent.lab_id == lab_id,
                InventoryEvent.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    locked: dict[UUID, tuple[ResourceContainer, InventoryBalance]] = {}
    for container_id in sorted(
        (from_container_id, to_container_id), key=str
    ):
        locked[container_id] = await _lock_container_balance(
            db_session, container_id
        )
    source, source_balance = locked[from_container_id]
    destination, destination_balance = locked[to_container_id]
    if source.lab_id != lab_id or destination.lab_id != lab_id:
        raise InventoryError("container belongs to another Lab")
    if source.resource_id != destination.resource_id:
        raise InventoryError(
            "inventory can only be transferred between containers of one resource"
        )
    try:
        source_quantity = convert_quantity(quantity, unit, source_balance.unit)
        destination_quantity = convert_quantity(
            quantity, unit, destination_balance.unit
        )
    except UnitError as error:
        raise InventoryError(str(error)) from error
    if source_quantity <= 0:
        raise InventoryError("transfer quantity must be greater than zero")
    source_before = Decimal(source_balance.on_hand)
    destination_before = Decimal(destination_balance.on_hand)
    source_after = source_before - source_quantity
    if source_after < Decimal(source_balance.reserved):
        raise InventoryError("transfer would consume reserved inventory")
    destination_after = destination_before + destination_quantity
    source_balance.on_hand = source_after
    destination_balance.on_hand = destination_after
    source_balance.version += 1
    destination_balance.version += 1
    event = InventoryEvent(
        lab_id=lab_id,
        kind=InventoryEventKind.TRANSFER.value,
        resource_id=source.resource_id,
        lot_id=source.lot_id,
        container_id=source.id,
        from_container_id=source.id,
        to_container_id=destination.id,
        quantity=source_quantity,
        unit=source_balance.unit,
        on_hand_before=source_before,
        on_hand_after=source_after,
        reserved_before=source_balance.reserved,
        reserved_after=source_balance.reserved,
        actor_user_id=actor_user_id,
        reason=reason,
        idempotency_key=idempotency_key,
        event_metadata={
            "destination_unit": destination_balance.unit,
            "destination_quantity": str(destination_quantity),
            "destination_on_hand_before": str(destination_before),
            "destination_on_hand_after": str(destination_after),
        },
    )
    db_session.add(event)
    await db_session.flush()
    return event


async def _resource_for_binding(
    db_session: AsyncSession,
    *,
    lab_id: UUID,
    binding: ResourceBinding,
    actor_user_id: UUID,
    allow_output_creation: bool,
) -> Resource:
    resource_id = _uuid(binding.value["id"], f"{binding.field_path}.id")
    resource = await db_session.get(Resource, resource_id)
    if resource is not None:
        if resource.lab_id != lab_id or resource.archived_at is not None:
            raise InventoryError("resource is not available in this Lab")
        return resource
    if binding.role != "output":
        raise InventoryError(f"resource {resource_id} was not found")
    if not allow_output_creation:
        raise InventoryError(
            f"{binding.field_path} correction or migration must reference "
            "an existing output resource"
        )
    payload = binding.value.get("prepared_output")
    if not isinstance(payload, dict):
        raise InventoryError(
            f"{binding.field_path} output must be prepared by the resource resolver"
        )
    return await _create_output_resource(
        db_session,
        lab_id=lab_id,
        resource_id=resource_id,
        payload=payload,
        actor_user_id=actor_user_id,
    )


async def _create_output_resource(
    db_session: AsyncSession,
    *,
    lab_id: UUID,
    resource_id: UUID,
    payload: dict,
    actor_user_id: UUID,
) -> Resource:
    resource_type_id = _uuid(payload.get("resource_type_id"), "resource_type_id")
    resource_type = await db_session.get(ResourceType, resource_type_id)
    if (
        resource_type is None
        or resource_type.lab_id != lab_id
        or resource_type.archived_at is not None
        or resource_type.current_revision_id is None
    ):
        raise InventoryError("output resource type is not active in this Lab")
    type_revision = await db_session.get(
        ResourceTypeRevision, resource_type.current_revision_id
    )
    if type_revision is None:
        raise InventoryError("output resource type revision was not found")

    name = str(payload.get("name") or "").strip()
    code = str(payload.get("code") or "").strip()
    if not name or not code:
        raise InventoryError("output resource requires name and stable code")
    resource = Resource(
        id=resource_id,
        lab_id=lab_id,
        resource_type_id=resource_type_id,
        name=name,
        code=code,
        status="active",
        visibility=str(payload.get("visibility") or "lab"),
        created_by_user_id=actor_user_id,
    )
    db_session.add(resource)
    await db_session.flush()
    revision = ResourceRevision(
        resource_id=resource.id,
        resource_type_revision_id=type_revision.id,
        revision=1,
        data=payload.get("data") if isinstance(payload.get("data"), dict) else {},
        revision_kind="initial",
        reason="Created as Protocol output",
        created_by_user_id=actor_user_id,
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
    await db_session.flush()
    return resource


async def _ensure_output_container(
    db_session: AsyncSession,
    *,
    resource: Resource,
    binding: ResourceBinding,
) -> ResourceContainer:
    payload = binding.value.get("prepared_output") or {}
    container_payload = payload.get("container")
    if not isinstance(container_payload, dict):
        raise InventoryError(
            f"{binding.field_path} output quantity requires a prepared container"
        )
    container_id = _uuid(
        container_payload.get("id") or binding.value.get("container_id"),
        "output container id",
    )
    existing = await db_session.get(ResourceContainer, container_id)
    if existing is not None:
        if existing.resource_id != resource.id:
            raise InventoryError("output container belongs to another resource")
        return existing

    lot_id = None
    lot_payload = payload.get("lot")
    if isinstance(lot_payload, dict):
        lot_id = _uuid(lot_payload.get("id"), "output lot id")
        lot = ResourceLot(
            id=lot_id,
            resource_id=resource.id,
            code=str(lot_payload.get("code") or lot_id),
            supplier=lot_payload.get("supplier"),
            expires_at=lot_payload.get("expires_at"),
            status="active",
            data=lot_payload.get("data") or {},
        )
        db_session.add(lot)
    unit = normalize_ucum_unit(
        str(container_payload.get("unit") or binding.unit or "")
    )
    container = ResourceContainer(
        id=container_id,
        lab_id=resource.lab_id,
        resource_id=resource.id,
        lot_id=lot_id,
        location_id=container_payload.get("location_id"),
        code=str(container_payload.get("code") or container_id),
        status="active",
        unit=unit,
        data=container_payload.get("data") or {},
    )
    db_session.add(container)
    db_session.add(
        InventoryBalance(
            container_id=container.id,
            on_hand=Decimal("0"),
            reserved=Decimal("0"),
            unit=unit,
            version=0,
        )
    )
    await db_session.flush()
    return container


async def commit_record_resources(
    db_session: AsyncSession,
    *,
    lab_id: UUID,
    record: Record,
    actor_user_id: UUID,
    bindings: list[ResourceBinding],
    apply_inventory: bool = True,
) -> None:
    input_resources: list[Resource] = []
    output_resources: list[Resource] = []
    for binding in bindings:
        resource = await _resource_for_binding(
            db_session,
            lab_id=lab_id,
            binding=binding,
            actor_user_id=actor_user_id,
            allow_output_creation=apply_inventory,
        )
        container_id = (
            _uuid(binding.value["container_id"], "container_id")
            if binding.value.get("container_id")
            else None
        )
        lot_id = (
            _uuid(binding.value["lot_id"], "lot_id")
            if binding.value.get("lot_id")
            else None
        )
        booking_id = (
            _uuid(binding.value["booking_id"], "booking_id")
            if binding.value.get("booking_id")
            else None
        )

        reservation_id = (
            _uuid(binding.value["reservation_id"], "reservation_id")
            if binding.value.get("reservation_id")
            else None
        )

        if (
            apply_inventory
            and binding.role == "input"
            and binding.quantity is not None
        ):
            if container_id is None or binding.unit is None:
                raise InventoryError(
                    f"{binding.field_path} input consumption requires container and unit"
                )
            if reservation_id:
                reservation = (
                    await db_session.execute(
                        select(InventoryReservation)
                        .where(
                            InventoryReservation.id == reservation_id
                        )
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if (
                    reservation is None
                    or reservation.status != "active"
                    or reservation.lab_id != lab_id
                    or reservation.resource_id != resource.id
                    or reservation.container_id != container_id
                    or (
                        reservation.expires_at is not None
                        and reservation.expires_at <= datetime.now(UTC)
                    )
                ):
                    raise InventoryError("inventory reservation is not active")
                requested = convert_quantity(
                    binding.quantity, binding.unit, reservation.unit
                )
                if requested > reservation.quantity:
                    raise InventoryError("consumption exceeds reserved quantity")
                event = await apply_inventory_event(
                    db_session,
                    lab_id=lab_id,
                    actor_user_id=actor_user_id,
                    container_id=container_id,
                    kind=InventoryEventKind.CONSUMPTION.value,
                    quantity=binding.quantity,
                    unit=binding.unit,
                    idempotency_key=(
                        f"record:{record.id}:{record.version}:{binding.field_path}:consume"
                    ),
                    on_hand_direction=-1,
                    reserved_direction=-1,
                    record_id=record.id,
                    record_version=record.version,
                    reason="Protocol Record input consumption",
                )
                if event.resource_id != resource.id:
                    raise InventoryError(
                        f"{binding.field_path} container belongs to another resource"
                    )
                if requested == reservation.quantity:
                    reservation.status = "consumed"
                else:
                    reservation.quantity -= requested
            else:
                event = await apply_inventory_event(
                    db_session,
                    lab_id=lab_id,
                    actor_user_id=actor_user_id,
                    container_id=container_id,
                    kind=InventoryEventKind.CONSUMPTION.value,
                    quantity=binding.quantity,
                    unit=binding.unit,
                    idempotency_key=(
                        f"record:{record.id}:{record.version}:{binding.field_path}:consume"
                    ),
                    on_hand_direction=-1,
                    record_id=record.id,
                    record_version=record.version,
                    reason="Protocol Record input consumption",
                )
                if event.resource_id != resource.id:
                    raise InventoryError(
                        f"{binding.field_path} container belongs to another resource"
                    )
        if binding.role == "input":
            input_resources.append(resource)

        if binding.role == "output":
            output_resources.append(resource)
            if apply_inventory and binding.quantity is not None:
                container = await _ensure_output_container(
                    db_session, resource=resource, binding=binding
                )
                await apply_inventory_event(
                    db_session,
                    lab_id=lab_id,
                    actor_user_id=actor_user_id,
                    container_id=container.id,
                    kind=InventoryEventKind.OUTPUT.value,
                    quantity=binding.quantity,
                    unit=binding.unit or container.unit,
                    idempotency_key=(
                        f"record:{record.id}:{record.version}:{binding.field_path}:output"
                    ),
                    on_hand_direction=1,
                    record_id=record.id,
                    record_version=record.version,
                    reason="Protocol Record output",
                )
                container_id = container.id
                lot_id = container.lot_id

        if binding.role == "equipment":
            if booking_id is None and binding.booking_required:
                raise InventoryError(f"{binding.field_path} requires a booking")
            if booking_id is not None:
                booking = await db_session.get(EquipmentBooking, booking_id)
                if (
                    booking is None
                    or booking.lab_id != lab_id
                    or booking.resource_id != resource.id
                    or booking.status not in {"approved", "completed"}
                ):
                    raise InventoryError("equipment booking is not valid")

        revision_id = resource.current_revision_id
        db_session.add(
            RecordResourceLink(
                record_id=record.id,
                record_version=record.version,
                protocol_id=record.protocol_id,
                protocol_version=record.protocol_version,
                resource_id=resource.id,
                resource_revision_id=revision_id,
                lot_id=lot_id,
                container_id=container_id,
                booking_id=booking_id,
                reservation_id=reservation_id,
                field_path=binding.field_path,
                role=binding.role,
                quantity=binding.quantity,
                unit=binding.unit,
                snapshot=(
                    binding.value.get("snapshot")
                    if isinstance(binding.value.get("snapshot"), dict)
                    else {}
                ),
            )
        )

    for parent in {resource.id: resource for resource in input_resources}.values():
        for child in {
            resource.id: resource for resource in output_resources
        }.values():
            db_session.add(
                ResourceLineage(
                    parent_resource_id=parent.id,
                    child_resource_id=child.id,
                    record_id=record.id,
                    record_version=record.version,
                    relationship="derived_from",
                )
            )
    await db_session.flush()
