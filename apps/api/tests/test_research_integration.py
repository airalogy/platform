"""Real API + PostgreSQL + persistent-job acceptance, with explicit fault injection.

Run through `pnpm research:integration`, never against development data. No API
responses, authorization, ledger, or state transitions are mocked. Only external
provider latency/failure and crash state are injected where the test names say so.
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from app.config import config
from app.database import sessionmanager
from app.main import app
from app.models.lab import LabUser
from app.models.research import ResearchAction, ResearchTask
from app.models.research_asset import ResearchActionOutputSnapshot, ResearchEvidence
from app.models.research_execution import ResearchBudgetEntry, ResearchToolJob
from app.models.resource import PersistentJob
from app.services import research_tools, resource_job_worker
from app.services.persistent_jobs import (
    JobDeferred,
    claim_job,
    complete_job,
    defer_job,
    fail_job,
)
from app.services.research_action_outputs import action_output_digest
from app.services.resource_job_worker import (
    process_persistent_job,
    reconcile_exhausted_jobs,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RESEARCH_INTEGRATION_TEST") != "1",
    reason="Use pnpm research:integration with the isolated migrated PostgreSQL runtime",
)


class Runtime:
    def __init__(self, runner):
        self.runner = runner
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    def run(self, coroutine):
        return self.runner.run(coroutine)

    async def json(self, method, url, data=None, status=200):
        response = await self.client.request(method, url, json=data)
        assert response.status_code == status, (
            url,
            response.status_code,
            response.text,
        )
        return response.json()

    async def confirm(self, url, draft):
        preview = await self.json("POST", url + "/preview", draft)
        return await self.json(
            "POST", url, {**draft, "preview_digest": preview["preview_digest"]}
        )

    async def setup(self):
        assert (
            config.DATABASE_URL
            == "postgresql+asyncpg://airalogy_e2e:airalogy_e2e@127.0.0.1:55432/airalogy_e2e"
        )
        self.seed = await self.json("POST", "/dev/fixtures/quickstart")
        owner = next(a for a in self.seed["accounts"] if a["key"] == "owner")
        auth = await self.json(
            "POST",
            "/signin_by_email",
            {"email": owner["email"], "password": owner["password"]},
        )
        self.client.headers["Auth-Token"] = auth["token"]

    async def task(self, **overrides):
        task = await self.confirm(
            "/research-tasks",
            {
                "project_id": self.seed["project"]["id"],
                "title": "Runtime acceptance " + uuid4().hex,
                "goal": "Preserve evidence and execution boundaries",
                "success_criteria": ["Traceable reviewed outcome"],
                "tool_keys": ["knowledge.search"],
                **overrides,
            },
        )
        return await self.transition(task["id"], "start")

    async def transition(self, task_id, operation, **extra):
        task = await self.json("GET", f"/research-tasks/{task_id}")
        return await self.json(
            "POST",
            f"/research-tasks/{task_id}/{operation}",
            {
                "expected_revision": task["revision"],
                "reason": "Integration acceptance",
                **extra,
            },
        )

    async def tool(self, task, key="knowledge.search", arguments=None):
        return await self.confirm(
            f"/research-tasks/{task['id']}/tool-actions",
            {
                "tool_key": key,
                "arguments": arguments or {"query": "acceptance"},
                "idempotency_key": uuid4().hex,
            },
        )

    async def dispatch(self, tool):
        # Restrict the actual claim query to this fixture's job, leaving other
        # acceptance tasks' planner and notification jobs untouched.
        async with sessionmanager.session() as db:
            job = await db.scalar(
                select(PersistentJob).where(
                    PersistentJob.idempotency_key
                    == f"research-tool-job:{tool['tool_job']['id']}"
                )
            )
            claimed = await claim_job(
                db, worker_id="integration", kinds={"research_tool_job"}, job_id=job.id
            )
            assert claimed is not None
            await db.commit()
            try:
                result = await process_persistent_job(db, claimed)
                await complete_job(
                    db, job=claimed, worker_id="integration", result=result
                )
            except JobDeferred as error:
                await defer_job(
                    db, job=claimed, worker_id="integration", reason=str(error)
                )
            except Exception as error:  # noqa: BLE001 - mirror worker failure accounting for injected faults
                job_id = claimed.id
                await db.rollback()
                claimed = await db.get(PersistentJob, job_id)
                await fail_job(
                    db, job=claimed, worker_id="integration", error=str(error)
                )
                await research_tools.mark_research_tool_job_failure(
                    db,
                    tool_job_id=UUID(tool["tool_job"]["id"]),
                    error=str(error),
                    terminal=claimed.status == "failed",
                )
            await db.commit()
            return claimed.status, claimed.attempts


@pytest.fixture(scope="module")
def runtime():
    with asyncio.Runner() as runner:
        runtime = Runtime(runner)
        runtime.run(runtime.setup())
        yield runtime
        runtime.run(runtime.client.aclose())
        runtime.run(sessionmanager._engine.dispose())


def test_equipment_onboarding_real_api_pagination_and_scope(runtime):
    from tests.onboarding_acceptance import exercise_onboarding_scope

    exercise_onboarding_scope(runtime)


def test_managed_activation_real_api_and_installed_copy(runtime, tmp_path, monkeypatch):
    from tests.activation_acceptance import exercise_managed_activation

    exercise_managed_activation(runtime, tmp_path, monkeypatch)


def test_http_reader_installed_runtime_actual_api_and_lost_receipt(
    runtime, tmp_path, monkeypatch
):
    from tests.http_read_acceptance import exercise_http_reader

    exercise_http_reader(runtime, tmp_path, monkeypatch)


def test_http_controlled_reader_installed_start_readback_and_receipt_recovery(
    runtime, tmp_path, monkeypatch
):
    from tests.http_read_acceptance import exercise_http_controlled_reader

    exercise_http_controlled_reader(runtime, tmp_path, monkeypatch)


def test_source_authoring_real_api_local_resume_and_private_permissions(
    runtime, tmp_path, monkeypatch
):
    from tests.authoring_acceptance import exercise_authoring

    exercise_authoring(runtime, tmp_path, monkeypatch)


def test_controlled_source_authoring_real_api_consent_and_no_execution(
    runtime, tmp_path, monkeypatch
):
    from tests.authoring_acceptance import exercise_authoring

    exercise_authoring(runtime, tmp_path, monkeypatch, controlled=True)


def test_export_reader_installed_runtime_actual_intake_and_lost_receipt(
    runtime, tmp_path, monkeypatch
):
    from tests.http_read_acceptance import exercise_export_reader

    exercise_export_reader(runtime, tmp_path, monkeypatch)


def test_interface_exploration_real_api_browser_and_scope(
    runtime, tmp_path, monkeypatch
):
    from tests.exploration_acceptance import exercise_exploration

    exercise_exploration(runtime, tmp_path, monkeypatch)


@pytest.mark.skipif(
    os.environ.get("RUN_INTERFACE_NATIVE_TESTS") != "1",
    reason="Requires an explicitly authorized graphical macOS session",
)
def test_interface_exploration_real_api_native_and_scope(
    runtime, tmp_path, monkeypatch
):
    from tests.exploration_acceptance import exercise_exploration

    exercise_exploration(runtime, tmp_path, monkeypatch, native=True)


def test_interface_survey_real_browser_api_and_readonly_draft(
    runtime, tmp_path, monkeypatch
):
    from tests.survey_acceptance import exercise_survey

    exercise_survey(runtime, tmp_path, monkeypatch)


def test_application_selection_private_metadata_api_and_current_identity(
    runtime, tmp_path, monkeypatch
):
    from tests.application_selection_acceptance import exercise_application_selection

    exercise_application_selection(runtime, tmp_path, monkeypatch)


@pytest.mark.skipif(
    os.environ.get("RUN_INTERFACE_NATIVE_TESTS") != "1",
    reason="Requires an explicitly authorized graphical macOS session",
)
def test_interface_survey_real_native_api_and_readonly_draft(
    runtime, tmp_path, monkeypatch
):
    from tests.survey_acceptance import exercise_survey

    exercise_survey(runtime, tmp_path, monkeypatch, native=True)


@pytest.mark.parametrize("cancel_before_finalize", [False, True])
def test_file_declaring_activation_waits_for_scoped_intake(
    runtime, tmp_path, monkeypatch, cancel_before_finalize
):
    from tests.activation_acceptance import exercise_managed_activation

    exercise_managed_activation(
        runtime,
        tmp_path,
        monkeypatch,
        file_outputs=True,
        cancel_before_finalize=cancel_before_finalize,
    )


def test_sdk_file_delivery_recovers_against_real_scoped_api(
    runtime, tmp_path, monkeypatch
):
    from tests.activation_acceptance import exercise_managed_activation

    exercise_managed_activation(
        runtime, tmp_path, monkeypatch, file_outputs=True, sdk_delivery=True
    )


def test_instrument_uncertain_stop_holds_equipment_across_gateways(runtime):
    """Inject persisted synthetic jobs, then exercise real API/locking/recovery."""
    from app.models.research import ResearchRun
    from app.models.research_execution import (
        ResearchInstrumentCommand,
        ResearchInstrumentJob,
    )
    from app.models.resource import EquipmentBooking, Resource, ResourceRevision

    async def exercise():
        base = f"/labs/{runtime.seed['lab']['id']}/resource-library"
        definitions = await runtime.json("GET", base + "/definition-versions")
        definition = next(
            item
            for item in definitions["items"]
            if item["protocol_uid"] == "plasmid_resource_definition_en"
        )
        resource_type = await runtime.json(
            "POST",
            base + "/types",
            {
                "protocol_version_id": definition["id"],
                "code": "safety_" + uuid4().hex,
                "name": "Synthetic safety fixture",
                "capabilities": {"booking": True},
                "booking_policy": "approval",
            },
        )
        resource = await runtime.json(
            "POST",
            base + "/resources",
            {
                "resource_type_id": resource_type["id"],
                "name": "Synthetic equipment",
                "code": "SAFE-" + uuid4().hex,
                "visibility": "lab",
                "data": {
                    "construct_name": "Synthetic",
                    "features": [],
                    **dict.fromkeys(
                        [
                            "aliases",
                            "backbone",
                            "sequence",
                            "sequence_file",
                            "resistance_markers",
                            "host_species",
                            "copy_number",
                            "external_source",
                        ]
                    ),
                },
            },
        )
        stations, jobs = [], []
        for station_index in range(2):
            station = await runtime.confirm(
                "/research-instrument-gateways",
                {
                    "lab_id": runtime.seed["lab"]["id"],
                    "name": "Safety " + uuid4().hex,
                    "enabled": True,
                },
            )
            stations.append(station)
            task_json = await runtime.task()
            async with sessionmanager.session() as db:
                task = await db.get(ResearchTask, UUID(task_json["id"]))
                run = await db.scalar(
                    select(ResearchRun).where(ResearchRun.task_id == task.id)
                )
                run.status = "waiting_for_instrument"
                task.status = "active"
                equipment = await db.get(Resource, UUID(resource["id"]))
                equipment_revision = await db.get(
                    ResourceRevision, equipment.current_revision_id
                )
                pins = {
                    "resource_id": equipment.id,
                    "resource_revision_id": equipment.current_revision_id,
                    "resource_revision": equipment_revision.revision,
                }
                booking = EquipmentBooking(
                    lab_id=task.lab_id,
                    resource_id=equipment.id,
                    user_id=task.created_by_user_id,
                    starts_at=datetime.now(UTC)
                    + timedelta(minutes=station_index * 120 - 1),
                    ends_at=datetime.now(UTC) + timedelta(hours=1 + station_index * 2),
                    status="approved" if station_index == 0 else "pending",
                    approval_policy="approval",
                    idempotency_key=uuid4().hex,
                )
                command = ResearchInstrumentCommand(
                    gateway_id=UUID(station["gateway"]["id"]),
                    lab_id=task.lab_id,
                    **pins,
                    command_key="synthetic.read",
                    command_version="1.0.0",
                    name="Synthetic read",
                    risk="read_only",
                    device_confirmation_required=False,
                    created_by_user_id=task.created_by_user_id,
                    updated_by_user_id=task.created_by_user_id,
                )
                action = ResearchAction(
                    run_id=run.id,
                    sequence=900,
                    plan_version=1,
                    kind="instrument",
                    status="queued",
                    title="Synthetic safety acceptance",
                    executor_type="instrument_gateway",
                    preview_digest="a" * 64,
                    idempotency_key=uuid4().hex,
                )
                db.add_all([booking, command, action])
                await db.flush()
                job = ResearchInstrumentJob(
                    action_id=action.id,
                    gateway_id=command.gateway_id,
                    command_id=command.id,
                    equipment_booking_id=booking.id,
                    **pins,
                    command_key=command.command_key,
                    command_version=command.command_version,
                    command_revision=1,
                    risk="read_only",
                    device_confirmation_required=False,
                    timeout_seconds=60,
                )
                db.add(job)
                await db.flush()
                jobs.append(str(job.id))
                await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as local:
            headers = [{"X-Airalogy-Gateway-Token": s["credential"]} for s in stations]
            # Concurrent requests on one Gateway cannot both receive a job.
            receipts = await asyncio.gather(
                *[
                    local.post("/instrument-gateway/v1/jobs/lease", headers=headers[0])
                    for _ in range(2)
                ]
            )
            assert all(r.status_code == 200 for r in receipts), [
                r.text for r in receipts
            ]
            leases = [r.json() for r in receipts if r.json()["job"]]
            assert len(leases) == 1
            lease = leases[0]
            headers[0]["X-Airalogy-Instrument-Lease"] = lease["lease_token"]
            root = f"/instrument-gateway/v1/jobs/{jobs[0]}"
            started = await local.post(root + "/start", headers=headers[0], json={})
            assert started.status_code == 200, started.text
            for _ in range(2):
                failed = await local.post(
                    root + "/fail",
                    headers=headers[0],
                    json={"error": "Synthetic controller disconnect"},
                )
                assert (
                    failed.status_code == 200
                    and failed.json()["status"] == "stop_requested"
                ), failed.text
            # A later valid booking on a different Gateway cannot bypass the hold.
            async with sessionmanager.session() as db:
                job = await db.get(ResearchInstrumentJob, UUID(jobs[0]))
                assert job.completed_at is None and job.lease_token_digest
                booking = await db.get(EquipmentBooking, job.equipment_booking_id)
                booking.ends_at = datetime.now(UTC) - timedelta(seconds=1)
                await db.flush()
                later_job = await db.get(ResearchInstrumentJob, UUID(jobs[1]))
                later_booking = await db.get(
                    EquipmentBooking, later_job.equipment_booking_id
                )
                later_booking.starts_at = datetime.now(UTC)
                later_booking.status = "approved"
                await db.commit()
            held = await local.post(
                "/instrument-gateway/v1/jobs/lease", headers=headers[1]
            )
            assert held.status_code == 200 and held.json()["job"] is None, held.text
            gateway = stations[0]["gateway"]
            rotate = {
                "expected_revision": gateway["revision"],
                "reason": "Synthetic rotation check",
            }
            url = f"/research-instrument-gateways/{gateway['id']}/rotate"
            preview = await runtime.json("POST", url + "/preview", rotate)
            await runtime.json(
                "POST",
                url,
                {**rotate, "preview_digest": preview["preview_digest"]},
                status=409,
            )
            # Only an explicit bounded safe-stop confirmation releases the held equipment.
            recovered = await local.post(
                root + "/fail",
                headers=headers[0],
                json={
                    "error": "Synthetic controller disconnect",
                    "safe_stop_confirmed": True,
                },
            )
            assert (
                recovered.status_code == 200 and recovered.json()["status"] == "failed"
            ), recovered.text
            later = await local.post(
                "/instrument-gateway/v1/jobs/lease", headers=headers[1]
            )
            assert (
                later.status_code == 200 and later.json()["job"]["job_id"] == jobs[1]
            ), later.text
            headers[1]["X-Airalogy-Instrument-Lease"] = later.json()["lease_token"]
            cancelled = await local.post(
                f"/instrument-gateway/v1/jobs/{jobs[1]}/fail",
                headers=headers[1],
                json={"error": "Synthetic fixture complete before start"},
            )
            assert (
                cancelled.status_code == 200 and cancelled.json()["status"] == "failed"
            )

    runtime.run(exercise())


def test_instrument_package_import_review_revoke_and_private_file_roundtrip(
    runtime, monkeypatch
):
    import json
    from pathlib import Path

    from app.models.instrument_package import InstrumentAdapterRelease
    from app.models.knowledge import ResearchFile, ResearchFileAccessAudit

    repository = Path(__file__).resolve().parents[3]
    gateway = repository / "apps/instrument-gateway"
    monkeypatch.syspath_prepend(str(gateway / "src"))
    from airalogy_instrument_gateway.package_builder import build_package

    example = gateway / "examples/adapter-package"
    manifest = json.loads((example / "manifest.json").read_text())
    manifest["id"] = "synthetic." + uuid4().hex
    manifest["compatibility"]["declared"][0]["manufacturer"] = (
        " \u00a0Synthetic-" + uuid4().hex + "\u3000 "
    )
    manifest["compatibility"]["declared"][0]["architecture"] = "arm64"
    target = {
        **manifest["compatibility"]["declared"][0],
        "gateway_version": "0.1.0",
        "python_version": "3.12",
    }
    payloads = {
        name: (example / name).read_bytes()
        for name in [
            "source/synthetic_reader.py",
            "tests/test_reader.py",
            "licenses/LICENSE.txt",
        ]
    }
    raw, _inspection = build_package(
        manifest, factory="synthetic_reader:create_adapter", payloads=payloads
    )

    async def upload(path, data, request_id, digest=None, status=200):
        headers = {"Content-Type": "application/zip"}
        if digest:
            headers["X-Airalogy-Preview-Digest"] = digest
        response = await runtime.client.post(
            "/instrument-adapter-packages" + path,
            params={"lab_id": runtime.seed["lab"]["id"], "request_id": request_id},
            headers=headers,
            content=data,
        )
        assert response.status_code == status, response.text
        return response.json()

    async def exercise():
        request_id = str(uuid4())
        match_url = (
            f"/instrument-adapter-packages/match?lab_id={runtime.seed['lab']['id']}"
        )

        async def matches(profile=target, include_revoked=False, suffix="", status=200):
            return await runtime.json(
                "POST",
                match_url + suffix,
                {"profile": profile, "include_revoked": include_revoked},
                status=status,
            )

        assert (await matches())["items"] == []
        preview = await upload("/preview", raw, request_id)
        assert (
            not preview["hardware_authorized"]
            and not preview["installation_authorized"]
        )
        await upload("", raw, request_id, "a" * 64, status=409)
        saved = await upload("", raw, request_id, preview["preview_digest"])
        assert saved["state"] == "imported" and saved["id"] == request_id
        found = await matches()
        assert not found["model_called"] and not found["qualification_checked"]
        assert found["items"][0]["release"]["id"] == request_id
        assert found["items"][0]["comparison"]["status"] == "declaration_match"
        assert found["items"][0]["release"]["state"] == "imported"
        assert not found["items"][0]["comparison"]["hardware_authorized"]
        assert (
            await matches(
                {"manufacturer": target["manufacturer"], "model": target["model"]}
            )
        )["items"][0]["comparison"]["status"] == "needs_information"
        assert (await matches({**target, "application_version": "different"}))["items"][
            0
        ]["comparison"]["status"] == "conflicts"
        assert (await matches({**target, "model": "Missing model"}))["items"] == []
        await matches({**target, "hardware_authorized": True}, status=422)
        assert (
            await runtime.json("GET", f"/instrument-adapter-packages/{request_id}")
        )["archive_digest"] == saved["archive_digest"]
        await runtime.json(
            "POST",
            f"/instrument-adapter-packages/match?lab_id={uuid4()}",
            {"profile": target},
            status=404,
        )
        assert (await upload("", raw, request_id, preview["preview_digest"]))[
            "id"
        ] == request_id
        modified = {
            **manifest,
            "limitations": ["Different content for the same version"],
        }
        other, _ = build_package(
            modified, factory="synthetic_reader:create_adapter", payloads=payloads
        )
        await upload("/preview", other, str(uuid4()), status=409)
        review = {
            "expected_revision": 1,
            "operation": "approve_source",
            "reason": "Synthetic source reviewed independently",
            "source_reviewed": True,
        }
        review_url = f"/instrument-adapter-packages/{request_id}/review"
        reviewed = await runtime.confirm(review_url, review)
        assert reviewed["state"] == "approved" and reviewed["revision"] == 2
        assert (await matches())["items"][0]["release"]["state"] == "approved"
        await runtime.json("POST", review_url + "/preview", review, status=409)
        token = await runtime.json(
            "POST",
            f"/knowledge/files/{saved['research_file_id']}/token",
            {"mode": "download"},
        )
        response = await runtime.client.get(token["url"])
        assert response.status_code == 200, response.text
        assert response.content == raw
        assert "attachment" in response.headers["content-disposition"]
        revoked = await runtime.confirm(
            review_url,
            {
                **review,
                "expected_revision": 2,
                "operation": "revoke",
                "reason": "Synthetic version retired",
            },
        )
        assert revoked["state"] == "revoked"
        assert (await matches())["items"] == []
        assert (await matches(include_revoked=True))["items"][0]["release"][
            "state"
        ] == "revoked"
        assert (
            await runtime.json("GET", f"/instrument-adapter-packages/{request_id}")
        )["state"] == "revoked"
        # Neither a lost import response nor re-import revives a revoked release.
        assert (await upload("", raw, request_id, preview["preview_digest"]))[
            "state"
        ] == "revoked"
        await runtime.json(
            "POST",
            review_url + "/preview",
            {**review, "expected_revision": 3},
            status=409,
        )
        history = await runtime.json(
            "GET", f"/instrument-adapter-packages/{request_id}/history"
        )
        assert [item["action"] for item in history["items"]] == [
            "imported",
            "approved",
            "revoked",
        ]
        assert all(
            not item["snapshot"]["hardware_authorized"] for item in history["items"]
        )
        async with sessionmanager.session() as db:
            file = await db.get(ResearchFile, UUID(saved["research_file_id"]))
            assert file.scope_type == "lab" and file.visibility == "lab"
            assert (
                await db.scalars(
                    select(ResearchFileAccessAudit).where(
                        ResearchFileAccessAudit.research_file_id == file.id
                    )
                )
            ).all()
        # First-import race: one immutable identity and one logical file are retained.
        race_raw, _ = build_package(
            {**manifest, "version": "1.0.1"},
            factory="synthetic_reader:create_adapter",
            payloads=payloads,
        )
        race_ids = [str(uuid4()), str(uuid4())]
        previews = await asyncio.gather(
            *(upload("/preview", race_raw, rid) for rid in race_ids)
        )
        results = await asyncio.gather(
            *(
                upload("", race_raw, rid, p["preview_digest"])
                for rid, p in zip(race_ids, previews, strict=True)
            )
        )
        assert results[0]["id"] == results[1]["id"]
        first = await matches(include_revoked=True, suffix="&limit=1")
        second = await matches(
            include_revoked=True, suffix=f"&limit=1&offset={first['next_offset']}"
        )
        assert first["has_more"] and not second["has_more"]
        assert {
            first["items"][0]["release"]["id"],
            second["items"][0]["release"]["id"],
        } == {request_id, results[0]["id"]}
        assert len((await matches())["items"]) == 1
        async with sessionmanager.session() as db:
            releases = (
                await db.scalars(
                    select(InstrumentAdapterRelease).where(
                        InstrumentAdapterRelease.package_key == manifest["id"]
                    )
                )
            ).all()
            assert len(releases) == 2
        # A newer unrelated package must not hide matching rows before pagination.
        # Manufacturer and model on different declaration rows never combine.
        split_compatibility = {
            **manifest["compatibility"],
            "declared": [
                {
                    **manifest["compatibility"]["declared"][0],
                    "manufacturer": "Different manufacturer",
                },
                {
                    **manifest["compatibility"]["declared"][0],
                    "model": "Different model",
                },
            ],
        }
        split_raw, _ = build_package(
            {**manifest, "version": "1.0.2", "compatibility": split_compatibility},
            factory="synthetic_reader:create_adapter",
            payloads=payloads,
        )
        split_id = str(uuid4())
        split_preview = await upload("/preview", split_raw, split_id)
        await upload("", split_raw, split_id, split_preview["preview_digest"])
        filtered = await matches(suffix="&limit=1")
        assert not filtered["has_more"]
        assert filtered["items"][0]["release"]["id"] == results[0]["id"]
        original_auth = runtime.client.headers["Auth-Token"]
        viewer = next(
            account
            for account in runtime.seed["accounts"]
            if account["key"] == "viewer"
        )
        auth = await runtime.json(
            "POST",
            "/signin_by_email",
            {"email": viewer["email"], "password": viewer["password"]},
        )
        try:
            runtime.client.headers["Auth-Token"] = auth["token"]
            await matches(status=403)
            await runtime.json(
                "GET", f"/instrument-adapter-packages/{request_id}", status=403
            )
            await runtime.json(
                "GET",
                f"/instrument-adapter-packages?lab_id={runtime.seed['lab']['id']}",
                status=403,
            )
            await upload("/preview", raw, str(uuid4()), status=403)
            await runtime.json("POST", review_url + "/preview", review, status=403)
            await runtime.json(
                "GET", f"/instrument-adapter-packages/{request_id}/history", status=403
            )
        finally:
            runtime.client.headers["Auth-Token"] = original_auth
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as anonymous:
            assert (
                await anonymous.post(match_url, json={"profile": target})
            ).status_code == 401
            assert (
                await anonymous.get(f"/instrument-adapter-packages/{request_id}")
            ).status_code == 401
            assert (
                await anonymous.get(
                    f"/instrument-adapter-packages?lab_id={runtime.seed['lab']['id']}"
                )
            ).status_code == 401
            assert (await anonymous.get(token["url"])).status_code == 401

    runtime.run(exercise())


def test_installation_grant_real_local_copy_receipt_and_revocation(
    runtime, monkeypatch, tmp_path
):
    """Real authorization/storage/local install; no driver or hardware execution."""
    import json
    from pathlib import Path

    from app.models.instrument_installation import InstrumentDeviceBinding
    from app.models.knowledge import ResearchFile, ResearchFileAccessAudit
    from app.models.research_execution import (
        ResearchInstrumentCommand,
        ResearchInstrumentGateway,
    )
    from app.services.instrument_installations import managed_execution_block_reason
    from app.services.research_capabilities import instrument_command_capability_rows
    from app.services.research_instruments import (
        gateway_token_digest,
        generate_gateway_token,
    )

    sdk_root = Path(__file__).resolve().parents[3] / "apps/instrument-gateway"
    monkeypatch.syspath_prepend(str(sdk_root / "src"))
    monkeypatch.syspath_prepend(str(sdk_root / "tests"))
    from airalogy_instrument_gateway.installation_manager import (
        apply,
        prepare,
        read_request,
    )
    from airalogy_instrument_gateway.package_builder import build_package
    from airalogy_instrument_gateway.package_contract import sha256
    from test_package_installation import sdk

    example = sdk_root / "examples/adapter-package"
    manifest = json.loads((example / "manifest.json").read_text())
    manifest["id"] = "synthetic." + uuid4().hex
    raw, _ = build_package(
        manifest,
        factory="synthetic_reader:create_adapter",
        payloads={
            name: (example / name).read_bytes()
            for name in [
                "source/synthetic_reader.py",
                "tests/test_reader.py",
                "licenses/LICENSE.txt",
            ]
        },
    )
    sdk_bytes = sdk()
    # pytest ancestors need not be private; the actual selected root must be.
    root = tmp_path.resolve() / "station"
    root.mkdir(mode=0o700)
    (root / "package.zip").write_bytes(raw)
    (root / "sdk.whl").write_bytes(sdk_bytes)
    (root / "config.json").write_text("{}")

    async def exercise():
        lab = runtime.seed["lab"]["id"]
        base = f"/labs/{lab}/resource-library"
        definitions = await runtime.json("GET", base + "/definition-versions")
        definition = next(
            item
            for item in definitions["items"]
            if item["protocol_uid"] == "plasmid_resource_definition_en"
        )
        kind = await runtime.json(
            "POST",
            base + "/types",
            {
                "protocol_version_id": definition["id"],
                "code": "install_" + uuid4().hex,
                "name": "Synthetic installation fixture",
                "capabilities": {"booking": True},
                "booking_policy": "approval",
            },
        )
        resource = await runtime.json(
            "POST",
            base + "/resources",
            {
                "resource_type_id": kind["id"],
                "name": "Synthetic installation equipment",
                "code": uuid4().hex,
                "visibility": "lab",
                "data": {
                    "construct_name": "Synthetic",
                    "features": [],
                    **dict.fromkeys(
                        [
                            "aliases",
                            "backbone",
                            "sequence",
                            "sequence_file",
                            "resistance_markers",
                            "host_species",
                            "copy_number",
                            "external_source",
                        ]
                    ),
                },
            },
        )
        gateway = (
            await runtime.confirm(
                "/research-instrument-gateways",
                {"lab_id": lab, "name": "Install " + uuid4().hex, "enabled": False},
            )
        )["gateway"]
        issued = await runtime.confirm(
            "/instrument-pairings",
            {
                "gateway_id": gateway["id"],
                "expected_revision": gateway["revision"],
                "reason": "Synthetic pairing",
            },
        )
        runtime_token = generate_gateway_token()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as local:
            paired = await local.post(
                "/instrument-pairings/claim",
                json={
                    "code": issued["code"],
                    "gateway_id": gateway["id"],
                    "lab_id": lab,
                    "client_name": "Synthetic station",
                    "credential_digest": gateway_token_digest(runtime_token),
                    "credential_hint": runtime_token[-8:],
                },
            )
            assert paired.status_code == 200, paired.text
            pair_url = f"/instrument-pairings/{issued['pairing']['id']}"
            preview = await runtime.json("POST", pair_url + "/preview")
            gateway = (
                await runtime.json(
                    "POST",
                    pair_url + "/confirm",
                    {"preview_digest": preview["preview_digest"]},
                )
            )["gateway"]
            release_id = str(uuid4())
            upload_params = {"lab_id": lab, "request_id": release_id}
            headers = {"Content-Type": "application/zip"}
            preview = await runtime.client.post(
                "/instrument-adapter-packages/preview",
                params=upload_params,
                content=raw,
                headers=headers,
            )
            assert preview.status_code == 200, preview.text
            saved = await runtime.client.post(
                "/instrument-adapter-packages",
                params=upload_params,
                content=raw,
                headers={
                    **headers,
                    "X-Airalogy-Preview-Digest": preview.json()["preview_digest"],
                },
            )
            assert saved.status_code == 200, saved.text
            review_url = f"/instrument-adapter-packages/{release_id}/review"
            await runtime.confirm(
                review_url,
                {
                    "expected_revision": 1,
                    "operation": "approve_source",
                    "source_reviewed": True,
                    "reason": "Reviewed synthetic source",
                },
            )

            def new_request(name):
                path = root / name
                public = prepare(
                    destination=path,
                    platform_url="http://127.0.0.1",
                    lab_id=lab,
                    gateway_id=gateway["id"],
                    package=root / "package.zip",
                    sdk_wheel=root / "sdk.whl",
                    trusted_sdk_digest=sha256(sdk_bytes),
                    config=root / "config.json",
                    root=root,
                )
                return (
                    path,
                    public,
                    {
                        "request": public,
                        "resource_id": resource["id"],
                        "release_id": release_id,
                        "reason": "Independent inactive installation approval",
                        "fingerprint_confirmed": True,
                    },
                )

            path, public, draft = new_request("private.json")
            preview = await runtime.json(
                "POST", "/instrument-installations/preview", draft
            )
            await runtime.json(
                "POST",
                "/instrument-installations",
                {
                    **draft,
                    "reason": "Changed",
                    "preview_digest": preview["preview_digest"],
                },
                status=409,
            )
            grants = await asyncio.gather(
                *(
                    runtime.json(
                        "POST",
                        "/instrument-installations",
                        {**draft, "preview_digest": preview["preview_digest"]},
                    )
                    for _ in range(2)
                )
            )
            assert grants[0]["id"] == grants[1]["id"] == public["id"]
            assert (
                "gateway_credential_pin" not in grants[0]
                and "installer_token_digest" not in grants[0]
            )
            url = f"/instrument-installations/{public['id']}"
            local.headers["X-Airalogy-Installation-Token"] = runtime_token
            assert (await local.post(url + "/claim")).status_code == 401
            local.headers["X-Airalogy-Installation-Token"] = read_request(path)[
                "installation_token"
            ]
            assert (await local.post(url + "/package")).status_code == 409
            assert (
                await local.post(f"/instrument-installations/{uuid4()}/claim")
            ).status_code == 401
            assert (
                await local.post("/instrument-gateway/v1/jobs/lease")
            ).status_code in {401, 422}
            rotation = {
                "expected_revision": gateway["revision"],
                "reason": "Must block pending installation",
            }
            rotate_preview = await runtime.json(
                "POST",
                f"/research-instrument-gateways/{gateway['id']}/rotate/preview",
                rotation,
            )
            await runtime.json(
                "POST",
                f"/research-instrument-gateways/{gateway['id']}/rotate",
                {**rotation, "preview_digest": rotate_preview["preview_digest"]},
                status=409,
            )
            await runtime.json(
                "POST",
                "/instrument-pairings/preview",
                {**rotation, "gateway_id": gateway["id"]},
                status=409,
            )
            update = {
                **rotation,
                "name": gateway["name"],
                "description": gateway["description"],
                "enabled": True,
            }
            update_preview = await runtime.json(
                "POST", f"/research-instrument-gateways/{gateway['id']}/preview", update
            )
            await runtime.json(
                "PUT",
                f"/research-instrument-gateways/{gateway['id']}",
                {**update, "preview_digest": update_preview["preview_digest"]},
                status=409,
            )

            loop = asyncio.get_running_loop()
            calls = []

            async def call(operation, payload):
                calls.append(operation)
                response = await local.post(url + "/" + operation, json=payload or {})
                assert response.status_code == 200, response.text
                return response.content if operation == "package" else response.json()

            class Bridge:
                def call(self, operation, payload=None):
                    return asyncio.run_coroutine_threadsafe(
                        call(operation, payload), loop
                    ).result(timeout=30)

            result = await asyncio.to_thread(
                apply, path, source_reviewed=True, client=Bridge()
            )
            assert result["state"] == "installed" and not result["hardware_authorized"]
            assert calls == ["status", "claim", "package", "receipt"]
            calls.clear()
            await asyncio.to_thread(apply, path, source_reviewed=True, client=Bridge())
            assert calls == ["status", "receipt"]
            binding = (
                await runtime.json(
                    "GET", f"/instrument-installations?gateway_id={gateway['id']}"
                )
            )["items"][0]
            assert binding["execution_state"] == "inactive"
            # Independent observations are immutable acceptance records, not commands.
            from tests.test_instrument_qualifications import (
                report as qualification_report,
            )

            qualification_url = url + "/qualifications"
            qdraft = qualification_report()
            qdraft["commands"][0]["key"] = "reader.measure"
            qpreview = await runtime.json(
                "POST", qualification_url + "/preview", qdraft
            )
            assert qpreview["pins"]["descriptor"] == public["descriptor"]
            assert qpreview["hardware_authorized"] is False
            await runtime.json(
                "POST",
                qualification_url,
                {
                    **qdraft,
                    "reason": "Modified before first confirmation",
                    "preview_digest": qpreview["preview_digest"],
                },
                status=409,
            )
            qualified = await runtime.json(
                "POST",
                qualification_url,
                {**qdraft, "preview_digest": qpreview["preview_digest"]},
            )
            assert qualified["effective_state"] == "simulation_only"
            assert (
                not qualified["hardware_authorized"]
                and not qualified["activation_performed"]
            )
            repeated = await runtime.json(
                "POST",
                qualification_url,
                {**qdraft, "preview_digest": qpreview["preview_digest"]},
            )
            assert repeated["id"] == qualified["id"]
            await runtime.json(
                "POST",
                qualification_url,
                {
                    **qdraft,
                    "reason": "Changed after preview",
                    "preview_digest": qpreview["preview_digest"],
                },
                status=409,
            )
            await runtime.json(
                "POST",
                qualification_url + "/preview",
                {
                    **qdraft,
                    "scope": "read_only",
                    "independent_review_confirmed": True,
                    "physical_tests_authorized": True,
                },
                status=422,
            )
            failed_draft = qualification_report()
            failed_draft["commands"][0]["key"] = "reader.measure"
            failed_draft["commands"][0]["checks"][0]["passed"] = False
            failed_qualification = await runtime.confirm(
                qualification_url, failed_draft
            )
            assert failed_qualification["effective_state"] == "failed"
            listed = await runtime.json("GET", qualification_url)
            assert len(listed["items"]) == 2
            # A separately scoped evidence reference never grants bytes/access.
            async with sessionmanager.session() as db:
                source_file = await db.get(
                    ResearchFile, UUID(saved.json()["research_file_id"])
                )
                evidence_file = ResearchFile(
                    blob_id=source_file.blob_id,
                    filename="synthetic-acceptance-evidence.zip",
                    scope_type="lab",
                    lab_id=source_file.lab_id,
                    visibility="lab",
                    uploaded_by_user_id=source_file.uploaded_by_user_id,
                )
                db.add(evidence_file)
                await db.flush()
                evidence_id = str(evidence_file.id)
                await db.commit()
            evidence_draft = {
                **qdraft,
                "id": str(uuid4()),
                "evidence_file_ids": [evidence_id],
            }
            await runtime.json(
                "POST",
                qualification_url + "/preview",
                {**evidence_draft, "evidence_file_ids": [str(uuid4())]},
                status=404,
            )
            evidence_record = await runtime.confirm(qualification_url, evidence_draft)
            assert (
                evidence_record["evidence_files"][0]["sha256"]
                == public["descriptor"]["archive_digest"]
            )
            async with sessionmanager.session() as db:
                evidence_file = await db.get(ResearchFile, UUID(evidence_id))
                evidence_file.archived_at = datetime.now(UTC)
                await db.commit()
            evidence_list = await runtime.json("GET", qualification_url)
            hidden = next(
                item
                for item in evidence_list["items"]
                if item["id"] == evidence_record["id"]
            )
            assert (
                hidden["effective_state"] == "evidence_unavailable"
                and hidden["details_redacted"]
            )
            assert "report" not in hidden and "pins" not in hidden
            await runtime.confirm(
                qualification_url + f"/{evidence_record['id']}/revoke",
                {"expected_revision": 1, "reason": "Withdraw after evidence archive"},
            )
            revoke_q_url = qualification_url + f"/{failed_qualification['id']}/revoke"
            revoke_q = {
                "expected_revision": 1,
                "reason": "Keep failed synthetic evidence, withdraw acceptance",
            }
            revoke_q_preview = await runtime.json(
                "POST", revoke_q_url + "/preview", revoke_q
            )
            for _ in range(2):
                revoked = await runtime.json(
                    "POST",
                    revoke_q_url,
                    {**revoke_q, "preview_digest": revoke_q_preview["preview_digest"]},
                )
                assert revoked["effective_state"] == "revoked"
            # A receipt must not reopen the old manual enablement path.
            await runtime.json(
                "PUT",
                f"/research-instrument-gateways/{gateway['id']}",
                {**update, "preview_digest": update_preview["preview_digest"]},
                status=409,
            )
            alternate = await runtime.confirm(
                "/research-instrument-gateways",
                {
                    "lab_id": lab,
                    "name": "Alternate synthetic installation " + uuid4().hex,
                    "enabled": True,
                },
            )
            command_draft = {
                "gateway_id": alternate["gateway"]["id"],
                "resource_id": resource["id"],
                "command_key": "synthetic.read",
                "command_version": "1.0.0",
                "name": "Synthetic read",
                "timeout_seconds": 30,
                "input_schema": {"type": "object", "additionalProperties": False},
                "output_schema": {"type": "object", "additionalProperties": False},
                "risk": "read_only",
                "device_confirmation_required": False,
                "enabled": True,
            }
            await runtime.json(
                "POST",
                "/research-instrument-gateways/commands/preview",
                command_draft,
                status=409,
            )
            # Disabled definitions may still be prepared for later qualification.
            disabled = await runtime.confirm(
                "/research-instrument-gateways/commands",
                {**command_draft, "enabled": False},
            )
            enable_command = {
                key: value
                for key, value in command_draft.items()
                if key
                not in {"gateway_id", "resource_id", "command_key", "command_version"}
            }
            enable_command.update(
                expected_revision=disabled["revision"], reason="Must not bypass"
            )
            await runtime.json(
                "POST",
                f"/research-instrument-gateways/commands/{disabled['id']}/preview",
                enable_command,
                status=409,
            )
            receipt = binding["receipt"]
            assert str(root) not in json.dumps(receipt)
            assert (
                await local.post(
                    url + "/receipt",
                    json={"receipt": {**receipt, "local_receipt_digest": "a" * 64}},
                )
            ).status_code == 409
            assert (
                await local.post(
                    url + "/receipt",
                    json={"receipt": {**receipt, "hardware_authorized": True}},
                )
            ).status_code == 422
            async with sessionmanager.session() as db:
                audit = await db.scalar(
                    select(ResearchFileAccessAudit).where(
                        ResearchFileAccessAudit.action == "install_download",
                        ResearchFileAccessAudit.request_id == public["id"],
                    )
                )
                assert audit is not None
            history = await runtime.json("GET", url + "/history")
            assert [entry["action"] for entry in history["items"]] == [
                "authorized",
                "claimed",
                "package_downloaded",
                "installed",
            ]
            original_auth = runtime.client.headers["Auth-Token"]
            viewer = next(
                account
                for account in runtime.seed["accounts"]
                if account["key"] == "viewer"
            )
            auth = await runtime.json(
                "POST",
                "/signin_by_email",
                {"email": viewer["email"], "password": viewer["password"]},
            )
            try:
                runtime.client.headers["Auth-Token"] = auth["token"]
                await runtime.json("GET", qualification_url, status=403)
                await runtime.json(
                    "POST", qualification_url + "/preview", qdraft, status=403
                )
                await runtime.json("GET", url + "/history", status=403)
                await runtime.json(
                    "GET",
                    f"/instrument-installations?gateway_id={gateway['id']}",
                    status=403,
                )
                await runtime.json(
                    "POST", "/instrument-installations/preview", draft, status=403
                )
                await runtime.json(
                    "POST",
                    url + "/revoke/preview",
                    {
                        "expected_revision": binding["revision"],
                        "reason": "Unauthorized revocation",
                    },
                    status=403,
                )
            finally:
                runtime.client.headers["Auth-Token"] = original_auth
            await runtime.confirm(
                url + "/revoke",
                {
                    "expected_revision": binding["revision"],
                    "reason": "Retire synthetic installation",
                },
            )
            invalidated = await runtime.json("GET", qualification_url)
            saved_qualification = next(
                item for item in invalidated["items"] if item["id"] == qualified["id"]
            )
            assert saved_qualification["effective_state"] == "installation_not_current"
            assert saved_qualification["report"] == qualified["report"]
            async with sessionmanager.session() as db:
                # Revocation/identity rotation must not remove a claimed-history gate.
                assert await managed_execution_block_reason(db, UUID(gateway["id"]))
                assert await managed_execution_block_reason(
                    db, UUID(alternate["gateway"]["id"]), UUID(resource["id"])
                )
                assert (
                    await managed_execution_block_reason(
                        db, UUID(alternate["gateway"]["id"]), uuid4()
                    )
                    is None
                )
                station = await db.get(ResearchInstrumentGateway, UUID(gateway["id"]))
                # Fault injection only: even an older enabled DB row cannot lease.
                station.enabled = True
                manual_command = await db.get(
                    ResearchInstrumentCommand, UUID(disabled["id"])
                )
                manual_command.enabled = True
                await db.flush()
                assert all(
                    str(command.id) != disabled["id"]
                    for command, _, _ in await instrument_command_capability_rows(
                        db, lab_id=UUID(lab)
                    )
                )
                await db.commit()
            guarded_lease = await local.post(
                "/instrument-gateway/v1/jobs/lease",
                headers={"X-Airalogy-Gateway-Token": runtime_token},
            )
            assert guarded_lease.status_code == 409, guarded_lease.text
            assert "activation" in guarded_lease.text
            async with sessionmanager.session() as db:
                station = await db.get(ResearchInstrumentGateway, UUID(gateway["id"]))
                station.enabled = False
                await db.commit()
            assert (
                await local.post(url + "/receipt", json={"receipt": receipt})
            ).status_code == 409

            path2, public2, draft2 = new_request("private2.json")
            await runtime.confirm("/instrument-installations", draft2)
            local.headers["X-Airalogy-Installation-Token"] = read_request(path2)[
                "installation_token"
            ]
            url2 = f"/instrument-installations/{public2['id']}"
            async with sessionmanager.session() as db:
                row = await db.get(InstrumentDeviceBinding, UUID(public2["id"]))
                row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                await db.commit()
            assert (await local.post(url2 + "/claim")).status_code == 409
            # Expired unclaimed requests release the unique pending slot atomically.
            path3, public3, draft3 = new_request("private3.json")
            await runtime.confirm("/instrument-installations", draft3)
            local.headers["X-Airalogy-Installation-Token"] = read_request(path3)[
                "installation_token"
            ]
            url3 = f"/instrument-installations/{public3['id']}"
            assert (await local.post(url3 + "/claim")).status_code == 200
            async with sessionmanager.session() as db:
                row = await db.get(InstrumentDeviceBinding, UUID(public3["id"]))
                row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                await db.commit()
            assert (await local.post(url3 + "/package")).status_code == 409
            # An already durable inactive receipt may reconcile after download expiry.
            assert (
                await local.post(url3 + "/receipt", json={"receipt": receipt})
            ).status_code == 200
            await runtime.confirm(
                review_url,
                {
                    "expected_revision": 2,
                    "operation": "revoke",
                    "source_reviewed": False,
                    "reason": "Withdraw synthetic source",
                },
            )
            assert (
                await local.post(url3 + "/receipt", json={"receipt": receipt})
            ).status_code == 409
            # Revocation remains possible even after the source review is withdrawn.
            state = (await local.post(url3 + "/status")).json()
            await runtime.confirm(
                url3 + "/revoke",
                {
                    "expected_revision": state["revision"],
                    "reason": "Reconcile withdrawn source",
                },
            )

    runtime.run(exercise())


def test_instrument_pairing_single_use_scope_expiry_and_confirmation(runtime):
    from app.models.instrument_pairing import InstrumentPairing
    from app.models.research_execution import (
        ResearchInstrumentGateway,
        ResearchInstrumentGatewayAudit,
    )
    from app.services.research_instruments import (
        gateway_token_digest,
        generate_gateway_token,
    )

    async def exercise():
        original = await runtime.confirm(
            "/research-instrument-gateways",
            {
                "lab_id": runtime.seed["lab"]["id"],
                "name": "Pairing " + uuid4().hex,
                "enabled": False,
            },
        )
        gateway = original["gateway"]
        draft = {
            "gateway_id": gateway["id"],
            "expected_revision": gateway["revision"],
            "reason": "Synthetic local installation",
        }
        issued = await runtime.confirm("/instrument-pairings", draft)
        pair_id = issued["pairing"]["id"]
        token = generate_gateway_token()
        claim = {
            "code": issued["code"],
            "gateway_id": gateway["id"],
            "lab_id": gateway["lab_id"],
            "client_name": "Synthetic local station",
            "credential_digest": gateway_token_digest(token),
            "credential_hint": token[-8:],
        }
        # No user cookie/session at the equipment station; possession of the short-lived code only.
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as local:
            assert (
                await local.post(
                    "/instrument-pairings/claim", json={**claim, "lab_id": str(uuid4())}
                )
            ).status_code == 404
            competing = {**claim, "credential_digest": "d" * 64}
            responses = await asyncio.gather(
                local.post("/instrument-pairings/claim", json=claim),
                local.post("/instrument-pairings/claim", json=competing),
            )
            assert sorted(response.status_code for response in responses) == [200, 409]
            # Determine the winner without silently replacing its identity.
            accepted = next(
                response.json() for response in responses if response.status_code == 200
            )
            winner = claim if responses[0].status_code == 200 else competing
            retry = await local.post("/instrument-pairings/claim", json=winner)
            assert retry.status_code == 200
            assert retry.json()["fingerprint"] == accepted["fingerprint"]
            async with sessionmanager.session() as db:
                saved_gateway = await db.get(
                    ResearchInstrumentGateway, UUID(gateway["id"])
                )
                assert saved_gateway.token_digest == gateway_token_digest(
                    original["credential"]
                )
            preview = await runtime.json(
                "POST", f"/instrument-pairings/{pair_id}/preview"
            )
            assert preview["pairing"]["fingerprint"] == accepted["fingerprint"]
            await runtime.json(
                "POST",
                f"/instrument-pairings/{pair_id}/confirm",
                {"preview_digest": "0" * 64},
                status=409,
            )
            confirmed = await runtime.json(
                "POST",
                f"/instrument-pairings/{pair_id}/confirm",
                {"preview_digest": preview["preview_digest"]},
            )
            assert confirmed["gateway"]["enabled"] is False
            assert confirmed["pairing"]["state"] == "confirmed"
            assert (
                await local.post("/instrument-pairings/claim", json=winner)
            ).status_code == 409
            assert (
                await local.post(f"/instrument-pairings/{pair_id}/status")
            ).status_code == 404
            # A second confirmed enrollment tests a known local credential and lost-response recovery.
            draft["expected_revision"] = confirmed["gateway"]["revision"]
            issued2 = await runtime.confirm("/instrument-pairings", draft)
            claim["code"] = issued2["code"]
            assert (
                await local.post("/instrument-pairings/claim", json=claim)
            ).status_code == 200
            pair2 = issued2["pairing"]["id"]
            preview2 = await runtime.json(
                "POST", f"/instrument-pairings/{pair2}/preview"
            )
            await runtime.json(
                "POST",
                f"/instrument-pairings/{pair2}/confirm",
                {"preview_digest": preview2["preview_digest"]},
            )
            status = await local.post(
                f"/instrument-pairings/{pair2}/status",
                headers={"X-Airalogy-Gateway-Token": token},
            )
            assert status.json()["state"] == "confirmed"
            commands = await runtime.json(
                "GET", f"/research-instrument-gateways/{gateway['id']}/commands"
            )
            assert commands["items"] == []
            draft["expected_revision"] += 1
            expired = await runtime.confirm("/instrument-pairings", draft)
            async with sessionmanager.session() as db:
                row = await db.get(InstrumentPairing, UUID(expired["pairing"]["id"]))
                row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                await db.commit()
            assert (
                await local.post(
                    "/instrument-pairings/claim",
                    json={**claim, "code": expired["code"]},
                )
            ).status_code == 409
            cancelled = await runtime.confirm("/instrument-pairings", draft)
            await runtime.json(
                "POST", f"/instrument-pairings/{cancelled['pairing']['id']}/cancel"
            )
            assert (
                await local.post(
                    "/instrument-pairings/claim",
                    json={**claim, "code": cancelled["code"]},
                )
            ).status_code == 409
        async with sessionmanager.session() as db:
            audits = (
                await db.scalars(
                    select(ResearchInstrumentGatewayAudit).where(
                        ResearchInstrumentGatewayAudit.gateway_id == UUID(gateway["id"])
                    )
                )
            ).all()
            for audit in audits:
                assert "credential_digest" not in str(audit.snapshot)
                assert issued["code"] not in str(audit.snapshot)
        original_auth = runtime.client.headers["Auth-Token"]
        viewer = next(
            account
            for account in runtime.seed["accounts"]
            if account["key"] == "viewer"
        )
        auth = await runtime.json(
            "POST",
            "/signin_by_email",
            {"email": viewer["email"], "password": viewer["password"]},
        )
        try:
            runtime.client.headers["Auth-Token"] = auth["token"]
            await runtime.json(
                "GET", f"/instrument-pairings?gateway_id={gateway['id']}", status=403
            )
            await runtime.json(
                "POST", "/instrument-pairings/preview", draft, status=403
            )
            await runtime.json(
                "POST", f"/instrument-pairings/{pair_id}/preview", status=403
            )
        finally:
            runtime.client.headers["Auth-Token"] = original_auth

    runtime.run(exercise())


def test_instrument_integration_revisions_permissions_and_no_execution(
    runtime, monkeypatch
):
    """Real authorization and PostgreSQL writes; synthetic observations only."""
    import copy
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.routers import instrument_integrations as integration_router
    from app.services.instrument_adapter_contract import example_bundle

    async def exercise():
        suffix = uuid4().hex
        base = f"/labs/{runtime.seed['lab']['id']}/resource-library"
        definitions = await runtime.json("GET", base + "/definition-versions")
        definition = next(
            item
            for item in definitions["items"]
            if item["protocol_uid"] == "plasmid_resource_definition_en"
        )
        # Reuse a synthetic resource-definition fixture, not a vendor device schema.
        resource_type = await runtime.json(
            "POST",
            base + "/types",
            {
                "protocol_version_id": definition["id"],
                "code": f"integration_{suffix}",
                "name": "Synthetic equipment",
                "capabilities": {"booking": True},
                "booking_policy": "approval",
            },
        )
        resource = await runtime.json(
            "POST",
            base + "/resources",
            {
                "resource_type_id": resource_type["id"],
                "name": "Synthetic GUI reader",
                "code": f"GUI-{suffix}",
                "visibility": "lab",
                "data": {
                    "construct_name": "Synthetic fixture",
                    "aliases": None,
                    "backbone": None,
                    "sequence": None,
                    "sequence_file": None,
                    "resistance_markers": None,
                    "host_species": None,
                    "copy_number": None,
                    "external_source": None,
                    "features": [],
                },
            },
        )
        gateway = (
            await runtime.confirm(
                "/research-instrument-gateways",
                {
                    "lab_id": runtime.seed["lab"]["id"],
                    "name": f"GUI rehearsal {suffix}",
                    "enabled": False,
                },
            )
        )["gateway"]
        draft = {
            "id": str(uuid4()),
            "gateway_id": gateway["id"],
            "resource_id": resource["id"],
            "expected_revision": 0,
            "goal": "Read synthetic GUI result",
            "reason": "Initial integration",
            "bundle": example_bundle(),
        }
        preview = await runtime.json("POST", "/instrument-integrations/preview", draft)
        assert preview["report"]["passed"] is True
        responses = await asyncio.gather(
            *[
                runtime.client.post(
                    "/instrument-integrations",
                    json={**draft, "preview_digest": preview["preview_digest"]},
                )
                for _ in range(2)
            ]
        )
        assert sorted(response.status_code for response in responses) == [200, 409]
        saved = next(
            response.json() for response in responses if response.status_code == 200
        )
        assert saved["revision"] == 1
        assert saved["report"]["hardware_authorized"] is False
        changed = {
            **draft,
            "expected_revision": 1,
            "goal": "Review a changed observation",
        }
        pending = await runtime.json(
            "POST", "/instrument-integrations/preview", changed
        )
        await runtime.json(
            "POST",
            "/instrument-integrations",
            {
                **changed,
                "goal": "Unpreviewed change",
                "preview_digest": pending["preview_digest"],
            },
            status=409,
        )
        updated = await runtime.json(
            "POST",
            "/instrument-integrations",
            {**changed, "preview_digest": pending["preview_digest"]},
        )
        assert updated["revision"] == 2
        history = await runtime.json(
            "GET", f"/instrument-integrations/{saved['id']}/history"
        )
        assert [item["revision"] for item in history["items"]] == [2, 1]
        assert history["items"][1]["snapshot"]["goal"] == draft["goal"]
        commands = await runtime.json(
            "GET", f"/research-instrument-gateways/{gateway['id']}/commands"
        )
        assert commands["items"] == []
        await runtime.json(
            "POST",
            "/instrument-integrations/draft-with-aira",
            {**draft, "expected_revision": 2, "model_processing_consent": True},
            status=409,
        )
        # Inject only the external model response; exercise actual HTTP parsing,
        # authorization and transaction release/recheck against PostgreSQL.
        generated = copy.deepcopy(draft["bundle"]["package"])
        generated["source"]["kind"] = "aira"
        with monkeypatch.context() as model_patch:
            model_patch.setattr(
                integration_router,
                "config",
                SimpleNamespace(
                    effective_ai_enabled=True, CHAT_MODEL_FAST="synthetic-provider"
                ),
            )
            provider = AsyncMock(return_value=generated)
            model_patch.setattr(
                integration_router, "aira_structured_proposal", provider
            )
            proposed = await runtime.json(
                "POST",
                "/instrument-integrations/draft-with-aira",
                {
                    **draft,
                    "expected_revision": 2,
                    "model_processing_consent": True,
                },
            )
            assert proposed["package"] == generated
            assert proposed["hardware_authorized"] is False
            provider.assert_awaited_once()
        unchanged = await runtime.json(
            "GET", f"/instrument-integrations/{saved['id']}/history"
        )
        assert len(unchanged["items"]) == 2
        original_token = runtime.client.headers["Auth-Token"]
        viewer = next(
            account
            for account in runtime.seed["accounts"]
            if account["key"] == "viewer"
        )
        auth = await runtime.json(
            "POST",
            "/signin_by_email",
            {"email": viewer["email"], "password": viewer["password"]},
        )
        try:
            runtime.client.headers["Auth-Token"] = auth["token"]
            await runtime.json(
                "GET",
                f"/instrument-integrations?gateway_id={gateway['id']}",
                status=403,
            )
            await runtime.json(
                "GET", f"/instrument-integrations/{saved['id']}/history", status=403
            )
            await runtime.json(
                "POST",
                "/instrument-integrations/preview",
                {**draft, "expected_revision": 2},
                status=403,
            )
        finally:
            runtime.client.headers["Auth-Token"] = original_token

    runtime.run(exercise())


def test_manual_knowledge_and_claim_creation_without_generation_metadata(runtime):
    async def exercise():
        task = await runtime.task()
        knowledge = await runtime.confirm(
            "/knowledge/items",
            {
                "scope_type": "personal",
                "visibility": "private",
                "kind": "note",
                "title": "Synthetic manual researcher note",
                "body": "An observation to verify, not a scientific conclusion.",
            },
        )
        assert knowledge["generated_by"] == "human"
        assert knowledge["generation_snapshot"] is None
        updated = await runtime.json(
            "PATCH",
            f"/knowledge/items/{knowledge['id']}",
            {
                "expected_revision": knowledge["revision"],
                "body": "Revised synthetic note with uncertainty preserved.",
                "change_summary": "Clarify uncertainty",
            },
        )
        assert updated["revision"] == 2 and updated["updated_at"]
        claim = await runtime.confirm(
            "/research-assets/claims",
            {
                "task_id": task["id"],
                "statement": "Synthetic unverified claim for interface testing",
                "uncertainty": "No scientific validation has been performed.",
                "evidence": [],
            },
        )
        assert claim["state"] == "draft"
        assert claim["generated_by"] == "human"
        assert claim["generation_snapshot"] is None

    runtime.run(exercise())


def test_ai_disabled_tool_pause_resume_evidence_and_final_package(runtime):
    async def exercise():
        assert not config.effective_ai_enabled
        task = await runtime.task()
        tool = await runtime.tool(task)
        await runtime.transition(task["id"], "pause")
        assert await runtime.dispatch(tool) == ("pending", 0)
        paused = await runtime.json("GET", f"/research-tasks/{task['id']}")
        assert paused["actions"][0]["status"] == "queued"
        await runtime.transition(task["id"], "resume")
        assert await runtime.dispatch(tool) == ("succeeded", 1)
        evidence = await runtime.confirm(
            "/research-assets/evidence",
            {
                "task_id": task["id"],
                "run_id": task["runs"][0]["id"],
                "action_id": tool["id"],
                "kind": "citation",
                "artifact_type": "action_output",
                "artifact_id": tool["id"],
                "summary": "The local search returned its actual structured result",
            },
        )
        assert evidence["quality_state"] == "pending"
        assert len(evidence["artifact_version"]) == 64
        await runtime.json(
            "POST",
            f"/research-assets/evidence/{evidence['id']}/review",
            {
                "expected_quality_state": "pending",
                "quality_state": "validated",
                "validation_report": {
                    "scope": "search result only, not experimental proof"
                },
            },
        )
        completed = await runtime.transition(
            task["id"],
            "complete",
            outcome="inconclusive",
            scientific_outcome="inconclusive",
            conclusion="Local search alone cannot settle the research question.",
        )
        assert completed["status"] == "completed"
        package = await runtime.json(
            "GET", f"/research-tasks/{task['id']}/result-package"
        )
        assert evidence["id"] in str(package)

    runtime.run(exercise())


@pytest.mark.parametrize("late_failure", [True, False])
def test_cancellation_wins_over_provider_return(runtime, monkeypatch, late_failure):
    async def exercise():
        task = await runtime.task()
        tool = await runtime.tool(task)
        started, released = asyncio.Event(), asyncio.Event()
        stop = asyncio.Event()
        async with sessionmanager.session() as db:
            persistent_id = await db.scalar(
                select(PersistentJob.id).where(
                    PersistentJob.idempotency_key
                    == f"research-tool-job:{tool['tool_job']['id']}"
                )
            )

        async def select_fixture_job(db, **kwargs):
            return await claim_job(db, **kwargs, job_id=persistent_id)

        async def delayed_provider(*args, **kwargs):
            started.set()
            await released.wait()
            stop.set()
            if late_failure:
                raise ValueError("Injected late provider failure")
            return {"items": []}

        monkeypatch.setattr(research_tools, "execute_research_tool", delayed_provider)
        monkeypatch.setattr(resource_job_worker, "claim_job", select_fixture_job)
        worker = asyncio.create_task(
            resource_job_worker.run_persistent_job_worker(stop, poll_seconds=0.01)
        )
        await asyncio.wait_for(started.wait(), 10)
        try:
            await runtime.transition(task["id"], "cancel")
        finally:
            released.set()
        await worker
        cancelled = await runtime.json("GET", f"/research-tasks/{task['id']}")
        assert cancelled["status"] == cancelled["runs"][0]["status"] == "cancelled"
        assert cancelled["actions"][0]["status"] == "cancelled"
        assert not any(e["kind"] == "tool_job.completed" for e in cancelled["events"])
        async with sessionmanager.session() as db:
            persisted = await db.get(PersistentJob, persistent_id)
            assert persisted.status != "running" and persisted.lease_owner is None

    runtime.run(exercise())


def test_resume_with_ai_available_waits_for_existing_tool(runtime, monkeypatch):
    async def exercise():
        task = await runtime.task()
        await runtime.tool(task)
        paused = await runtime.transition(task["id"], "pause")
        generation = paused["runs"][0]["advance_generation"]
        monkeypatch.setattr(config, "AI_ENABLED", True)
        monkeypatch.setattr(
            config, "DASHSCOPE_API_KEY", "integration-fake-key-not-a-credential"
        )
        resumed = await runtime.transition(task["id"], "resume")
        assert resumed["runs"][0]["status"] == "waiting_for_tool"
        assert resumed["runs"][0]["advance_generation"] == generation
        await runtime.transition(task["id"], "cancel")

    runtime.run(exercise())


def test_final_attempt_crash_is_reconciled_once_without_reexecution(runtime):
    async def exercise():
        task = await runtime.task()
        tool = await runtime.tool(task)
        async with sessionmanager.session() as db:
            job = await db.scalar(
                select(PersistentJob).where(
                    PersistentJob.idempotency_key
                    == f"research-tool-job:{tool['tool_job']['id']}"
                )
            )
            # Fault injection: persisted state at process death after its final claim.
            job.max_attempts = job.attempts = 1
            job.status, job.lease_owner = "running", "dead-worker"
            job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            action = await db.get(ResearchAction, UUID(tool["id"]))
            typed = await db.get(ResearchToolJob, UUID(tool["tool_job"]["id"]))
            action.status = typed.status = "running"
            await db.commit()
        async with sessionmanager.session() as restarted:
            assert await reconcile_exhausted_jobs(restarted) == 1
            await restarted.commit()
        async with sessionmanager.session() as restarted:
            assert await reconcile_exhausted_jobs(restarted) == 0
        stopped = await runtime.json("GET", f"/research-tasks/{task['id']}")
        assert stopped["status"] == stopped["runs"][0]["status"] == "paused"
        assert stopped["actions"][0]["status"] == "failed"
        assert "uncertain" in stopped["runs"][0]["last_error"]

    runtime.run(exercise())


@pytest.mark.parametrize("limit", ["time", "budget"])
def test_limits_rechecked_after_queueing(runtime, limit):
    async def exercise():
        task = await runtime.task(budget_limit="1", budget_currency="USD")
        tool = await runtime.tool(task)
        async with sessionmanager.session() as db:
            stored = await db.get(ResearchTask, UUID(task["id"]))
            if limit == "time":
                stored.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
            else:
                db.add(
                    ResearchBudgetEntry(
                        task_id=stored.id,
                        kind="expense",
                        amount=Decimal(1),
                        currency="USD",
                        command_digest="a" * 64,
                        idempotency_key=uuid4().hex,
                    )
                )
            await db.commit()
        assert await runtime.dispatch(tool) == ("pending", 0)
        paused = await runtime.json("GET", f"/research-tasks/{task['id']}")
        assert paused["status"] == "paused" and paused["outcome"] == f"stopped_{limit}"
        assert paused["actions"][0]["status"] == "queued"

    runtime.run(exercise())


def test_current_membership_is_required_at_dispatch(runtime):
    async def exercise():
        task = await runtime.task()
        tool = await runtime.tool(task)
        async with sessionmanager.session() as db:
            membership = await db.scalar(
                select(LabUser).where(
                    LabUser.lab_id == UUID(task["lab_id"]),
                    LabUser.user_id == UUID(task["owner_user_id"]),
                )
            )
            original = membership.as_dict()
            await db.delete(membership)
            await db.commit()
        try:
            assert await runtime.dispatch(tool) == ("pending", 0)
        finally:
            async with sessionmanager.session() as db:
                db.add(LabUser(**original))
                await db.commit()
        paused = await runtime.json("GET", f"/research-tasks/{task['id']}")
        assert paused["status"] == "paused"
        assert "permission was revoked" in paused["runs"][0]["last_error"]

    runtime.run(exercise())


def test_human_submission_validation_review_and_finalization_without_ai(runtime):
    async def exercise():
        task = await runtime.task()
        action = await runtime.confirm(
            f"/research-tasks/{task['id']}/human-actions",
            {
                "idempotency_key": uuid4().hex,
                "request": {
                    "title": "Read instrument display",
                    "instructions": "Record the displayed temperature",
                    "fields": [
                        {
                            "key": "temperature",
                            "label": "Temperature",
                            "value_type": "number",
                            "unit": "C",
                        }
                    ],
                },
            },
        )
        work = action["work_item"]
        url = f"/research-work-items/{work['id']}"
        await runtime.json(
            "POST",
            url + "/submission/preview",
            {
                "expected_revision": work["revision"],
                "values": {"temperature": "not-a-number"},
            },
            status=422,
        )
        submitted = await runtime.confirm(
            url + "/submission",
            {
                "expected_revision": work["revision"],
                "values": {"temperature": 23.5},
            },
        )
        assert submitted["status"] == "submitted"
        reviewed = await runtime.confirm(
            url + "/review",
            {
                "expected_revision": submitted["revision"],
                "expected_action_revision": submitted["action"]["revision"],
                "decision": "accept",
                "reason": "Checked against the recorded display",
            },
        )
        assert (
            reviewed["status"] == "accepted"
            and reviewed["action"]["status"] == "completed"
        )
        completed = await runtime.transition(
            task["id"],
            "complete",
            outcome="inconclusive",
            scientific_outcome="inconclusive",
            conclusion="One verified observation is insufficient for the research goal.",
        )
        assert completed["status"] == "completed"
        package = await runtime.json(
            "GET", f"/research-tasks/{task['id']}/result-package"
        )
        assert "23.5" in str(package) and "validated" in str(package)

    runtime.run(exercise())


def test_specialist_output_cannot_enter_evidence_api(runtime, monkeypatch):
    from app.services import research_specialists

    async def provider(*args, **kwargs):
        return {
            "summary": "No empirical conclusion is possible from the task description alone."
        }

    monkeypatch.setattr(config, "AI_ENABLED", True)
    monkeypatch.setattr(
        config, "DASHSCOPE_API_KEY", "integration-fake-key-not-a-credential"
    )
    monkeypatch.setattr(research_specialists, "aira_structured_proposal", provider)

    async def exercise():
        task = await runtime.task(tool_keys=["aira.specialist"])
        tool = await runtime.tool(
            task,
            "aira.specialist",
            {"role": "research_critic", "question": "Assess the available sources"},
        )
        assert await runtime.dispatch(tool) == ("succeeded", 1)
        await runtime.json(
            "POST",
            "/research-assets/evidence/preview",
            {
                "task_id": task["id"],
                "run_id": task["runs"][0]["id"],
                "action_id": tool["id"],
                "artifact_type": "action_output",
                "artifact_id": tool["id"],
                "kind": "analysis",
            },
            status=409,
        )
        # A pre-fix pending Evidence/snapshot must not bypass the new review gate.
        async with sessionmanager.session() as db:
            stored = await db.get(ResearchAction, UUID(tool["id"]))
            digest = action_output_digest(
                {
                    "schema": "airalogy.research-action-output.v1",
                    "task_id": task["id"],
                    "run_id": str(stored.run_id),
                    "action_id": str(stored.id),
                    "action_revision": stored.revision,
                    "action_kind": stored.kind,
                    "output_data": stored.output_data,
                }
            )
            db.add(
                ResearchActionOutputSnapshot(
                    task_id=UUID(task["id"]),
                    run_id=stored.run_id,
                    action_id=stored.id,
                    action_revision=stored.revision,
                    action_kind=stored.kind,
                    output_data=stored.output_data,
                    digest=digest,
                    created_by_user_id=UUID(task["owner_user_id"]),
                )
            )
            evidence = ResearchEvidence(
                task_id=UUID(task["id"]),
                run_id=stored.run_id,
                action_id=stored.id,
                kind="analysis",
                artifact_type="action_output",
                artifact_id=str(stored.id),
                artifact_version=digest,
                quality_state="pending",
                created_by_user_id=UUID(task["owner_user_id"]),
            )
            db.add(evidence)
            await db.commit()
            evidence_id = str(evidence.id)
        await runtime.json(
            "POST",
            f"/research-assets/evidence/{evidence_id}/review",
            {
                "expected_quality_state": "pending",
                "quality_state": "validated",
            },
            status=409,
        )
        rejected = await runtime.json(
            "POST",
            f"/research-assets/evidence/{evidence_id}/review",
            {
                "expected_quality_state": "pending",
                "quality_state": "rejected",
            },
        )
        assert rejected["quality_state"] == "rejected"

    runtime.run(exercise())
