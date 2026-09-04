import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.main import app
from app.models.research_execution import (
    ResearchInstrumentCommand,
    ResearchInstrumentGateway,
    ResearchInstrumentGatewayAudit,
    ResearchInstrumentJob,
)
from app.routers.research_instrument_gateways import InstrumentCommandDraft
from app.services.research_capabilities import instrument_command_capability
from app.services.research_instruments import (
    activate_aira_instrument_action,
    available_instrument_command_options,
    gateway_snapshot,
    gateway_token_digest,
    generate_gateway_token,
    generate_job_lease_token,
    instrument_job_snapshot,
    job_lease_token_digest,
    normalized_safety_contract,
    reconcile_expired_instrument_leases,
    sign_job_envelope,
    validate_bounded_schema,
    validate_safety_attestation,
    validate_schema_payload,
)


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def object_schema() -> dict:
    return {
        "type": "object",
        "properties": {"temperature": {"type": "number"}},
        "required": ["temperature"],
        "additionalProperties": False,
    }


def test_instrument_gateway_tables_keep_credentials_out_of_public_models():
    gateway_ddl = compile_table(ResearchInstrumentGateway)
    command_ddl = compile_table(ResearchInstrumentCommand)
    audit_ddl = compile_table(ResearchInstrumentGatewayAudit)

    assert "token_digest VARCHAR(64) NOT NULL" in gateway_ddl
    assert "UNIQUE (token_digest)" in gateway_ddl
    assert "uq_research_instrument_command_identity" in command_ddl
    assert "device_confirmation_required" in command_ddl
    assert "safety_contract JSON" in command_ddl
    assert "resource_revision_id" in command_ddl
    assert "snapshot JSON" in audit_ddl

    gateway = ResearchInstrumentGateway(
        id=uuid4(),
        lab_id=uuid4(),
        name="Microscope room gateway",
        description="Local adapter",
        token_digest="a" * 64,
        token_hint="12345678",
        enabled=True,
        revision=1,
        created_by_user_id=uuid4(),
        updated_by_user_id=uuid4(),
    )
    assert "token_digest" not in gateway.as_dict()
    assert "token_digest" not in gateway_snapshot(gateway)


def test_instrument_gateway_migration_follows_notifications():
    migration = import_module("migrations.versions.0026_research_instrument_gateways")

    assert migration.down_revision == "0025_research_notifications"
    assert migration.TABLE_NAMES == (
        "research_instrument_gateways",
        "research_instrument_commands",
        "research_instrument_gateway_audits",
    )


def test_gateway_credentials_are_high_entropy_and_only_stored_as_digest():
    first = generate_gateway_token()
    second = generate_gateway_token()

    assert first.startswith("aigw_")
    assert len(first) > 40
    assert first != second
    assert len(gateway_token_digest(first)) == 64
    assert first not in gateway_token_digest(first)


def test_instrument_command_contract_is_schema_bounded_and_fail_closed():
    command = InstrumentCommandDraft(
        gateway_id=uuid4(),
        resource_id=uuid4(),
        command_key="incubator.set-temperature",
        command_version="1",
        name="Set incubator temperature",
        input_schema=object_schema(),
        output_schema={
            "type": "object",
            "properties": {"accepted": {"type": "boolean"}},
            "required": ["accepted"],
            "additionalProperties": False,
        },
        risk="high",
        device_confirmation_required=True,
        safety_contract={
            "required_interlocks": ["door.closed", "temperature.safe"],
            "operator_presence_required": True,
            "emergency_stop_required": True,
        },
    )
    assert command.command_key == "incubator.set-temperature"
    assert command.safety_contract["required_interlocks"] == [
        "door.closed",
        "temperature.safe",
    ]

    with pytest.raises(ValidationError, match="device-side confirmation"):
        InstrumentCommandDraft(
            gateway_id=uuid4(),
            resource_id=uuid4(),
            command_key="incubator.set-temperature",
            command_version="1",
            name="Set incubator temperature",
            input_schema=object_schema(),
            output_schema=object_schema(),
            risk="high",
            device_confirmation_required=False,
        )

    with pytest.raises(ValidationError, match="operator presence"):
        InstrumentCommandDraft(
            gateway_id=uuid4(),
            resource_id=uuid4(),
            command_key="incubator.set-temperature",
            command_version="1",
            name="Set incubator temperature",
            input_schema=object_schema(),
            output_schema=object_schema(),
            risk="high",
            device_confirmation_required=True,
        )

    with pytest.raises(ValueError, match="remote references"):
        validate_bounded_schema(
            {
                "type": "object",
                "properties": {
                    "payload": {"$ref": "https://example.org/unsafe-schema.json"}
                },
            },
            "input",
        )

    with pytest.raises(ValueError, match="must describe an object"):
        validate_bounded_schema({"type": "string"}, "input")


def test_instrument_gateway_management_routes_are_registered():
    routes = {
        (route.path, tuple(sorted(route.methods or [])))
        for route in app.routes
        if route.path.startswith("/research-instrument-gateways")
    }

    assert ("/research-instrument-gateways", ("GET",)) in routes
    assert ("/research-instrument-gateways", ("POST",)) in routes
    assert ("/research-instrument-gateways/commands", ("POST",)) in routes
    assert (
        "/research-instrument-gateways/{gateway_id}/rotate",
        ("POST",),
    ) in routes


def test_instrument_command_projects_an_exact_gateway_executor_capability():
    gateway_id = uuid4()
    resource_id = uuid4()
    revision_id = uuid4()
    command = SimpleNamespace(
        id=uuid4(),
        lab_id=uuid4(),
        gateway_id=gateway_id,
        resource_id=resource_id,
        resource_revision_id=revision_id,
        resource_revision=2,
        command_key="microscope.capture",
        command_version="1.2",
        name="Capture microscope image",
        description="Acquire one bounded image",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        risk="medium",
        device_confirmation_required=True,
        timeout_seconds=300,
        enabled=True,
        revision=4,
        archived_at=None,
    )
    gateway = SimpleNamespace(
        id=gateway_id,
        name="Microscopy Gateway",
        enabled=True,
        revoked_at=None,
        revision=3,
    )
    resource = SimpleNamespace(
        id=resource_id,
        resource_type_id=uuid4(),
        name="Microscope A",
        code="scope-a",
        current_revision_id=revision_id,
        status="active",
        archived_at=None,
    )

    capability = instrument_command_capability(command, gateway, resource).payload()

    assert capability["key"] == f"instrument:{command.id}"
    assert capability["version"] == "4"
    assert capability["executor_types"] == ["instrument_gateway"]
    assert capability["metadata"]["gateway_id"] == str(gateway_id)
    assert capability["metadata"]["command_version"] == "1.2"


def test_instrument_jobs_pin_contracts_and_hide_lease_credentials():
    ddl = compile_table(ResearchInstrumentJob)

    assert "UNIQUE (action_id)" in ddl
    assert "lease_token_digest VARCHAR(64)" in ddl
    assert "equipment_booking_id" in ddl
    assert "command_revision" in ddl
    assert "output_schema JSON" in ddl
    assert "safety_contract JSON" in ddl
    assert "safety_attestation JSON" in ddl
    assert "ck_research_instrument_job_status" in ddl

    job = ResearchInstrumentJob(
        id=uuid4(),
        action_id=uuid4(),
        gateway_id=uuid4(),
        command_id=uuid4(),
        resource_id=uuid4(),
        resource_revision_id=uuid4(),
        resource_revision=2,
        equipment_booking_id=uuid4(),
        command_key="incubator.set-temperature",
        command_version="1",
        command_revision=3,
        arguments={"temperature": 37},
        input_schema=object_schema(),
        output_schema=object_schema(),
        risk="high",
        device_confirmation_required=True,
        timeout_seconds=300,
        status="leased",
        lease_token_digest="b" * 64,
        attempt_count=1,
        revision=2,
    )
    assert "lease_token_digest" not in job.as_dict()
    assert "lease_token_digest" not in instrument_job_snapshot(job)


def test_instrument_safety_attestation_requires_every_pinned_interlock():
    contract = normalized_safety_contract(
        {
            "required_interlocks": ["lid.closed", "temperature.safe"],
            "operator_presence_required": True,
            "emergency_stop_required": True,
        }
    )
    attestation = validate_safety_attestation(
        contract,
        {
            "interlocks": {"lid.closed": True, "temperature.safe": True},
            "operator_present": True,
            "emergency_stop_available": True,
            "reference": "device-panel:preflight-42",
        },
    )

    assert attestation["reference"] == "device-panel:preflight-42"
    with pytest.raises(ValueError, match="temperature.safe"):
        validate_safety_attestation(
            contract,
            {
                "interlocks": {"lid.closed": True, "temperature.safe": False},
                "operator_present": True,
                "emergency_stop_available": True,
                "reference": "device-panel:preflight-43",
            },
        )


def test_instrument_safety_migration_follows_sample_lineage():
    migration = import_module("migrations.versions.0045_instrument_safety_interlocks")

    assert migration.down_revision == "0044_sample_lineage_semantics"
    source = inspect.getsource(migration.upgrade)
    assert "WHERE risk = 'high'" in source
    assert "status IN ('queued', 'leased')" in source
    assert "operator_presence_required" in source
    assert "emergency_stop_required" in source


def test_instrument_job_migration_follows_gateway_configuration():
    migration = import_module("migrations.versions.0027_research_instrument_jobs")

    assert migration.down_revision == "0026_research_instrument_gateways"
    assert migration.TABLE_NAMES == ("research_instrument_jobs",)


def test_instrument_job_lease_and_payload_contracts_fail_closed():
    lease = generate_job_lease_token()
    gateway_digest = gateway_token_digest(generate_gateway_token())
    envelope = {
        "schema": "airalogy.instrument-job.v1",
        "job_id": str(uuid4()),
        "command": {
            "key": "incubator.set-temperature",
            "arguments": {"temperature": 37},
        },
    }

    assert lease.startswith("aijl_")
    assert len(job_lease_token_digest(lease)) == 64
    assert lease not in job_lease_token_digest(lease)
    assert sign_job_envelope(envelope, gateway_digest) == sign_job_envelope(
        envelope, gateway_digest
    )
    assert len(sign_job_envelope(envelope, gateway_digest)) == 64
    assert validate_schema_payload(object_schema(), {"temperature": 37}, "input") == {
        "temperature": 37
    }
    with pytest.raises(ValueError, match="Invalid input at temperature"):
        validate_schema_payload(object_schema(), {"temperature": "hot"}, "input")


def test_instrument_job_runtime_routes_are_registered():
    paths = app.openapi()["paths"]

    assert "/research-instrument-commands" in paths
    assert "/research-tasks/{task_id}/instrument-actions/preview" in paths
    assert "/research-tasks/{task_id}/instrument-actions" in paths
    assert "/research-instrument-jobs/{job_id}/stop/preview" in paths
    assert "/instrument-gateway/v1/jobs/lease" in paths
    assert "/instrument-gateway/v1/jobs/{job_id}/start" in paths
    assert "/instrument-gateway/v1/jobs/{job_id}/heartbeat" in paths
    assert "/instrument-gateway/v1/jobs/{job_id}/complete" in paths
    assert "/instrument-gateway/v1/jobs/{job_id}/fail" in paths
    assert "/instrument-gateway/v1/jobs/{job_id}/stopped" in paths


def test_expired_instrument_leases_recover_only_undelivered_work(monkeypatch):
    now = datetime.now(UTC)
    leased = SimpleNamespace(
        id=uuid4(),
        action_id=uuid4(),
        status="leased",
        lease_token_digest="a" * 64,
        lease_expires_at=now - timedelta(seconds=1),
        revision=2,
        attempt_count=1,
    )
    running = SimpleNamespace(
        id=uuid4(),
        action_id=uuid4(),
        status="running",
        lease_token_digest="b" * 64,
        lease_expires_at=now - timedelta(seconds=1),
        revision=4,
        attempt_count=1,
        stop_reason=None,
        stop_requested_at=None,
    )
    leased_action = SimpleNamespace(
        id=leased.action_id, run_id=uuid4(), status="queued", error=None, revision=1
    )
    running_action = SimpleNamespace(
        id=running.action_id,
        run_id=uuid4(),
        status="running",
        error=None,
        revision=2,
    )
    leased_run = SimpleNamespace(
        id=leased_action.run_id,
        task_id=uuid4(),
        status="waiting_for_instrument",
        last_error=None,
    )
    running_run = SimpleNamespace(
        id=running_action.run_id,
        task_id=uuid4(),
        status="waiting_for_instrument",
        last_error=None,
    )
    leased_task = SimpleNamespace(id=leased_run.task_id, status="active", revision=1)
    running_task = SimpleNamespace(id=running_run.task_id, status="active", revision=1)
    values = {
        leased.action_id: leased_action,
        running.action_id: running_action,
        leased_action.run_id: leased_run,
        running_action.run_id: running_run,
        leased_run.task_id: leased_task,
        running_run.task_id: running_task,
    }

    async def get_model(_model, item_id):
        return values[item_id]

    db_session = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [leased, running])),
        get=AsyncMock(side_effect=get_model),
    )
    emit = AsyncMock()
    from app.services import research_runtime

    monkeypatch.setattr(research_runtime, "emit_research_event", emit)

    result = asyncio.run(reconcile_expired_instrument_leases(db_session))

    assert result == {"recovered": 1, "stop_requested": 1}
    assert leased.status == "queued"
    assert leased.lease_token_digest is None
    assert leased_run.status == "waiting_for_instrument"
    assert running.status == "stop_requested"
    assert running_action.status == "waiting"
    assert running_run.status == "paused"
    assert running_task.status == "paused"
    assert emit.await_count == 2


def test_aira_instrument_activation_rechecks_pins_and_approved_booking(monkeypatch):
    from app.services import research_instruments

    gateway_id = uuid4()
    command_id = uuid4()
    resource_id = uuid4()
    resource_revision_id = uuid4()
    booking_id = uuid4()
    job = SimpleNamespace(
        id=uuid4(),
        action_id=uuid4(),
        gateway_id=gateway_id,
        command_id=command_id,
        resource_id=resource_id,
        resource_revision_id=resource_revision_id,
        resource_revision=4,
        equipment_booking_id=booking_id,
        command_key="incubator.set-temperature",
        command_version="1",
        command_revision=3,
        arguments={"temperature": 37},
        input_schema=object_schema(),
        output_schema={"type": "object", "additionalProperties": True},
        risk="high",
        device_confirmation_required=True,
        timeout_seconds=300,
        status="queued",
    )
    action = SimpleNamespace(
        id=job.action_id,
        status="proposed",
        error="pending",
        revision=1,
    )
    run = SimpleNamespace(
        requested_by_user_id=uuid4(),
        status="waiting_for_approval",
        last_error="pending",
        advance_generation=5,
    )
    task = SimpleNamespace(id=uuid4(), lab_id=uuid4())
    option = {
        "id": str(command_id),
        "gateway_id": str(gateway_id),
        "resource_id": str(resource_id),
        "resource_revision_id": str(resource_revision_id),
        "resource_revision": 4,
        "command_key": job.command_key,
        "command_version": job.command_version,
        "revision": 3,
        "input_schema": job.input_schema,
        "output_schema": job.output_schema,
        "risk": job.risk,
        "device_confirmation_required": True,
        "timeout_seconds": 300,
        "bookings": [{"id": str(booking_id)}],
    }
    monkeypatch.setattr(ResearchInstrumentJob, "find_by", AsyncMock(return_value=job))
    available = AsyncMock(return_value=[option])
    monkeypatch.setattr(
        research_instruments,
        "available_instrument_command_options",
        available,
    )
    locked = SimpleNamespace(first=lambda: SimpleNamespace())
    db_session = SimpleNamespace(
        scalars=AsyncMock(side_effect=[locked, locked, locked, locked] * 2),
        scalar=AsyncMock(return_value=0),
        flush=AsyncMock(),
    )

    payload = asyncio.run(
        activate_aira_instrument_action(
            db_session,
            task=task,
            run=run,
            action=action,
        )
    )

    assert payload["instrument_job_id"] == str(job.id)
    assert action.status == "queued"
    assert run.status == "waiting_for_instrument"
    assert run.advance_generation == 6
    available.assert_awaited_once()
    db_session.flush.assert_awaited_once()

    action.status = "proposed"
    run.status = "waiting_for_approval"
    option["command_version"] = "2"
    with pytest.raises(ValueError, match="changed after the approval preview"):
        asyncio.run(
            activate_aira_instrument_action(
                db_session,
                task=task,
                run=run,
                action=action,
            )
        )


def test_aira_sees_only_pinned_accessible_commands_with_unused_bookings(monkeypatch):
    from app.services import research_instruments

    lab_id = uuid4()
    user_id = uuid4()
    resource_type_id = uuid4()
    resource_id = uuid4()
    resource_revision_id = uuid4()
    gateway_id = uuid4()
    booking_id = uuid4()
    command = SimpleNamespace(
        id=uuid4(),
        gateway_id=gateway_id,
        lab_id=lab_id,
        resource_id=resource_id,
        resource_revision_id=resource_revision_id,
        resource_revision=4,
        command_key="incubator.set-temperature",
        command_version="1",
        name="Set temperature",
        description="Set an approved incubator target",
        input_schema=object_schema(),
        output_schema={"type": "object"},
        risk="high",
        device_confirmation_required=True,
        timeout_seconds=300,
        enabled=True,
        revision=3,
        archived_at=None,
    )
    gateway = SimpleNamespace(id=gateway_id, name="Incubator Gateway")
    resource = SimpleNamespace(
        id=resource_id,
        lab_id=lab_id,
        resource_type_id=resource_type_id,
        current_revision_id=resource_revision_id,
        archived_at=None,
        status="active",
        name="Incubator 01",
        code="INC-01",
    )
    revision = SimpleNamespace(id=resource_revision_id, revision=4)
    booking = SimpleNamespace(
        id=booking_id,
        as_dict=lambda: {
            "id": str(booking_id),
            "starts_at": datetime.now(UTC),
            "ends_at": datetime.now(UTC) + timedelta(hours=1),
        },
    )

    async def get_model(model, _item_id):
        return {"Resource": resource, "ResourceRevision": revision}[model.__name__]

    rows = SimpleNamespace(all=lambda: [(command, gateway)])
    bookings = SimpleNamespace(all=lambda: [booking])
    no_active_bookings = SimpleNamespace(all=list)
    db_session = SimpleNamespace(
        execute=AsyncMock(return_value=rows),
        get=AsyncMock(side_effect=get_model),
        scalars=AsyncMock(side_effect=[bookings, no_active_bookings]),
    )
    monkeypatch.setattr(
        research_instruments,
        "resolve_resource_access",
        AsyncMock(
            return_value=SimpleNamespace(
                allows=lambda capability: capability == "equipment.book"
            )
        ),
    )
    task = SimpleNamespace(lab_id=lab_id)
    run = SimpleNamespace(
        environment_snapshot={"resources": [{"source_id": str(resource_type_id)}]}
    )

    options = asyncio.run(
        available_instrument_command_options(
            db_session,
            task=task,
            run=run,
            user_id=user_id,
        )
    )

    assert options[0]["id"] == str(command.id)
    assert options[0]["bookings"][0]["id"] == str(booking_id)

    db_session.scalars = AsyncMock(
        side_effect=[bookings, SimpleNamespace(all=lambda: [booking_id])]
    )
    assert (
        asyncio.run(
            available_instrument_command_options(
                db_session,
                task=task,
                run=run,
                user_id=user_id,
            )
        )
        == []
    )


def test_terminal_gateway_callbacks_are_idempotent_and_conflict_safe(monkeypatch):
    routes = import_module("app.routers.research_instrument_jobs")
    completed = SimpleNamespace(status="completed", result={"value": 42})
    failed = SimpleNamespace(status="failed", error="device fault")
    stopped = SimpleNamespace(status="stopped", stop_reason="operator stop")
    context_tail = (
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(),
    )
    db_session = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(
        routes,
        "_authenticate_gateway",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )

    monkeypatch.setattr(
        routes,
        "_gateway_job_context",
        AsyncMock(return_value=(completed, *context_tail)),
    )
    result = asyncio.run(
        routes.complete_instrument_job(
            uuid4(),
            routes.GatewayComplete(result={"value": 42}),
            "aigw_token",
            "aijl_token",
            db_session,
        )
    )
    assert result == {"status": "completed"}
    with pytest.raises(HTTPException) as conflict:
        asyncio.run(
            routes.complete_instrument_job(
                uuid4(),
                routes.GatewayComplete(result={"value": 43}),
                "aigw_token",
                "aijl_token",
                db_session,
            )
        )
    assert conflict.value.status_code == 409

    monkeypatch.setattr(
        routes,
        "_gateway_job_context",
        AsyncMock(return_value=(failed, *context_tail)),
    )
    result = asyncio.run(
        routes.fail_instrument_job(
            uuid4(),
            routes.GatewayFail(error="device fault"),
            "aigw_token",
            "aijl_token",
            db_session,
        )
    )
    assert result == {"status": "failed"}

    monkeypatch.setattr(
        routes,
        "_gateway_job_context",
        AsyncMock(return_value=(stopped, *context_tail)),
    )
    result = asyncio.run(
        routes.acknowledge_instrument_job_stopped(
            uuid4(),
            routes.GatewayStopped(reason="operator stop"),
            "aigw_token",
            "aijl_token",
            db_session,
        )
    )
    assert result == {"status": "stopped"}
    assert db_session.commit.await_count == 3
