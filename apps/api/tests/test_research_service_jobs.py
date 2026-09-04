import asyncio
from datetime import UTC, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from app.main import app
from app.models.research_execution import (
    ResearchServiceCustodyEvent,
    ResearchServiceJob,
    ResearchServiceJobStatus,
    ResearchServiceQuote,
    ResearchServiceResultAsset,
)
from app.routers import research_service_jobs as service_jobs_router
from app.routers.research_service_jobs import (
    ServiceCustodyDraft,
    ServiceProgressCreate,
    ServiceQuoteDraft,
    ServiceResultCreate,
    ServiceResultDraft,
    _custody_command,
    _progress_command,
    _result_command,
)
from app.services import research_external_services, research_runtime
from app.services.research_external_services import (
    request_service_order_approval,
    service_order_command,
)
from app.services.research_runtime import canonical_digest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def test_external_service_job_models_are_typed_and_append_only():
    job_ddl = compile_table(ResearchServiceJob)
    quote_ddl = compile_table(ResearchServiceQuote)
    custody_ddl = compile_table(ResearchServiceCustodyEvent)
    asset_ddl = compile_table(ResearchServiceResultAsset)

    assert "ck_research_service_job_status" in job_ddl
    assert "'blocked'" in job_ddl
    assert "creation_digest" in job_ddl
    assert "uq_research_service_quote_revision" in quote_ddl
    assert "quote_digest" in quote_ddl
    assert "uq_research_service_custody_sequence" in custody_ddl
    assert "event_digest" in custody_ddl
    assert "uq_research_service_result_asset" in asset_ddl


def test_external_service_job_migration_follows_catalog():
    migration = import_module("migrations.versions.0029_research_service_jobs")

    assert migration.down_revision == "0028_research_service_catalog"
    assert migration.TABLE_NAMES == (
        "research_service_jobs",
        "research_service_quotes",
        "research_service_custody_events",
        "research_service_result_assets",
    )

    graph_migration = import_module(
        "migrations.versions.0041_research_service_graph_state"
    )
    assert graph_migration.down_revision == "0040_research_autonomy_policy"
    assert graph_migration.NEW_STATUSES[0] == "blocked"


def test_service_graph_state_migration_replaces_constraint_and_cancels_on_downgrade(
    monkeypatch,
):
    migration = import_module("migrations.versions.0041_research_service_graph_state")
    calls: list[tuple[str, object]] = []

    class Inspector:
        def get_check_constraints(self, _table: str):
            return [{"name": migration.CONSTRAINT_NAME}]

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: Inspector())
    monkeypatch.setattr(
        migration.op,
        "drop_constraint",
        lambda name, *_args, **_kwargs: calls.append(("drop", name)),
    )
    monkeypatch.setattr(
        migration.op,
        "create_check_constraint",
        lambda name, _table, expression: calls.append(("create", expression)),
    )
    monkeypatch.setattr(
        migration.op,
        "execute",
        lambda statement: calls.append(("execute", str(statement))),
    )

    migration.upgrade()
    assert calls[0] == ("drop", migration.CONSTRAINT_NAME)
    assert calls[1][0] == "create"
    assert "'blocked'" in str(calls[1][1])

    calls.clear()
    migration.downgrade()
    assert calls[0][0] == "execute"
    assert "status = 'cancelled'" in str(calls[0][1])
    assert calls[1] == ("drop", migration.CONSTRAINT_NAME)
    assert "'blocked'" not in str(calls[2][1])


def test_quote_normalizes_currency_and_rejects_expired_validity():
    draft = ServiceQuoteDraft(
        expected_revision=1,
        amount="1250.00",
        currency="usd",
        valid_until=datetime.now(UTC) + timedelta(days=7),
    )

    assert draft.currency == "USD"
    with pytest.raises(ValidationError, match="end in the future"):
        ServiceQuoteDraft(
            expected_revision=1,
            amount="1250.00",
            currency="USD",
            valid_until=datetime.now(UTC) - timedelta(seconds=1),
        )


def test_custody_event_rejects_future_time_and_result_assets_are_unique():
    common = {
        "expected_revision": 2,
        "kind": "released_to_carrier",
        "resource_id": uuid4(),
        "from_party": "Lab",
        "to_party": "Provider",
        "occurred_at": datetime.now(UTC),
    }
    custody = ServiceCustodyDraft(**common)
    assert custody.from_party == "Lab"

    with pytest.raises(ValidationError, match="cannot be in the future"):
        ServiceCustodyDraft(
            **{**common, "occurred_at": datetime.now(UTC) + timedelta(hours=1)}
        )

    version_id = uuid4()
    with pytest.raises(ValidationError, match="contain duplicates"):
        ServiceResultDraft(
            expected_revision=2,
            result={},
            data_asset_version_ids=[version_id, version_id],
        )


def test_order_and_custody_commands_bind_exact_versions_and_state():
    quote = SimpleNamespace(
        id=uuid4(),
        revision=3,
        quote_digest="a" * 64,
        amount="1250",
        currency="USD",
        valid_until=None,
    )
    job = SimpleNamespace(
        id=uuid4(),
        revision=4,
        provider_id=uuid4(),
        service_offering_id=uuid4(),
        service_offering_revision_id=uuid4(),
        service_version="2026.1",
        request_payload={"sample_count": 4},
    )
    approval = service_order_command(job, quote)
    assert approval["quote_revision"] == 3
    assert approval["service_offering_revision_id"] == str(
        job.service_offering_revision_id
    )

    custody = ServiceCustodyDraft(
        expected_revision=4,
        kind="released_to_carrier",
        resource_id=uuid4(),
        from_party="Airalogy Lab",
        to_party="Sequencing Provider",
        occurred_at=datetime.now(UTC),
    )
    command = _custody_command(job, 2, custody)
    assert command["sequence"] == 2
    assert len(canonical_digest(command)) == 64


def test_manual_and_aira_service_orders_share_the_same_approval_gate(monkeypatch):
    added = []
    db_session = SimpleNamespace(
        add=added.append,
        flush=AsyncMock(),
    )
    task = SimpleNamespace(id=uuid4(), owner_user_id=uuid4(), revision=7)
    run = SimpleNamespace(id=uuid4(), status="waiting_for_event", last_error="old")
    action = SimpleNamespace(
        id=uuid4(),
        preview_digest="a" * 64,
        status="waiting",
        policy_decision="allow",
        revision=2,
    )
    job = SimpleNamespace(
        id=uuid4(),
        revision=4,
        status="awaiting_quote",
        current_quote_revision=None,
        provider_id=uuid4(),
        service_offering_id=uuid4(),
        service_offering_revision_id=uuid4(),
        service_version="2026.1",
        request_payload={"sample_count": 4},
    )
    quote = SimpleNamespace(
        id=uuid4(),
        revision=3,
        quote_digest="b" * 64,
        amount="1250",
        currency="USD",
        valid_until=None,
    )
    event = AsyncMock()
    monkeypatch.setattr(research_external_services, "emit_research_event", event)

    approval = asyncio.run(
        request_service_order_approval(
            db_session,
            task=task,
            run=run,
            action=action,
            job=job,
            quote=quote,
            requested_by_user_id=uuid4(),
            actor_user_id=None,
            reason="Approve Aira service order",
        )
    )

    assert approval in added
    assert approval.preview_digest == action.preview_digest
    assert approval.reason == "Approve Aira service order"
    assert job.status == "awaiting_approval"
    assert job.current_quote_revision == 3
    assert job.revision == 5
    assert action.status == "proposed"
    assert action.policy_decision == "ask"
    assert action.revision == 3
    assert run.status == "waiting_for_approval"
    assert run.last_error is None
    assert task.revision == 8
    event.assert_awaited_once()


def test_aira_service_graph_revalidates_before_requesting_quote(monkeypatch):
    provider_id = uuid4()
    offering_id = uuid4()
    revision_id = uuid4()
    requester_id = uuid4()
    pinned = {
        "source_id": str(offering_id),
        "source_revision_id": str(revision_id),
        "version": "2026.1",
        "name": "RNA sequencing",
        "metadata": {
            "provider": {"id": str(provider_id), "name": "Core Facility"},
            "offering_revision": 3,
        },
    }
    revision = SimpleNamespace(
        id=revision_id,
        revision=3,
        service_version="2026.1",
        input_schema={
            "type": "object",
            "required": ["sample_count"],
            "properties": {"sample_count": {"type": "integer", "minimum": 1}},
        },
        result_schema={"type": "object"},
        risk="medium",
        quote_required=True,
    )
    job = SimpleNamespace(
        id=uuid4(),
        action_id=uuid4(),
        provider_id=provider_id,
        service_offering_id=offering_id,
        service_offering_revision_id=revision_id,
        service_offering_revision=3,
        service_version="2026.1",
        provider_snapshot=pinned["metadata"]["provider"],
        offering_snapshot=pinned,
        request_payload={"sample_count": 4},
        input_schema=revision.input_schema,
        result_schema=revision.result_schema,
        risk="medium",
        quote_required=True,
        status=ResearchServiceJobStatus.BLOCKED.value,
        revision=1,
        quote_requested_at=None,
    )
    action = SimpleNamespace(
        id=job.action_id,
        input_data={"action_graph": {"id": "aira-action-graph:3:service"}},
        status="proposed",
        policy_decision="ask",
        revision=2,
    )
    task = SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        status="active",
        revision=5,
    )
    run = SimpleNamespace(
        id=uuid4(),
        requested_by_user_id=requester_id,
        status="running",
    )
    provider = SimpleNamespace(id=provider_id)
    offering = SimpleNamespace(id=offering_id)
    db_session = AsyncMock()
    db_session.scalars.return_value = SimpleNamespace(first=lambda: job)
    db_session.get.side_effect = [SimpleNamespace(), SimpleNamespace(id=requester_id)]
    db_session.add = Mock()
    event = AsyncMock()
    monkeypatch.setattr(
        research_external_services,
        "pinned_service_job_context",
        AsyncMock(return_value=(pinned, provider, offering, revision)),
    )
    monkeypatch.setattr(
        research_runtime,
        "has_research_capability",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(research_runtime, "emit_research_event", event)

    result = asyncio.run(
        research_runtime._activate_aira_service_request(
            db_session,
            task=task,
            run=run,
            action=action,
        )
    )

    assert result is job
    assert job.status == ResearchServiceJobStatus.AWAITING_QUOTE.value
    assert job.quote_requested_at is not None
    assert job.revision == 2
    assert action.status == "waiting"
    assert action.policy_decision == "allow"
    assert run.status == "waiting_for_event"
    assert task.revision == 6
    db_session.add.assert_not_called()
    event.assert_awaited_once()
    assert event.await_args.kwargs["payload"]["source"] == "aira_action_graph"


def test_service_failure_waits_for_the_governed_graph_before_replanning(monkeypatch):
    job = SimpleNamespace(
        id=uuid4(),
        status=ResearchServiceJobStatus.ORDERED.value,
        revision=2,
        external_order_ref="",
        provider_status="",
        expected_completion_at=None,
        error=None,
        completed_at=None,
    )
    action = SimpleNamespace(
        id=uuid4(),
        status="waiting",
        error=None,
        completed_at=None,
        revision=1,
    )
    run = SimpleNamespace(id=uuid4(), status="waiting_for_event", aira_state={})
    task = SimpleNamespace(id=uuid4(), status="active", revision=4)
    user = SimpleNamespace(id=uuid4())
    draft = ServiceProgressCreate(
        expected_revision=2,
        status="failed",
        reason="Provider rejected the samples",
        preview_digest="0" * 64,
    )
    params = draft.model_copy(
        update={"preview_digest": canonical_digest(_progress_command(job, draft))}
    )
    db_session = AsyncMock()
    barrier = AsyncMock(return_value=False)
    enqueue = AsyncMock()
    monkeypatch.setattr(
        service_jobs_router,
        "_job_context",
        AsyncMock(
            return_value=(job, action, run, task, SimpleNamespace(), SimpleNamespace())
        ),
    )
    monkeypatch.setattr(
        service_jobs_router,
        "release_service_budget",
        AsyncMock(),
    )
    monkeypatch.setattr(
        service_jobs_router,
        "hold_or_release_aira_action_group",
        barrier,
    )
    monkeypatch.setattr(
        service_jobs_router,
        "enqueue_research_advance",
        enqueue,
    )
    monkeypatch.setattr(service_jobs_router, "emit_research_event", AsyncMock())
    monkeypatch.setattr(
        service_jobs_router,
        "service_job_snapshot",
        AsyncMock(return_value={"status": "failed"}),
    )

    result = asyncio.run(
        service_jobs_router.create_service_progress(
            job.id,
            params,
            user,
            db_session,
        )
    )

    assert result == {"status": "failed"}
    assert action.status == "failed"
    assert run.aira_state["service_results"][0]["status"] == "failed"
    barrier.assert_awaited_once()
    enqueue.assert_not_awaited()


def test_service_result_waits_for_the_governed_graph_before_replanning(monkeypatch):
    job = SimpleNamespace(
        id=uuid4(),
        status=ResearchServiceJobStatus.IN_FULFILLMENT.value,
        revision=3,
        result_schema={"type": "object"},
        result={},
        actual_amount=None,
        completed_at=None,
        offering_snapshot={"name": "RNA sequencing"},
    )
    action = SimpleNamespace(
        id=uuid4(),
        status="waiting",
        output_data={},
        completed_at=None,
        revision=1,
    )
    run = SimpleNamespace(id=uuid4(), status="waiting_for_event", aira_state={})
    task = SimpleNamespace(id=uuid4(), status="active", revision=6)
    user = SimpleNamespace(id=uuid4())
    quote = SimpleNamespace(
        id=uuid4(),
        revision=1,
        amount="1250.00",
        currency="USD",
    )
    draft = ServiceResultCreate(
        expected_revision=3,
        result={"read_count": 1200},
        preview_digest="0" * 64,
    )
    params = draft.model_copy(
        update={"preview_digest": canonical_digest(_result_command(job, quote, draft))}
    )
    db_session = AsyncMock()
    db_session.add = Mock()
    barrier = AsyncMock(return_value=False)
    enqueue = AsyncMock()
    monkeypatch.setattr(
        service_jobs_router,
        "_job_context",
        AsyncMock(
            return_value=(job, action, run, task, SimpleNamespace(), SimpleNamespace())
        ),
    )
    monkeypatch.setattr(
        service_jobs_router,
        "latest_service_quote",
        AsyncMock(return_value=quote),
    )
    monkeypatch.setattr(
        service_jobs_router,
        "_result_asset_versions",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        service_jobs_router,
        "settle_service_budget",
        AsyncMock(),
    )
    monkeypatch.setattr(
        service_jobs_router,
        "hold_or_release_aira_action_group",
        barrier,
    )
    monkeypatch.setattr(
        service_jobs_router,
        "enqueue_research_advance",
        enqueue,
    )
    monkeypatch.setattr(service_jobs_router, "emit_research_event", AsyncMock())
    monkeypatch.setattr(
        service_jobs_router,
        "service_job_snapshot",
        AsyncMock(return_value={"status": "completed"}),
    )

    result = asyncio.run(
        service_jobs_router.create_service_result(
            job.id,
            params,
            user,
            db_session,
        )
    )

    assert result == {"status": "completed"}
    assert action.status == "completed"
    assert run.aira_state["service_results"][0]["status"] == "completed"
    barrier.assert_awaited_once()
    enqueue.assert_not_awaited()


def test_external_service_job_routes_are_registered():
    paths = {route.path for route in app.routes}

    assert "/research-tasks/{task_id}/service-actions/preview" in paths
    assert "/research-service-jobs/{job_id}/quotes/preview" in paths
    assert "/research-service-jobs/{job_id}/custody/preview" in paths
    assert "/research-service-jobs/{job_id}/result/preview" in paths
