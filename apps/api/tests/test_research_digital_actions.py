from importlib import import_module
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock
from uuid import uuid4

import asyncio
import pytest
from app.main import app
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.research_execution import ResearchToolJob, ResearchWaitEvent
from app.routers.research_actions import WaitEventDraft
from app.services import resource_job_worker
from app.models.research import (
    ResearchActionStatus,
    ResearchRunStatus,
    ResearchTaskStatus,
)
from app.services.research_tools import (
    get_research_tool,
    research_tool_catalog,
    validate_tool_arguments,
)
from app.services import research_runtime
from app.services.research_capabilities import (
    executor_bindings_for_environment,
    pinned_tool_definition,
    protocol_capability,
    tool_capability,
)
from app.services.research_runtime import (
    activate_tool_action,
    activate_wait_event_action,
)
from pydantic import ValidationError


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def test_tool_jobs_are_typed_one_to_one_action_executions():
    ddl = compile_table(ResearchToolJob)

    assert "UNIQUE (action_id)" in ddl
    assert "tool_key" in ddl
    assert "arguments" in ddl
    assert "timeout_seconds" in ddl


def test_wait_events_have_unique_keys_payload_contract_and_stale_guard():
    ddl = compile_table(ResearchWaitEvent)

    assert "UNIQUE (event_key)" in ddl
    assert "expected_event_type" in ddl
    assert "payload_schema" in ddl
    assert "revision" in ddl


def test_digital_action_migration_follows_scientific_assets():
    migration = import_module("migrations.versions.0015_research_digital_actions")

    assert migration.down_revision == "0014_research_assets"
    assert migration.TABLE_NAMES == ("research_tool_jobs", "research_wait_events")


def test_tool_catalog_is_allowlisted_versioned_and_schema_validated():
    catalog = research_tool_catalog()

    assert set(catalog) == {"knowledge.search", "literature.search"}
    assert catalog["knowledge.search"].version == "1"
    assert catalog["knowledge.search"].available is True
    validate_tool_arguments(catalog["knowledge.search"], {"query": "RNA", "limit": 5})
    with pytest.raises(ValueError, match="Invalid Tool arguments"):
        validate_tool_arguments(catalog["knowledge.search"], {"query": ""})
    with pytest.raises(ValueError, match="Invalid Tool arguments"):
        validate_tool_arguments(
            catalog["knowledge.search"], {"query": "RNA", "unknown": True}
        )
    with pytest.raises(ValueError, match="Unknown Research Tool"):
        get_research_tool("shell.run")


def test_tool_execution_is_limited_to_the_pinned_environment():
    environment = {
        "schema": "airalogy.research-environment.v2",
        "tools": [research_tool_catalog()["knowledge.search"].payload()],
    }

    assert pinned_tool_definition(environment, "knowledge.search").version == "1"
    with pytest.raises(ValueError, match="not pinned"):
        pinned_tool_definition(environment, "literature.search")


def test_capability_registry_is_derived_and_executor_bindings_are_explicit():
    protocol_id = uuid4()
    version_id = uuid4()
    protocol = SimpleNamespace(
        id=protocol_id,
        uid="rna_assay",
        name="RNA assay",
        description="Measure RNA",
    )
    version = SimpleNamespace(
        id=version_id,
        version="1.2.0",
        json_schema={"type": "object"},
    )
    protocol_item = protocol_capability(protocol, version).payload()
    tool_item = tool_capability(
        research_tool_catalog()["knowledge.search"]
    ).payload()
    bindings = executor_bindings_for_environment(
        protocol_capabilities=[protocol_item],
        tool_capabilities=[tool_item],
        owner_user_id=str(uuid4()),
    )

    assert protocol_item["key"] == f"protocol:{protocol_id}"
    assert protocol_item["source_revision_id"] == str(version_id)
    assert tool_item["key"] == "tool:knowledge.search"
    assert bindings[0]["mode"] == "protocol_record"
    assert bindings[1]["mode"] == "durable_job"
    assert all(item["policy"] == "approval_required_for_aira" for item in bindings)


def test_wait_event_draft_validates_contract_and_normalizes_naive_deadline():
    deadline = datetime.now() + timedelta(hours=1)
    draft = WaitEventDraft(
        title="Wait for instrument upload",
        event_key="instrument.run-42.completed",
        expected_event_type="instrument.completed",
        payload_schema={
            "type": "object",
            "required": ["file_id"],
            "properties": {"file_id": {"type": "string"}},
        },
        due_at=deadline,
        idempotency_key="wait-instrument-run-42",
    )

    assert draft.due_at == deadline.replace(tzinfo=UTC)
    with pytest.raises(ValidationError, match="Invalid event payload Schema"):
        WaitEventDraft(
            title="Broken contract",
            event_key="broken.contract",
            expected_event_type="broken",
            payload_schema={"type": "not-a-json-schema-type"},
            idempotency_key="broken-contract-key",
        )


def test_wait_event_has_a_distinct_run_boundary():
    assert ResearchRunStatus.WAITING_FOR_TOOL.value == "waiting_for_tool"
    assert ResearchRunStatus.WAITING_FOR_EVENT.value == "waiting_for_event"
    with pytest.raises(ValidationError, match="must be in the future"):
        WaitEventDraft(
            title="Expired event",
            event_key="expired.event",
            expected_event_type="expired",
            due_at=datetime.now(UTC) - timedelta(seconds=1),
            idempotency_key="expired-event-key",
        )


def test_persistent_worker_dispatches_research_tool_job(monkeypatch):
    tool_job_id = uuid4()
    process = AsyncMock(return_value={"items": []})
    monkeypatch.setattr(resource_job_worker, "process_research_tool_job", process)

    result = asyncio.run(
        resource_job_worker.process_persistent_job(
            SimpleNamespace(),
            SimpleNamespace(
                kind="research_tool_job",
                payload={"tool_job_id": str(tool_job_id)},
            ),
        )
    )

    assert result == {"items": []}
    process.assert_awaited_once_with(ANY, tool_job_id=tool_job_id)


def test_openapi_exposes_digital_action_preview_confirm_contracts():
    paths = app.openapi()["paths"]

    assert "/research-tools" in paths
    assert "/research-tasks/{task_id}/tool-actions/preview" in paths
    assert "/research-tasks/{task_id}/tool-actions" in paths
    assert "/research-tasks/{task_id}/wait-actions/preview" in paths
    assert "/research-tasks/{task_id}/wait-actions" in paths
    assert "/research-wait-events/{wait_event_id}/signal/preview" in paths
    assert "/research-wait-events/{wait_event_id}/signal" in paths


def test_approved_tool_action_is_queued_at_a_durable_boundary(monkeypatch):
    job = SimpleNamespace(
        id=uuid4(),
        tool_key="knowledge.search",
        tool_version="1",
        status="queued",
    )
    action = SimpleNamespace(
        id=uuid4(),
        policy_decision="allow",
        status=ResearchActionStatus.PROPOSED.value,
        revision=1,
    )
    run = SimpleNamespace(id=uuid4(), status="waiting_for_approval", last_error="old")
    task = SimpleNamespace(
        id=uuid4(), lab_id=uuid4(), status=ResearchTaskStatus.ACTIVE.value
    )
    monkeypatch.setattr(
        ResearchToolJob, "find_by", AsyncMock(return_value=job)
    )
    enqueue = AsyncMock()
    emit = AsyncMock()
    monkeypatch.setattr(research_runtime, "enqueue_job", enqueue)
    monkeypatch.setattr(research_runtime, "emit_research_event", emit)

    result = asyncio.run(
        activate_tool_action(
            SimpleNamespace(),
            task=task,
            run=run,
            action=action,
            actor_user_id=uuid4(),
        )
    )

    assert result is job
    assert action.status == ResearchActionStatus.QUEUED.value
    assert run.status == ResearchRunStatus.WAITING_FOR_TOOL.value
    assert run.last_error is None
    enqueue.assert_awaited_once()
    emit.assert_awaited_once()


def test_approved_wait_action_opens_only_the_pinned_event(monkeypatch):
    event = SimpleNamespace(
        id=uuid4(),
        event_key="aira.run.step.data_asset.ready",
        expected_event_type="data_asset.ready",
        status="waiting",
    )
    action = SimpleNamespace(
        id=uuid4(),
        policy_decision="allow",
        status=ResearchActionStatus.PROPOSED.value,
        revision=1,
    )
    run = SimpleNamespace(id=uuid4(), status="waiting_for_approval", last_error="old")
    task = SimpleNamespace(id=uuid4(), status=ResearchTaskStatus.ACTIVE.value)
    monkeypatch.setattr(
        ResearchWaitEvent, "find_by", AsyncMock(return_value=event)
    )
    emit = AsyncMock()
    monkeypatch.setattr(research_runtime, "emit_research_event", emit)

    result = asyncio.run(
        activate_wait_event_action(
            SimpleNamespace(),
            task=task,
            run=run,
            action=action,
            actor_user_id=uuid4(),
        )
    )

    assert result is event
    assert action.status == ResearchActionStatus.WAITING.value
    assert run.status == ResearchRunStatus.WAITING_FOR_EVENT.value
    assert run.last_error is None
    emit.assert_awaited_once()
