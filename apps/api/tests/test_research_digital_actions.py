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
from app.models.research import ResearchRunStatus
from app.services.research_tools import (
    get_research_tool,
    research_tool_catalog,
    validate_tool_arguments,
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
