"""Pure governance arithmetic: no Runner, code execution or database doubles."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.research_budget import (
    ResearchBudgetError,
    protected_compute_reservations,
)
from app.services.workflow_compute_runtime import (
    failure_only_frontier,
    governance,
    stable_compute_contract,
)


def entry(kind, amount, *, source="job-a", currency="USD", source_type="compute_job"):
    return {
        "kind": kind,
        "amount": amount,
        "currency": currency,
        "source_ref": source,
        "source_type": source_type,
    }


def test_automatic_reservations_are_attributed_per_job_not_to_manual_releases():
    snapshot = {
        "currency": "USD",
        "entries": [
            entry("reserve", "0.1"),
            entry("release", "0.1", source_type="manual"),
            entry("reserve", "0.1", source="job-b"),
        ],
    }
    assert protected_compute_reservations(snapshot) == Decimal("0.2")
    snapshot["entries"].append(entry("release", "0.1"))
    assert protected_compute_reservations(snapshot) == Decimal("0.1")


@pytest.mark.parametrize(
    "entries",
    [
        [entry("reserve", "0.1", currency="EUR")],
        [entry("release", "0.1")],
        [entry("reserve", "0.1", source="")],
    ],
)
def test_invalid_automatic_reservation_attribution_fails_closed(entries):
    with pytest.raises(ResearchBudgetError):
        protected_compute_reservations({"currency": "USD", "entries": entries})


def test_compute_approval_seals_inputs_but_not_live_runner_count_or_display_name():
    summary = {
        "compute": {
            "input": {"sha256": "a", "record_count": 2},
            "approver": {"id": "user", "name": "First name"},
            "ready_runner_count": 1,
            "authorized_runner_count": 1,
        }
    }
    original = stable_compute_contract(summary)
    summary["compute"]["ready_runner_count"] = 0
    summary["compute"]["approver"]["name"] = "New name"
    assert stable_compute_contract(summary) == original
    summary["compute"]["input"]["record_count"] = 3
    assert stable_compute_contract(summary) != original
    assert "name" in summary["compute"]["approver"]


@pytest.mark.parametrize(
    "marker",
    [
        {},
        {"execution_contract_version": 3, "compute_governance": {"a": {}}},
        {"execution_contract_version": 4, "compute_governance": {}},
    ],
)
def test_compute_requires_explicit_new_execution_contract_and_node_governance(marker):
    with pytest.raises(HTTPException):
        governance(
            SimpleNamespace(environment_snapshot={"manual_workflow": marker}),
            SimpleNamespace(input_data={"action_graph": {"node_id": "a"}}),
        )


@pytest.mark.parametrize(
    "parent_status,state,expected",
    [
        ("failed", None, True),
        ("cancelled", None, True),
        ("skipped", "blocked", True),
        ("skipped", "branch_not_selected", False),
        ("completed", None, False),
    ],
)
def test_failure_only_settlement_never_treats_an_inactive_branch_as_failure(
    parent_status, state, expected
):
    actions = [
        SimpleNamespace(
            id="a",
            status=parent_status,
            input_data={"workflow_resolution": {"state": state}},
        ),
        SimpleNamespace(id="b", status="blocked", input_data={}),
        SimpleNamespace(id="c", status="blocked", input_data={}),
    ]
    dependencies = [
        SimpleNamespace(action_id="b", depends_on_action_id="a"),
        SimpleNamespace(action_id="c", depends_on_action_id="b"),
    ]
    assert failure_only_frontier(actions, dependencies) is expected
    actions.append(SimpleNamespace(id="independent", status="blocked", input_data={}))
    assert not failure_only_frontier(actions, dependencies)


def test_failure_settlement_waits_for_all_parents_and_rejects_an_approval_frontier():
    actions = [
        SimpleNamespace(id="a", status="cancelled", input_data={}),
        SimpleNamespace(id="b", status="proposed", input_data={}),
        SimpleNamespace(id="join", status="blocked", input_data={}),
    ]
    dependencies = [
        SimpleNamespace(action_id="join", depends_on_action_id=value)
        for value in ("a", "b")
    ]
    assert not failure_only_frontier(actions, dependencies)
