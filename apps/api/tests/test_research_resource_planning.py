import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.models.research import ResearchAction, ResearchRun, ResearchTask
from app.models.resource import (
    InventoryBalance,
    Resource,
    ResourceContainer,
    ResourceRevision,
)
from app.services import research_resources, research_runtime
from app.services.research_planner import AiraActionProposal


def _resource_environment(resource_type_id, type_revision_id):
    return {
        "resources": [
            {
                "key": f"resource:{resource_type_id}",
                "version": "2",
                "source_id": str(resource_type_id),
                "source_revision_id": str(type_revision_id),
                "metadata": {
                    "capabilities": {"inventory": True, "booking": False},
                    "booking_policy": "none",
                },
            }
        ]
    }


def test_resource_availability_exposes_only_permissioned_live_balances(monkeypatch):
    lab_id = uuid4()
    user_id = uuid4()
    resource_type_id = uuid4()
    type_revision_id = uuid4()
    resource = Resource(
        id=uuid4(),
        lab_id=lab_id,
        resource_type_id=resource_type_id,
        current_revision_id=uuid4(),
        name="Antibody A",
        code="AB-1",
        created_by_user_id=user_id,
    )
    revision = ResourceRevision(
        id=resource.current_revision_id,
        resource_id=resource.id,
        resource_type_revision_id=type_revision_id,
        revision=4,
        created_by_user_id=user_id,
    )
    container = ResourceContainer(
        id=uuid4(),
        lab_id=lab_id,
        resource_id=resource.id,
        code="VIAL-1",
        unit="mg",
    )
    balance = InventoryBalance(
        container_id=container.id,
        on_hand=Decimal(10),
        reserved=Decimal("2.5"),
        unit="mg",
        version=7,
    )
    task = ResearchTask(id=uuid4(), lab_id=lab_id)
    run = ResearchRun(
        id=uuid4(),
        environment_snapshot=_resource_environment(resource_type_id, type_revision_id),
    )
    db_session = AsyncMock()
    db_session.scalars.return_value = SimpleNamespace(all=lambda: [resource])
    db_session.get.return_value = revision
    db_session.execute.return_value = SimpleNamespace(
        all=lambda: [(container, balance, None)]
    )
    can_operate = AsyncMock(return_value=True)
    monkeypatch.setattr(research_resources, "_can_operate_resource", can_operate)

    result = asyncio.run(
        research_resources.resource_availability_for_planner(
            db_session,
            task=task,
            run=run,
            user_id=user_id,
        )
    )

    assert result[0]["available"] is True
    assert result[0]["accessible_resource_count"] == 1
    assert result[0]["inventory_options"][0]["balances"] == [
        {
            "container_code": "VIAL-1",
            "available": "7.5",
            "unit": "mg",
            "balance_version": 7,
            "lot_expires_at": None,
        }
    ]

    can_operate.return_value = False
    hidden = asyncio.run(
        research_resources.resource_availability_for_planner(
            db_session,
            task=task,
            run=run,
            user_id=user_id,
        )
    )
    assert hidden[0]["available"] is False
    assert hidden[0]["inventory_options"] == []
    assert hidden[0]["accessible_resource_count"] == 0


def test_repeated_unavailable_resource_becomes_a_typed_wait(monkeypatch):
    task = ResearchTask(id=uuid4())
    run = ResearchRun(id=uuid4(), aira_state={})
    proposal = AiraActionProposal.model_validate(
        {
            "decision": "resource",
            "resource_request": {
                "resource_type_key": "resource:antibody",
                "kind": "inventory",
                "quantity": "2",
                "unit": "mg",
                "purpose": "Run the planned assay",
            },
        }
    )
    db_session = AsyncMock()
    emitted = AsyncMock()
    monkeypatch.setattr(research_runtime, "emit_research_event", emitted)
    wait_action = ResearchAction(id=uuid4())
    materialize = AsyncMock(return_value=wait_action)
    monkeypatch.setattr(research_runtime, "_materialize_aira_action", materialize)

    first = asyncio.run(
        research_runtime._recover_unavailable_resource_proposal(
            db_session,
            task=task,
            run=run,
            proposal=proposal,
            step_index=3,
            error=ValueError("No live inventory"),
        )
    )
    assert first is None
    assert run.aira_state["resource_constraints"][0]["repeat_count"] == 1
    materialize.assert_not_awaited()

    second = asyncio.run(
        research_runtime._recover_unavailable_resource_proposal(
            db_session,
            task=task,
            run=run,
            proposal=proposal,
            step_index=3,
            error=ValueError("No live inventory"),
        )
    )
    assert second == [wait_action]
    assert run.aira_state["resource_constraints"][-1]["repeat_count"] == 2
    wait_proposal = materialize.await_args.kwargs["proposal"]
    assert wait_proposal.decision == "wait"
    assert wait_proposal.wait_template_key == "resource.available"
    assert materialize.await_args.kwargs["idempotency_key_override"].startswith(
        "aira-resource-wait:3:"
    )
    assert emitted.await_count == 2
