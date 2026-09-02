import asyncio
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.main import app
from app.models.research import (
    ResearchActionKind,
    ResearchRunStatus,
    ResearchTaskStatus,
)
from app.routers.research_tasks import ResearchTaskDraft
from app.services import resource_job_worker
from app.services.research_runtime import (
    EXPECTED_AIRA_STEPS,
    canonical_digest,
    initial_aira_state,
    path_status_after_step,
    research_task_command,
)


def test_research_task_command_is_canonical_and_digest_is_stable():
    project_id = uuid4()
    owner_id = uuid4()
    protocol_id = uuid4()

    command = research_task_command(
        project_id=project_id,
        title="  Protein stability study  ",
        goal="  Identify a stable condition  ",
        success_criteria=[" Reproducible signal ", "", " CV below 10% "],
        stop_conditions=[" Safety threshold exceeded "],
        autonomy_level="assisted",
        protocol_ids=[protocol_id],
        owner_user_id=owner_id,
        ai_model="  qwen3.5-flash  ",
    )

    assert command == {
        "project_id": str(project_id),
        "title": "Protein stability study",
        "goal": "Identify a stable condition",
        "success_criteria": ["Reproducible signal", "CV below 10%"],
        "stop_conditions": ["Safety threshold exceeded"],
        "autonomy_level": "assisted",
        "protocol_ids": [str(protocol_id)],
        "owner_user_id": str(owner_id),
        "ai_model": "qwen3.5-flash",
    }
    assert canonical_digest(command) == canonical_digest(dict(reversed(command.items())))
    assert len(canonical_digest(command)) == 64


def test_research_task_draft_rejects_missing_criteria_and_duplicate_protocols():
    protocol_id = uuid4()
    payload = {
        "project_id": uuid4(),
        "title": "Study",
        "goal": "Answer a question",
        "success_criteria": ["Measured result"],
        "protocol_ids": [protocol_id],
    }

    with pytest.raises(ValidationError):
        ResearchTaskDraft(**{**payload, "success_criteria": [" "]})
    with pytest.raises(ValidationError):
        ResearchTaskDraft(
            **{**payload, "protocol_ids": [protocol_id, protocol_id]}
        )


def test_aira_path_transitions_preserve_human_record_boundary():
    state = initial_aira_state("Determine the best condition")

    assert state["path_status"] == "waiting_for_research_strategy"
    assert (
        path_status_after_step(
            state["path_status"],
            {"data": {"researchable": True}},
        )
        == "waiting_for_next_protocol"
    )
    assert (
        path_status_after_step(
            "waiting_for_next_protocol", {"data": {"end_path": False}}
        )
        == "waiting_for_initial_values_for_fields_in_next_protocol"
    )
    assert (
        path_status_after_step(
            "waiting_for_initial_values_for_fields_in_next_protocol",
            {"data": {}},
        )
        == "waiting_for_record"
    )
    assert (
        path_status_after_step(
            "waiting_for_phased_research_conclusion", {"data": {}}
        )
        == "waiting_for_next_protocol"
    )
    assert EXPECTED_AIRA_STEPS["waiting_for_final_research_conclusion"] == (
        "add_final_research_conclusion"
    )


def test_research_runtime_has_explicit_review_and_human_states():
    assert ResearchTaskStatus.REVIEW_REQUIRED.value == "review_required"
    assert ResearchRunStatus.WAITING_FOR_HUMAN.value == "waiting_for_human"
    assert ResearchActionKind.PROTOCOL_RUN.value == "protocol_run"
    assert ResearchActionKind.HUMAN_WORK_ITEM.value == "human_work_item"


def test_persistent_worker_dispatches_research_run(monkeypatch):
    run_id = uuid4()
    advance = AsyncMock(return_value={"status": "waiting_for_human"})
    monkeypatch.setattr(resource_job_worker, "process_research_run_advance", advance)

    result = asyncio.run(
        resource_job_worker.process_persistent_job(
            SimpleNamespace(),
            SimpleNamespace(
                kind="research_run_advance",
                payload={"run_id": str(run_id), "generation": 3},
            ),
        )
    )

    assert result == {"status": "waiting_for_human"}
    advance.assert_awaited_once_with(
        ANY,
        run_id=run_id,
        generation=3,
    )


def test_openapi_exposes_research_task_and_human_work_contracts():
    paths = app.openapi()["paths"]

    assert "/research-tasks/preview" in paths
    assert "/research-tasks" in paths
    assert "/research-tasks/{task_id}" in paths
    assert "/research-tasks/{task_id}/start" in paths
    assert "/research-tasks/{task_id}/actions/preview" in paths
    assert "/research-work-items" in paths
    assert "/research-work-items/{work_item_id}/submit" in paths
