"""Disposable real-API policy test. Synthetic fixtures are not physical acceptance."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx

from app.database import sessionmanager
from app.main import app
from app.models.instrument_activation import InstrumentJobActivation
from app.models.research_execution import ResearchInstrumentJob
from app.models.resource import Resource
from app.services.research_instruments import (
    gateway_token_digest,
    generate_gateway_token,
)


def exercise_managed_activation(
    runtime,
    tmp_path,
    monkeypatch,
    *,
    file_outputs=False,
    cancel_before_finalize=False,
    sdk_delivery=False,
    http_reader=None,
):
    sdk_root = Path(__file__).resolve().parents[3] / "apps/instrument-gateway"
    monkeypatch.syspath_prepend(str(sdk_root / "src"))
    monkeypatch.syspath_prepend(str(sdk_root / "tests"))
    from airalogy_instrument_gateway.installation_manager import (
        apply,
        prepare,
        read_request,
    )
    from airalogy_instrument_gateway.package_contract import sha256
    from airalogy_instrument_gateway.security import verify_job_signature
    from managed_fixture import TARGET, package
    from test_package_installation import sdk

    from tests.test_instrument_qualifications import report

    raw, wheel = package(physical_policy=True, file_outputs=file_outputs), sdk()
    target = TARGET
    command_key, arguments = "reader.measure", {"sample_count": 2}
    platform_url, configuration = "http://127.0.0.1", b"{}"
    if http_reader:
        from airalogy_instrument_gateway.package_contract import canonical
        from http_reader_fixture import TARGET as HTTP_TARGET
        from http_reader_fixture import package as http_package
        from test_http_read import config as http_config

        raw, target = http_package(physical_policy=True), HTTP_TARGET
        command_key, arguments = "reader.result.read", {"sample_id": "sample-A"}
        platform_url = http_reader["platform_url"]
        configuration = canonical(http_config(http_reader["port"]))
    root = tmp_path.resolve() / "managed-station"
    root.mkdir(mode=0o700)
    for name, value in (
        ("package.zip", raw),
        ("sdk.whl", wheel),
        ("config.json", configuration),
    ):
        (root / name).write_bytes(value)
    (root / "config.json").chmod(0o600)

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
                "code": "managed_" + uuid4().hex,
                "name": "Synthetic managed policy fixture",
                "capabilities": {"booking": True},
                "booking_policy": "auto",
            },
        )
        resource = await runtime.json(
            "POST",
            base + "/resources",
            {
                "resource_type_id": kind["id"],
                "name": "Synthetic managed fixture — not real equipment",
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
        station = await runtime.confirm(
            "/research-instrument-gateways",
            {"lab_id": lab, "name": "Managed " + uuid4().hex, "enabled": False},
        )
        gateway, token = station["gateway"], generate_gateway_token()
        pairing = await runtime.confirm(
            "/instrument-pairings",
            {
                "gateway_id": gateway["id"],
                "expected_revision": gateway["revision"],
                "reason": "Synthetic two-sided pairing",
            },
        )
        await runtime.json(
            "POST",
            "/instrument-pairings/claim",
            {
                "code": pairing["code"],
                "gateway_id": gateway["id"],
                "lab_id": lab,
                "client_name": "Synthetic local station",
                "credential_digest": gateway_token_digest(token),
                "credential_hint": token[-8:],
            },
        )
        pair_url = f"/instrument-pairings/{pairing['pairing']['id']}"
        pair_preview = await runtime.json("POST", pair_url + "/preview")
        await runtime.json(
            "POST",
            pair_url + "/confirm",
            {"preview_digest": pair_preview["preview_digest"]},
        )
        release_id = str(uuid4())
        params, headers = (
            {"lab_id": lab, "request_id": release_id},
            {"Content-Type": "application/zip"},
        )
        preview = await runtime.client.post(
            "/instrument-adapter-packages/preview",
            params=params,
            headers=headers,
            content=raw,
        )
        assert preview.status_code == 200, preview.text
        saved = await runtime.client.post(
            "/instrument-adapter-packages",
            params=params,
            headers={
                **headers,
                "X-Airalogy-Preview-Digest": preview.json()["preview_digest"],
            },
            content=raw,
        )
        assert saved.status_code == 200, saved.text
        release_id = saved.json()["id"]
        if saved.json()["state"] == "imported":
            await runtime.confirm(
                f"/instrument-adapter-packages/{release_id}/review",
                {
                    "expected_revision": saved.json()["revision"],
                    "operation": "approve_source",
                    "source_reviewed": True,
                    "reason": "Disposable synthetic policy fixture",
                },
            )
        else:
            assert saved.json()["state"] == "approved"
        path = root / "private.json"
        public = prepare(
            destination=path,
            platform_url=platform_url,
            lab_id=lab,
            gateway_id=gateway["id"],
            package=root / "package.zip",
            sdk_wheel=root / "sdk.whl",
            trusted_sdk_digest=sha256(wheel),
            config=root / "config.json",
            root=root,
        )
        await runtime.confirm(
            "/instrument-installations",
            {
                "request": public,
                "resource_id": resource["id"],
                "release_id": release_id,
                "reason": "Synthetic software policy acceptance",
                "fingerprint_confirmed": True,
            },
        )
        binding_url = f"/instrument-installations/{public['id']}"
        listing = f"/instrument-installations?gateway_id={gateway['id']}&resource_id={resource['id']}"
        assert [
            item["id"] for item in (await runtime.json("GET", listing))["items"]
        ] == [public["id"]]
        # Archived equipment stays manageable in history; it is not a new target.
        async with sessionmanager.session() as db:
            row = await db.get(Resource, UUID(resource["id"]))
            row.archived_at = datetime.now(UTC)
            await db.commit()
        try:
            assert [
                item["id"] for item in (await runtime.json("GET", listing))["items"]
            ] == [public["id"]]
            choices = await runtime.json(
                "GET",
                f"/research-instrument-gateways/{gateway['id']}/equipment-options?resource_id={resource['id']}",
            )
            assert choices["items"] == []
            unscoped = await runtime.json(
                "GET", f"/instrument-installations?gateway_id={gateway['id']}"
            )
            assert [item["id"] for item in unscoped["items"]] == [public["id"]]
        finally:
            async with sessionmanager.session() as db:
                row = await db.get(Resource, UUID(resource["id"]))
                row.archived_at = None
                await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as local:
            loop = asyncio.get_running_loop()

            async def install_call(operation, payload):
                result = await local.post(
                    binding_url + "/" + operation,
                    headers={
                        "X-Airalogy-Installation-Token": read_request(path)[
                            "installation_token"
                        ]
                    },
                    json=payload or {},
                )
                assert result.status_code == 200, result.text
                return result.content if operation == "package" else result.json()

            class Bridge:
                def call(self, operation, payload=None):
                    return asyncio.run_coroutine_threadsafe(
                        install_call(operation, payload), loop
                    ).result(timeout=30)

            await asyncio.to_thread(apply, path, source_reviewed=True, client=Bridge())
            qdraft = report()
            qdraft.update(
                scope="read_only",
                target=target,
                independent_review_confirmed=True,
                physical_tests_authorized=True,
            )
            qdraft["commands"][0]["key"] = command_key
            qualified = await runtime.confirm(binding_url + "/qualifications", qdraft)
            assert qualified["effective_state"] == "qualified"
            activation_url = binding_url + "/activations"

            def draft(previous=None):
                return {
                    "id": str(uuid4()),
                    "qualification_id": qualified["id"],
                    "expected_active_id": previous,
                    "commands": [f"{command_key}@1.0.0"],
                    "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    "reason": "Synthetic software activation test, no hardware",
                    "activation_confirmed": True,
                }

            first = draft()
            preview = await runtime.json("POST", activation_url + "/preview", first)
            await runtime.json(
                "POST",
                activation_url,
                {
                    **first,
                    "reason": "changed",
                    "preview_digest": preview["preview_digest"],
                },
                status=409,
            )
            active = await runtime.json(
                "POST",
                activation_url,
                {**first, "preview_digest": preview["preview_digest"]},
            )
            assert active["effective_state"] == "authorized"
            assert (
                await runtime.json(
                    "POST",
                    activation_url,
                    {**first, "preview_digest": preview["preview_digest"]},
                )
            )["id"] == active["id"]
            local.headers["X-Airalogy-Gateway-Token"] = token
            snapshot = (await local.get("/instrument-gateway/v1/activation")).json()
            verify_job_signature(snapshot["activation"], snapshot["signature"], token)
            assert snapshot["activation"]["pin"] == active["pin"]
            assert (
                await local.post("/instrument-gateway/v1/jobs/lease")
            ).status_code == 409
            assert (
                await local.post(
                    "/instrument-gateway/v1/jobs/lease",
                    json={"activation": {**active["pin"], "id": str(uuid4())}},
                )
            ).status_code == 409
            booking = await runtime.json(
                "POST",
                base + "/bookings",
                {
                    "resource_id": resource["id"],
                    "starts_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                    "ends_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    "purpose": "Disposable managed software test",
                    "idempotency_key": uuid4().hex,
                },
            )

            async def queue():
                task = await runtime.task(resource_type_ids=[kind["id"]])
                available = await runtime.json(
                    "GET", f"/research-instrument-commands?task_id={task['id']}"
                )
                assert any(
                    item["id"] == active["commands"][0]["id"]
                    for item in available["items"]
                )
                return await runtime.confirm(
                    f"/research-tasks/{task['id']}/instrument-actions",
                    {
                        "command_id": active["commands"][0]["id"],
                        "equipment_booking_id": booking["id"],
                        "arguments": arguments,
                        "idempotency_key": uuid4().hex,
                    },
                )

            created = await queue()
            job = created["instrument_job"]
            if http_reader:
                from tests.http_read_acceptance import run_installed_http_reader

                await run_installed_http_reader(
                    runtime, root, snapshot["activation"], token, job, http_reader
                )
                return
            if sdk_delivery:
                from tests.instrument_output_acceptance import exercise_sdk_delivery

                await exercise_sdk_delivery(
                    runtime, local, root, snapshot["activation"], token, job
                )
                return
            if file_outputs:
                old = await local.post(
                    "/instrument-gateway/v1/jobs/lease",
                    json={"activation": active["pin"]},
                )
                assert old.status_code == 409 and "file delivery" in old.text
            async with sessionmanager.session() as db:
                pinned = await db.get(InstrumentJobActivation, UUID(job["id"]))
                assert pinned.pin == active["pin"]
            lease = await local.post(
                "/instrument-gateway/v1/jobs/lease",
                json={
                    "activation": active["pin"],
                    "file_delivery_version": "airalogy.instrument-output-plan.v1",
                },
            )
            assert lease.status_code == 200, lease.text
            leased = lease.json()
            assert leased["job"]["activation"] == active["pin"]
            verify_job_signature(leased["job"], leased["signature"], token)
            local.headers["X-Airalogy-Instrument-Lease"] = leased["lease_token"]
            job_url = f"/instrument-gateway/v1/jobs/{job['id']}"
            assert (await local.post(job_url + "/start", json={})).status_code == 409
            started = await local.post(
                job_url + "/start", json={"activation": active["pin"]}
            )
            assert started.status_code == 200, started.text
            # A running or uncertain job prevents changing drivers.
            change = draft(active["id"])
            change_preview = await runtime.json(
                "POST", activation_url + "/preview", change
            )
            await runtime.json(
                "POST",
                activation_url,
                {**change, "preview_digest": change_preview["preview_digest"]},
                status=409,
            )
            result = await local.post(
                job_url + "/complete",
                json={
                    "result": {
                        "value": 0.84,
                        "unit": "synthetic_unit",
                        "simulation_only": True,
                    }
                },
            )
            assert result.status_code == 200, result.text
            if file_outputs:
                assert result.json()["files_pending"] is True
                from tests.instrument_output_acceptance import exercise_outputs

                await exercise_outputs(
                    runtime,
                    local,
                    leased,
                    root,
                    monkeypatch,
                    cancel_before_finalize=cancel_before_finalize,
                )
                return
            async with sessionmanager.session() as db:
                assert (
                    await db.get(ResearchInstrumentJob, UUID(job["id"]))
                ).status == "completed"
            stale = await queue()
            second = await runtime.confirm(activation_url, change)
            assert (
                second["commands"][0]["revision"]
                == active["commands"][0]["revision"] + 1
            )
            assert (
                await local.post(
                    "/instrument-gateway/v1/jobs/lease",
                    json={"activation": active["pin"]},
                )
            ).status_code == 409
            current = await local.post(
                "/instrument-gateway/v1/jobs/lease", json={"activation": second["pin"]}
            )
            assert current.status_code == 200 and current.json()["job"] is None, (
                current.text
            )
            async with sessionmanager.session() as db:
                assert (
                    await db.get(
                        ResearchInstrumentJob, UUID(stale["instrument_job"]["id"])
                    )
                ).status == "failed"
            # Retrying an old confirmation cannot reactivate a superseded grant.
            old = await runtime.json(
                "POST",
                activation_url,
                {**first, "preview_digest": preview["preview_digest"]},
            )
            assert old["effective_state"] == "revoked"
            assert (await runtime.json("GET", activation_url))["current_id"] == second[
                "id"
            ]
            await runtime.confirm(
                activation_url + f"/{second['id']}/revoke",
                {"expected_revision": 1, "reason": "End synthetic acceptance"},
            )
            assert (await local.get("/instrument-gateway/v1/activation")).json()[
                "activation"
            ] is None
            assert (
                await local.post(
                    "/instrument-gateway/v1/jobs/lease",
                    json={"activation": second["pin"]},
                )
            ).status_code == 403
            # Rollback is a fresh checked grant, never restoration of an old token.
            rollback = await runtime.confirm(activation_url, draft())
            assert rollback["id"] not in {active["id"], second["id"]}
            assert (
                rollback["commands"][0]["revision"]
                == second["commands"][0]["revision"] + 1
            )
            active = rollback
            running = await queue()
            leased_response = await local.post(
                "/instrument-gateway/v1/jobs/lease", json={"activation": active["pin"]}
            )
            assert leased_response.status_code == 200, leased_response.text
            local.headers["X-Airalogy-Instrument-Lease"] = leased_response.json()[
                "lease_token"
            ]
            running_url = (
                f"/instrument-gateway/v1/jobs/{running['instrument_job']['id']}"
            )
            assert (
                await local.post(
                    running_url + "/start", json={"activation": active["pin"]}
                )
            ).status_code == 200
            await runtime.confirm(
                binding_url + f"/qualifications/{qualified['id']}/revoke",
                {"expected_revision": 1, "reason": "Withdraw fixture evidence"},
            )
            assert (await local.get("/instrument-gateway/v1/activation")).json()[
                "activation"
            ] is None
            heartbeat = await local.post(running_url + "/heartbeat")
            assert (
                heartbeat.status_code == 200 and heartbeat.json()["stop_requested"]
            ), heartbeat.text
            assert "qualification" in heartbeat.json()["reason"].lower()
            stopped = await local.post(
                running_url + "/stopped",
                json={"reason": "Synthetic stop confirmed after evidence withdrawal"},
            )
            assert stopped.status_code == 200, stopped.text
            async with sessionmanager.session() as db:
                assert (
                    await db.get(
                        ResearchInstrumentJob, UUID(running["instrument_job"]["id"])
                    )
                ).status == "stopped"

    runtime.run(exercise())
