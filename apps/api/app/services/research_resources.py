"""Cross-cutting lifecycle helpers for Research resource commitments."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchAction
from app.models.research_execution import (
    ResearchResourceReservation,
    ResearchResourceReservationStatus,
)
from app.models.resource import BookingStatus, EquipmentBooking, InventoryReservation
from app.services.resource_inventory import release_inventory_reservation


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
