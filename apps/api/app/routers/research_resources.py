"""Governed inventory and equipment reservations for Research Runs."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import config
from app.database import DBSession
from app.models.lab import Lab
from app.models.project import Project
from app.models.research import (
    ResearchAction,
    ResearchActionKind,
    ResearchActionStatus,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskStatus,
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
    ResourceRevision,
    ResourceStatus,
    ResourceTypeRevision,
    ResourceVisibility,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.access_control import resolve_resource_access
from app.services.research_budget import reached_operational_limit
from app.services.research_runtime import (
    append_aira_result,
    canonical_digest,
    create_plan_version,
    emit_research_event,
    enqueue_research_advance,
    require_research_capability,
    utcnow,
)
from app.services.resource_inventory import (
    InventoryError,
    release_inventory_reservation,
    reserve_inventory,
)
from app.services.resource_units import UnitError, convert_quantity, normalize_ucum_unit

router = APIRouter(tags=["research-resources"])


class ResourceActionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["inventory", "equipment"]
    resource_id: UUID
    container_id: UUID | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    expires_at: datetime | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    purpose: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def validate_kind(self):
        self.purpose = self.purpose.strip()
        self.idempotency_key = self.idempotency_key.strip()
        if self.kind == "inventory":
            if self.container_id is None or self.quantity is None or not self.unit:
                raise ValueError(
                    "Inventory reservations require a container, quantity, and unit"
                )
            if self.starts_at is not None or self.ends_at is not None:
                raise ValueError("Inventory reservations cannot include a booking window")
            try:
                self.unit = normalize_ucum_unit(self.unit)
            except UnitError as error:
                raise ValueError(str(error)) from error
        else:
            if self.starts_at is None or self.ends_at is None:
                raise ValueError("Equipment reservations require a booking window")
            if self.container_id is not None or self.quantity is not None or self.unit:
                raise ValueError("Equipment reservations cannot include inventory fields")
            if self.starts_at.tzinfo is None:
                self.starts_at = self.starts_at.replace(tzinfo=UTC)
            if self.ends_at.tzinfo is None:
                self.ends_at = self.ends_at.replace(tzinfo=UTC)
            if self.ends_at <= self.starts_at:
                raise ValueError("Equipment booking end must be later than start")
            if self.ends_at <= utcnow():
                raise ValueError("Equipment booking must end in the future")
            if self.expires_at is not None:
                raise ValueError("Equipment reservations cannot include expires_at")
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None:
                self.expires_at = self.expires_at.replace(tzinfo=UTC)
            if self.expires_at <= utcnow():
                raise ValueError("Inventory reservation expiry must be in the future")
        return self


class ResourceActionCreate(ResourceActionDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ResourceReleaseDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def normalize(self):
        self.reason = self.reason.strip()
        return self


class ResourceRelease(ResourceReleaseDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


async def _project(db_session: DBSession, project_id: UUID) -> Project:
    project = await Project.find_by(
        db_session, [Project.id == project_id, Project.deleted_at.is_(None)]
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _active_task_context(
    db_session: DBSession,
    current_user: User,
    task_id: UUID,
) -> tuple[ResearchTask, Project, Lab, ResearchRun]:
    task = await db_session.get(ResearchTask, task_id)
    if task is None or task.archived_at is not None:
        raise HTTPException(status_code=404, detail="Research Task not found")
    project = await _project(db_session, task.project_id)
    await require_research_capability(
        db_session, user=current_user, project=project, capability="research.run"
    )
    if task.status != ResearchTaskStatus.ACTIVE.value:
        raise HTTPException(status_code=409, detail="Research Task must be active")
    lab = await db_session.get(Lab, task.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    run = (
        await db_session.scalars(
            select(ResearchRun)
            .where(ResearchRun.task_id == task.id)
            .order_by(ResearchRun.run_number.desc())
            .limit(1)
        )
    ).first()
    if run is None or run.status in {
        ResearchRunStatus.COMPLETED.value,
        ResearchRunStatus.FAILED.value,
        ResearchRunStatus.CANCELLED.value,
    }:
        raise HTTPException(status_code=409, detail="Active Research Run not found")
    operational_limit = await reached_operational_limit(db_session, task=task)
    if operational_limit is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Research Task {operational_limit[0]} limit has been reached",
        )
    return task, project, lab, run


def _pinned_requirement(
    run: ResearchRun, resource_type_id: UUID
) -> dict[str, Any]:
    requirement = next(
        (
            item
            for item in list((run.environment_snapshot or {}).get("resources") or [])
            if item.get("source_id") == str(resource_type_id)
        ),
        None,
    )
    if requirement is None:
        raise HTTPException(
            status_code=422,
            detail="Resource type is not pinned in this Research Environment",
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


async def _resource_context(
    db_session: DBSession,
    *,
    user: User,
    task: ResearchTask,
    run: ResearchRun,
    params: ResourceActionDraft,
) -> dict[str, Any]:
    resource = await db_session.get(Resource, params.resource_id)
    if (
        resource is None
        or resource.lab_id != task.lab_id
        or resource.archived_at is not None
    ):
        raise HTTPException(status_code=404, detail="Resource not found")
    if resource.status != ResourceStatus.ACTIVE.value:
        raise HTTPException(status_code=409, detail="Resource is not active")
    requirement = _pinned_requirement(run, resource.resource_type_id)
    if resource.current_revision_id is None:
        raise HTTPException(status_code=409, detail="Resource has no current revision")
    resource_revision = await db_session.get(
        ResourceRevision, resource.current_revision_id
    )
    if resource_revision is None:
        raise HTTPException(status_code=409, detail="Resource revision is unavailable")
    if str(resource_revision.resource_type_revision_id) != str(
        requirement.get("source_revision_id")
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Resource schema no longer matches the pinned Research Environment; "
                "create a new Run with a current environment"
            ),
        )
    type_revision = await db_session.get(
        ResourceTypeRevision, resource_revision.resource_type_revision_id
    )
    if type_revision is None:
        raise HTTPException(status_code=409, detail="Resource type revision is unavailable")
    required_capability = (
        "inventory.operate" if params.kind == "inventory" else "equipment.book"
    )
    access = await resolve_resource_access(
        db_session,
        user.id,
        task.lab_id,
        resource_type_id=resource.resource_type_id,
        resource_id=resource.id,
    )
    if not access.allows(required_capability) or not _restricted_resource_allowed(
        resource, access
    ):
        raise HTTPException(status_code=403, detail="Resource reservation access denied")

    result: dict[str, Any] = {
        "resource": resource,
        "resource_revision": resource_revision,
        "type_revision": type_revision,
        "requirement": requirement,
        "access": access,
    }
    if params.kind == "inventory":
        if not (type_revision.capabilities or {}).get("inventory"):
            raise HTTPException(
                status_code=422, detail="Resource type does not support inventory"
            )
        container = await db_session.get(ResourceContainer, params.container_id)
        if (
            container is None
            or container.resource_id != resource.id
            or container.lab_id != task.lab_id
            or container.archived_at is not None
            or container.status != "active"
        ):
            raise HTTPException(status_code=422, detail="Inventory container is unavailable")
        balance = await db_session.get(InventoryBalance, container.id)
        if balance is None:
            raise HTTPException(status_code=409, detail="Inventory balance is unavailable")
        try:
            requested_in_balance_unit = convert_quantity(
                params.quantity, params.unit or "", balance.unit
            )
        except UnitError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if requested_in_balance_unit > balance.available:
            raise HTTPException(status_code=409, detail="Insufficient available inventory")
        result.update(
            container=container,
            balance=balance,
            requested_in_balance_unit=requested_in_balance_unit,
        )
    else:
        if not (type_revision.capabilities or {}).get("booking"):
            raise HTTPException(
                status_code=422, detail="Resource type is not bookable equipment"
            )
        conflicts = list(
            (
                await db_session.scalars(
                    select(EquipmentBooking)
                    .where(
                        EquipmentBooking.resource_id == resource.id,
                        EquipmentBooking.status.in_(
                            [
                                BookingStatus.PENDING.value,
                                BookingStatus.APPROVED.value,
                            ]
                        ),
                        EquipmentBooking.starts_at < params.ends_at,
                        EquipmentBooking.ends_at > params.starts_at,
                    )
                    .order_by(EquipmentBooking.starts_at)
                )
            ).all()
        )
        if conflicts:
            raise HTTPException(
                status_code=409, detail="Equipment is already booked in that time range"
            )
        result["conflicts"] = conflicts
    return result


def _resource_command(
    *,
    task: ResearchTask,
    run: ResearchRun,
    params: ResourceActionDraft,
    context: dict[str, Any],
) -> dict[str, Any]:
    resource: Resource = context["resource"]
    revision: ResourceRevision = context["resource_revision"]
    command: dict[str, Any] = {
        "task_id": str(task.id),
        "task_revision": task.revision,
        "run_id": str(run.id),
        "run_plan_version": run.plan_version,
        "kind": params.kind,
        "resource_id": str(resource.id),
        "resource_revision_id": str(revision.id),
        "resource_revision": revision.revision,
        "resource_type_requirement": {
            "key": context["requirement"]["key"],
            "version": context["requirement"]["version"],
            "source_revision_id": context["requirement"]["source_revision_id"],
        },
        "purpose": params.purpose,
        "idempotency_key": params.idempotency_key,
    }
    if params.kind == "inventory":
        balance: InventoryBalance = context["balance"]
        command["inventory"] = {
            "container_id": str(params.container_id),
            "quantity": str(params.quantity),
            "unit": params.unit,
            "expires_at": params.expires_at.isoformat() if params.expires_at else None,
            "balance_version": balance.version,
            "available": str(balance.available),
            "balance_unit": balance.unit,
            "reserved_quantity": str(context["requested_in_balance_unit"]),
        }
    else:
        command["equipment"] = {
            "starts_at": params.starts_at.isoformat(),
            "ends_at": params.ends_at.isoformat(),
            "booking_policy": context["type_revision"].booking_policy,
            "conflicting_booking_ids": [],
        }
    return command


def _destination(
    *, task: ResearchTask, project: Project, lab: Lab, run: ResearchRun
) -> dict[str, Any]:
    return {
        "lab": {"id": str(lab.id), "uid": lab.uid, "name": lab.name},
        "project": {"id": str(project.id), "uid": project.uid, "name": project.name},
        "task": {"id": str(task.id), "title": task.title},
        "run": {"id": str(run.id), "number": run.run_number},
    }


def _reservation_payload(
    action: ResearchAction,
    reservation: ResearchResourceReservation,
    *,
    resource: Resource | None = None,
) -> dict[str, Any]:
    return {
        **action.as_dict(),
        "resource_reservation": reservation.as_dict(),
        "resource": (
            {
                "id": str(resource.id),
                "name": resource.name,
                "code": resource.code,
                "resource_type_id": str(resource.resource_type_id),
            }
            if resource is not None
            else None
        ),
    }


async def _next_sequence(db_session: DBSession, run_id: UUID) -> int:
    return (
        await db_session.scalar(
            select(func.max(ResearchAction.sequence)).where(
                ResearchAction.run_id == run_id
            )
        )
        or 0
    ) + 1


@router.post("/research-tasks/{task_id}/resource-actions/preview")
async def preview_resource_action(
    task_id: UUID,
    params: ResourceActionDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab, run = await _active_task_context(
        db_session, current_user, task_id
    )
    context = await _resource_context(
        db_session, user=current_user, task=task, run=run, params=params
    )
    command = _resource_command(task=task, run=run, params=params, context=context)
    resource: Resource = context["resource"]
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": _destination(task=task, project=project, lab=lab, run=run),
        "resource": {
            "id": str(resource.id),
            "name": resource.name,
            "code": resource.code,
            "revision": context["resource_revision"].revision,
        },
        "effects": (
            [
                "Create a typed Resource Reservation Action",
                "Reserve the confirmed quantity in the selected inventory container",
                "Keep consumption in the existing Record-linked inventory ledger",
            ]
            if params.kind == "inventory"
            else [
                "Create a typed Resource Reservation Action",
                "Book the selected equipment time through the Lab booking policy",
                "Wait for resource-custodian approval when the policy requires it",
            ]
        ),
    }


@router.post("/research-tasks/{task_id}/resource-actions")
async def create_resource_action(
    task_id: UUID,
    params: ResourceActionCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, _project, lab, run = await _active_task_context(
        db_session, current_user, task_id
    )
    existing = await ResearchAction.find_by(
        db_session,
        [
            ResearchAction.run_id == run.id,
            ResearchAction.idempotency_key == params.idempotency_key,
        ],
    )
    if existing is not None:
        if (
            existing.kind != ResearchActionKind.RESOURCE_RESERVATION.value
            or existing.preview_digest != params.preview_digest
        ):
            raise HTTPException(
                status_code=409, detail="Action idempotency key is already in use"
            )
        typed = await ResearchResourceReservation.find_by(
            db_session, [ResearchResourceReservation.action_id == existing.id]
        )
        if typed is None:
            raise HTTPException(status_code=409, detail="Resource Action is incomplete")
        resource = await db_session.get(Resource, typed.resource_id)
        return _reservation_payload(existing, typed, resource=resource)

    context = await _resource_context(
        db_session, user=current_user, task=task, run=run, params=params
    )
    command = _resource_command(task=task, run=run, params=params, context=context)
    digest = canonical_digest(command)
    if digest != params.preview_digest:
        raise HTTPException(status_code=409, detail="Resource Action preview has changed")
    resource: Resource = context["resource"]
    revision: ResourceRevision = context["resource_revision"]
    await create_plan_version(
        db_session,
        task=task,
        run=run,
        kind="manual",
        plan={"action": command, "previous_plan_version": run.plan_version},
        summary=f"Reserve {resource.name}",
    )
    action = ResearchAction(
        run_id=run.id,
        sequence=await _next_sequence(db_session, run.id),
        plan_version=run.plan_version,
        kind=ResearchActionKind.RESOURCE_RESERVATION.value,
        status=ResearchActionStatus.PROPOSED.value,
        title=f"Reserve {resource.name}",
        description=params.purpose,
        executor_type="platform_resource_manager",
        input_data=command,
        requirements={
            "resource_type": context["requirement"],
            "resource_revision_id": str(revision.id),
            "risk": "resource_commitment",
        },
        policy_decision="allow",
        preview_digest=digest,
        idempotency_key=params.idempotency_key,
    )
    db_session.add(action)
    await db_session.flush()
    typed = ResearchResourceReservation(
        action_id=action.id,
        kind=params.kind,
        resource_id=resource.id,
        resource_revision_id=revision.id,
        resource_revision=revision.revision,
        container_id=params.container_id,
        quantity=params.quantity,
        unit=params.unit,
        starts_at=params.starts_at,
        ends_at=params.ends_at,
        purpose=params.purpose,
    )
    db_session.add(typed)
    await db_session.flush()
    try:
        if params.kind == "inventory":
            inventory = await reserve_inventory(
                db_session,
                lab_id=lab.id,
                resource_id=resource.id,
                container_id=params.container_id,
                quantity=params.quantity,
                unit=params.unit or "",
                actor_user_id=current_user.id,
                idempotency_key=f"research-action:{action.id}:inventory",
                expires_at=params.expires_at,
                reason=params.purpose,
            )
            typed.inventory_reservation_id = inventory.id
            typed.status = ResearchResourceReservationStatus.ACTIVE.value
            action.status = ResearchActionStatus.COMPLETED.value
            action.output_data = {
                "inventory_reservation_id": str(inventory.id),
                "status": inventory.status,
                "quantity": str(inventory.quantity),
                "unit": inventory.unit,
            }
            action.completed_at = utcnow()
            event_kind = "resource.inventory_reserved"
        else:
            policy = context["type_revision"].booking_policy
            booking_status = (
                BookingStatus.APPROVED.value
                if policy in {"none", "auto"}
                else BookingStatus.PENDING.value
            )
            booking = EquipmentBooking(
                lab_id=lab.id,
                resource_id=resource.id,
                user_id=current_user.id,
                starts_at=params.starts_at,
                ends_at=params.ends_at,
                status=booking_status,
                approval_policy=policy,
                purpose=params.purpose,
                idempotency_key=f"research-action:{action.id}:equipment",
            )
            db_session.add(booking)
            await db_session.flush()
            typed.equipment_booking_id = booking.id
            typed.status = (
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
                "approval_policy": policy,
            }
            if action.status == ResearchActionStatus.COMPLETED.value:
                action.completed_at = utcnow()
            event_kind = "resource.equipment_booking_requested"
    except (InventoryError, IntegrityError) as error:
        await db_session.rollback()
        detail = (
            str(error)
            if isinstance(error, InventoryError)
            else "Equipment is already booked in that time range"
        )
        raise HTTPException(status_code=409, detail=detail) from error

    run.advance_generation += 1
    if action.status == ResearchActionStatus.WAITING.value:
        run.status = ResearchRunStatus.WAITING_FOR_EVENT.value
    else:
        run.status = ResearchRunStatus.RUNNING.value
        if config.effective_ai_enabled:
            await enqueue_research_advance(db_session, task=task, run=run)
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind=event_kind,
        actor_user_id=current_user.id,
        payload={
            "resource_id": str(resource.id),
            "reservation_id": str(typed.id),
            "status": typed.status,
        },
        idempotency_key=f"research-resource:{typed.id}:created",
    )
    await db_session.commit()
    return _reservation_payload(action, typed, resource=resource)


async def _reservation_context(
    db_session: DBSession,
    current_user: User,
    reservation_id: UUID,
) -> tuple[
    ResearchResourceReservation,
    ResearchAction,
    ResearchRun,
    ResearchTask,
    Project,
    Lab,
    Resource,
]:
    reservation = await db_session.get(ResearchResourceReservation, reservation_id)
    action = (
        await db_session.get(ResearchAction, reservation.action_id)
        if reservation is not None
        else None
    )
    run = await db_session.get(ResearchRun, action.run_id) if action is not None else None
    task = await db_session.get(ResearchTask, run.task_id) if run is not None else None
    if reservation is None or action is None or run is None or task is None:
        raise HTTPException(status_code=404, detail="Research Resource Reservation not found")
    project = await _project(db_session, task.project_id)
    await require_research_capability(
        db_session, user=current_user, project=project, capability="research.run"
    )
    lab = await db_session.get(Lab, task.lab_id)
    resource = await db_session.get(Resource, reservation.resource_id)
    if lab is None or resource is None:
        raise HTTPException(status_code=404, detail="Resource context not found")
    access = await resolve_resource_access(
        db_session,
        current_user.id,
        lab.id,
        resource_type_id=resource.resource_type_id,
        resource_id=resource.id,
    )
    capability = (
        "inventory.operate"
        if reservation.kind == "inventory"
        else "equipment.book"
    )
    if not access.allows(capability) or not _restricted_resource_allowed(
        resource, access
    ):
        raise HTTPException(status_code=403, detail="Resource reservation access denied")
    return reservation, action, run, task, project, lab, resource


@router.post("/research-resource-reservations/{reservation_id}/sync")
async def sync_resource_reservation(
    reservation_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    reservation, action, run, task, _project_context, _lab, resource = (
        await _reservation_context(db_session, current_user, reservation_id)
    )
    if reservation.kind != "equipment" or reservation.equipment_booking_id is None:
        return _reservation_payload(action, reservation, resource=resource)
    booking = await db_session.get(EquipmentBooking, reservation.equipment_booking_id)
    if booking is None:
        raise HTTPException(status_code=409, detail="Equipment booking is unavailable")
    status_map = {
        BookingStatus.PENDING.value: (
            ResearchResourceReservationStatus.PENDING_APPROVAL.value,
            ResearchActionStatus.WAITING.value,
        ),
        BookingStatus.APPROVED.value: (
            ResearchResourceReservationStatus.APPROVED.value,
            ResearchActionStatus.COMPLETED.value,
        ),
        BookingStatus.REJECTED.value: (
            ResearchResourceReservationStatus.REJECTED.value,
            ResearchActionStatus.FAILED.value,
        ),
        BookingStatus.CANCELLED.value: (
            ResearchResourceReservationStatus.CANCELLED.value,
            ResearchActionStatus.CANCELLED.value,
        ),
        BookingStatus.COMPLETED.value: (
            ResearchResourceReservationStatus.COMPLETED.value,
            ResearchActionStatus.COMPLETED.value,
        ),
    }
    next_reservation_status, next_action_status = status_map[booking.status]
    changed = (
        reservation.status != next_reservation_status
        or action.status != next_action_status
    )
    if changed:
        reservation.status = next_reservation_status
        reservation.revision += 1
        action.status = next_action_status
        action.revision += 1
        action.output_data = {
            **(action.output_data or {}),
            "status": booking.status,
            "synced_at": utcnow().isoformat(),
        }
        if next_action_status in {
            ResearchActionStatus.COMPLETED.value,
            ResearchActionStatus.FAILED.value,
            ResearchActionStatus.CANCELLED.value,
        }:
            action.completed_at = utcnow()
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
        if next_action_status in {
            ResearchActionStatus.COMPLETED.value,
            ResearchActionStatus.FAILED.value,
            ResearchActionStatus.CANCELLED.value,
        }:
            run.status = ResearchRunStatus.RUNNING.value
            run.last_error = (
                None
                if next_action_status == ResearchActionStatus.COMPLETED.value
                else f"Equipment booking {booking.status}"
            )
            if task.status == ResearchTaskStatus.ACTIVE.value and config.effective_ai_enabled:
                await enqueue_research_advance(db_session, task=task, run=run)
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind="resource.equipment_booking_synced",
            actor_user_id=current_user.id,
            payload={"booking_id": str(booking.id), "status": booking.status},
            idempotency_key=f"research-resource:{reservation.id}:sync:{reservation.revision}",
        )
        await db_session.commit()
    return _reservation_payload(action, reservation, resource=resource)


def _release_command(
    reservation: ResearchResourceReservation,
    params: ResourceReleaseDraft,
    underlying_status: str,
) -> dict[str, Any]:
    return {
        "reservation_id": str(reservation.id),
        "expected_revision": params.expected_revision,
        "kind": reservation.kind,
        "underlying_status": underlying_status,
        "reason": params.reason,
    }


async def _validate_release(
    db_session: DBSession,
    reservation: ResearchResourceReservation,
    params: ResourceReleaseDraft,
) -> tuple[str, InventoryReservation | EquipmentBooking]:
    if reservation.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Resource Reservation changed")
    if reservation.kind == "inventory":
        underlying = (
            await db_session.get(
                InventoryReservation, reservation.inventory_reservation_id
            )
            if reservation.inventory_reservation_id
            else None
        )
        if underlying is None or underlying.status != "active":
            raise HTTPException(status_code=409, detail="Inventory reservation is not active")
    else:
        underlying = (
            await db_session.get(EquipmentBooking, reservation.equipment_booking_id)
            if reservation.equipment_booking_id
            else None
        )
        if underlying is None or underlying.status not in {
            BookingStatus.PENDING.value,
            BookingStatus.APPROVED.value,
        }:
            raise HTTPException(status_code=409, detail="Equipment booking is not cancellable")
    return underlying.status, underlying


@router.post("/research-resource-reservations/{reservation_id}/release/preview")
async def preview_resource_release(
    reservation_id: UUID,
    params: ResourceReleaseDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    reservation, action, run, task, project, lab, resource = (
        await _reservation_context(db_session, current_user, reservation_id)
    )
    underlying_status, _underlying = await _validate_release(
        db_session, reservation, params
    )
    command = _release_command(reservation, params, underlying_status)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": _destination(task=task, project=project, lab=lab, run=run),
        "action": {"id": str(action.id), "title": action.title},
        "resource": {"id": str(resource.id), "name": resource.name},
        "effect": (
            "Release the inventory quantity back to available stock"
            if reservation.kind == "inventory"
            else "Cancel the equipment booking"
        ),
    }


@router.post("/research-resource-reservations/{reservation_id}/release")
async def release_resource_reservation(
    reservation_id: UUID,
    params: ResourceRelease,
    current_user: CurrentUser,
    db_session: DBSession,
):
    reservation, action, run, task, _project_context, lab, resource = (
        await _reservation_context(db_session, current_user, reservation_id)
    )
    underlying_status, underlying = await _validate_release(
        db_session, reservation, params
    )
    command = _release_command(reservation, params, underlying_status)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Release preview has changed")
    if reservation.kind == "inventory":
        try:
            await release_inventory_reservation(
                db_session,
                reservation=underlying,
                actor_user_id=current_user.id,
                idempotency_key=f"research-resource:{reservation.id}:release",
                reason=params.reason,
            )
        except InventoryError as error:
            await db_session.rollback()
            raise HTTPException(status_code=409, detail=str(error)) from error
        reservation.status = ResearchResourceReservationStatus.RELEASED.value
    else:
        booking: EquipmentBooking = underlying
        if booking.user_id != current_user.id:
            access = await resolve_resource_access(
                db_session,
                current_user.id,
                lab.id,
                resource_type_id=resource.resource_type_id,
                resource_id=resource.id,
            )
            if not access.allows("resource.custody"):
                raise HTTPException(
                    status_code=403,
                    detail="Only the requester or a resource custodian can cancel this booking",
                )
        booking.status = BookingStatus.CANCELLED.value
        reservation.status = ResearchResourceReservationStatus.CANCELLED.value
    reservation.revision += 1
    action.output_data = {
        **(action.output_data or {}),
        "status": reservation.status,
        "released_at": utcnow().isoformat(),
        "release_reason": params.reason,
    }
    action.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="resource.reservation_released",
        actor_user_id=current_user.id,
        payload={
            "reservation_id": str(reservation.id),
            "resource_id": str(resource.id),
            "kind": reservation.kind,
            "reason": params.reason,
        },
        idempotency_key=f"research-resource:{reservation.id}:released",
    )
    await db_session.commit()
    return _reservation_payload(action, reservation, resource=resource)
