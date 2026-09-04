import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.models.protocol import Protocol
from app.models.research import ResearchAction, ResearchRun, ResearchTask
from app.models.research_execution import (
    ResearchResourceConsumption,
    ResearchResourceReservationStatus,
)
from app.services import research_runtime, resource_inventory


class ScalarRows:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


@pytest.mark.parametrize(
    ("reserved_quantity", "consume_quantity", "expected_remaining", "expected_status"),
    [
        ("3", "1", "2", ResearchResourceReservationStatus.ACTIVE.value),
        ("3", "3", "0", ResearchResourceReservationStatus.COMPLETED.value),
    ],
)
def test_record_consumption_updates_inventory_and_projects_research_state(
    monkeypatch,
    reserved_quantity,
    consume_quantity,
    expected_remaining,
    expected_status,
):
    lab_id = uuid4()
    resource_id = uuid4()
    container_id = uuid4()
    actor_user_id = uuid4()
    event_id = uuid4()
    consumption_id = uuid4()
    reservation = SimpleNamespace(
        id=uuid4(),
        lab_id=lab_id,
        resource_id=resource_id,
        container_id=container_id,
        quantity=Decimal(reserved_quantity),
        unit="mL",
        status="active",
        expires_at=None,
    )
    resource = SimpleNamespace(id=resource_id)
    record = SimpleNamespace(id=uuid4(), version=2, protocol_id=uuid4())
    event = SimpleNamespace(
        id=event_id,
        resource_id=resource_id,
        container_id=container_id,
        quantity=Decimal(consume_quantity),
        unit="mL",
    )
    typed = SimpleNamespace(
        id=uuid4(),
        action_id=uuid4(),
        status=ResearchResourceReservationStatus.ACTIVE.value,
        revision=1,
    )
    action = SimpleNamespace(
        id=typed.action_id,
        run_id=uuid4(),
        output_data={"inventory_reservation_id": str(reservation.id)},
        revision=3,
    )
    run = SimpleNamespace(id=action.run_id, task_id=uuid4())
    project_id = uuid4()
    task = SimpleNamespace(id=run.task_id, lab_id=lab_id, project_id=project_id)
    protocol = SimpleNamespace(id=record.protocol_id, project_id=project_id)
    added = []

    def add(model):
        added.append(model)

    async def flush():
        for model in added:
            if isinstance(model, ResearchResourceConsumption) and model.id is None:
                model.id = consumption_id

    async def get_model(model, model_id):
        if model is ResearchAction and model_id == action.id:
            return action
        if model is ResearchRun and model_id == run.id:
            return run
        if model is ResearchTask and model_id == task.id:
            return task
        if model is Protocol and model_id == protocol.id:
            return protocol
        return None

    db_session = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                ScalarRows(reservation),
                ScalarRows(None),
                ScalarRows(typed),
                ScalarRows(None),
            ]
        ),
        get=AsyncMock(side_effect=get_model),
        add=Mock(side_effect=add),
        flush=AsyncMock(side_effect=flush),
    )
    apply_event = AsyncMock(return_value=event)
    emit_event = AsyncMock()
    monkeypatch.setattr(resource_inventory, "apply_inventory_event", apply_event)
    monkeypatch.setattr(research_runtime, "emit_research_event", emit_event)

    result = asyncio.run(
        resource_inventory.consume_reserved_inventory_for_record(
            db_session,
            lab_id=lab_id,
            resource=resource,
            container_id=container_id,
            reservation_id=reservation.id,
            quantity=Decimal(consume_quantity),
            unit="mL",
            record=record,
            field_path="$.materials[0]",
            actor_user_id=actor_user_id,
        )
    )

    assert result is event
    assert reservation.status == (
        "consumed" if expected_status == "completed" else "active"
    )
    if reservation.status == "active":
        assert reservation.quantity == Decimal(expected_remaining)
    assert typed.status == expected_status
    assert typed.revision == 2
    assert action.revision == 4
    consumption = next(
        model for model in added if isinstance(model, ResearchResourceConsumption)
    )
    assert consumption.inventory_event_id == event_id
    assert consumption.record_id == record.id
    assert consumption.record_version == record.version
    assert consumption.quantity == Decimal(consume_quantity)
    assert consumption.remaining_quantity == Decimal(expected_remaining)
    assert action.output_data["inventory_consumption"] == {
        "consumption_id": str(consumption_id),
        "inventory_event_id": str(event_id),
        "record_id": str(record.id),
        "record_version": record.version,
        "field_path": "$.materials[0]",
        "quantity": consume_quantity,
        "unit": "mL",
        "remaining_quantity": expected_remaining,
        "remaining_unit": "mL",
        "reservation_status": expected_status,
    }
    assert run.aira_state["resource_results"][-1]["result"] == (
        action.output_data["inventory_consumption"]
    )
    emit_event.assert_awaited_once()
    assert emit_event.await_args.kwargs["kind"] == "resource.inventory_consumed"
    assert emit_event.await_args.kwargs["idempotency_key"] == (
        f"research-resource:{typed.id}:consume:{event_id}"
    )


def test_repeated_record_consumption_reuses_event_and_consumption_projection(
    monkeypatch,
):
    lab_id = uuid4()
    resource_id = uuid4()
    container_id = uuid4()
    reservation = SimpleNamespace(
        id=uuid4(),
        lab_id=lab_id,
        resource_id=resource_id,
        container_id=container_id,
        quantity=Decimal(2),
        unit="mL",
        status="active",
        expires_at=None,
    )
    event = SimpleNamespace(
        id=uuid4(),
        resource_id=resource_id,
        container_id=container_id,
        quantity=Decimal(1),
        unit="mL",
    )
    existing_consumption = SimpleNamespace(id=uuid4())
    typed = SimpleNamespace(id=uuid4(), action_id=uuid4())
    action = SimpleNamespace(id=typed.action_id, run_id=uuid4())
    run = SimpleNamespace(id=action.run_id, task_id=uuid4())
    project_id = uuid4()
    record = SimpleNamespace(id=uuid4(), version=1, protocol_id=uuid4())
    task = SimpleNamespace(id=run.task_id, lab_id=lab_id, project_id=project_id)
    protocol = SimpleNamespace(id=record.protocol_id, project_id=project_id)

    async def get_model(model, model_id):
        values = {
            (ResearchAction, action.id): action,
            (ResearchRun, run.id): run,
            (ResearchTask, task.id): task,
            (Protocol, protocol.id): protocol,
        }
        return values.get((model, model_id))

    db_session = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                ScalarRows(reservation),
                ScalarRows(event),
                ScalarRows(typed),
                ScalarRows(existing_consumption),
            ]
        ),
        get=AsyncMock(side_effect=get_model),
        add=Mock(),
    )
    apply_event = AsyncMock()
    monkeypatch.setattr(resource_inventory, "apply_inventory_event", apply_event)

    result = asyncio.run(
        resource_inventory.consume_reserved_inventory_for_record(
            db_session,
            lab_id=lab_id,
            resource=SimpleNamespace(id=resource_id),
            container_id=container_id,
            reservation_id=reservation.id,
            quantity=Decimal(1),
            unit="mL",
            record=record,
            field_path="$.materials[0]",
            actor_user_id=uuid4(),
        )
    )

    assert result is event
    assert reservation.quantity == Decimal(2)
    apply_event.assert_not_awaited()
    db_session.add.assert_not_called()


def test_research_reservation_cannot_be_consumed_by_another_project_record(
    monkeypatch,
):
    lab_id = uuid4()
    resource_id = uuid4()
    container_id = uuid4()
    reservation = SimpleNamespace(
        id=uuid4(),
        lab_id=lab_id,
        resource_id=resource_id,
        container_id=container_id,
        quantity=Decimal(2),
        unit="mL",
        status="active",
        expires_at=None,
    )
    typed = SimpleNamespace(id=uuid4(), action_id=uuid4())
    action = SimpleNamespace(id=typed.action_id, run_id=uuid4())
    run = SimpleNamespace(id=action.run_id, task_id=uuid4())
    task = SimpleNamespace(id=run.task_id, lab_id=lab_id, project_id=uuid4())
    record = SimpleNamespace(id=uuid4(), version=1, protocol_id=uuid4())
    protocol = SimpleNamespace(id=record.protocol_id, project_id=uuid4())

    async def get_model(model, model_id):
        values = {
            (ResearchAction, action.id): action,
            (ResearchRun, run.id): run,
            (ResearchTask, task.id): task,
            (Protocol, protocol.id): protocol,
        }
        return values.get((model, model_id))

    db_session = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                ScalarRows(reservation),
                ScalarRows(None),
                ScalarRows(typed),
            ]
        ),
        get=AsyncMock(side_effect=get_model),
    )
    apply_event = AsyncMock()
    monkeypatch.setattr(resource_inventory, "apply_inventory_event", apply_event)

    with pytest.raises(
        resource_inventory.InventoryError,
        match="belongs to another Project",
    ):
        asyncio.run(
            resource_inventory.consume_reserved_inventory_for_record(
                db_session,
                lab_id=lab_id,
                resource=SimpleNamespace(id=resource_id),
                container_id=container_id,
                reservation_id=reservation.id,
                quantity=Decimal(1),
                unit="mL",
                record=record,
                field_path="$.materials[0]",
                actor_user_id=uuid4(),
            )
        )

    apply_event.assert_not_awaited()
