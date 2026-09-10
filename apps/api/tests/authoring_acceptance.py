"""Real private API/DB authoring lifecycle; synthetic model and sandbox responses."""

import asyncio
import copy
import json
import os
import subprocess
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx

from app.config import config
from app.database import sessionmanager
from app.libs import masterbrain
from app.main import app
from app.models.instrument_authoring import (
    InstrumentAuthoringSession,
    InstrumentAuthoringTurn,
)


def exercise_authoring(runtime, tmp_path, monkeypatch):
    sdk_root = Path(__file__).resolve().parents[3] / "apps/instrument-gateway"
    monkeypatch.syspath_prepend(str(sdk_root / "src"))
    monkeypatch.syspath_prepend(str(sdk_root / "tests"))
    from airalogy_instrument_gateway.authoring import prepare, read_request, run
    from airalogy_instrument_gateway.package_contract import sha256
    from test_package_authoring import fixture_test, proposal, spec
    from test_package_installation import sdk

    root = tmp_path.resolve() / "private-authoring"
    root.mkdir(mode=0o700)
    wheel = sdk()
    (root / "sdk.whl").write_bytes(wheel)
    (root / "spec.json").write_text(json.dumps(spec()))
    calls, gate = [], None

    async def provider_stream(endpoint, payload, **kwargs):
        # Keep actual Aira JSON transport, validation, usage context and API writes.
        # Substitute only the external model's token stream; no paid requests.
        calls.append((endpoint, payload, kwargs))
        if gate:
            await gate.wait()
        text = json.dumps(proposal(broken=len(calls) == 1))
        for offset in range(0, len(text), 100):
            yield text[offset : offset + 100]

    monkeypatch.setattr(masterbrain, "stream_request", provider_stream)
    monkeypatch.setattr(config, "AI_ENABLED", False)

    async def setup():
        base = f"/labs/{runtime.seed['lab']['id']}/resource-library"
        definitions = await runtime.json("GET", base + "/definition-versions")
        definition = next(
            d
            for d in definitions["items"]
            if d["protocol_uid"] == "plasmid_resource_definition_en"
        )
        kind = await runtime.json(
            "POST",
            base + "/types",
            {
                "protocol_version_id": definition["id"],
                "code": "author_" + uuid4().hex,
                "name": "Synthetic authoring equipment",
                "capabilities": {"booking": True},
                "booking_policy": "auto",
            },
        )
        resource = await runtime.json(
            "POST",
            base + "/resources",
            {
                "resource_type_id": kind["id"],
                "name": "Synthetic authoring target",
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
                {
                    "lab_id": runtime.seed["lab"]["id"],
                    "name": "Source author " + uuid4().hex,
                    "enabled": False,
                },
            )
        )["gateway"]
        prepared = prepare(
            workspace=root,
            platform_url="http://127.0.0.1/api",
            gateway_id=gateway["id"],
            resource_id=resource["id"],
            spec=root / "spec.json",
            sdk_wheel=root / "sdk.whl",
            trusted_sdk_digest=sha256(wheel),
            image="sha256:" + "1" * 64,
        )
        content = read_request(prepared["request_file"])
        draft = {
            "request": content["request"],
            "reason": "Synthetic API authoring acceptance",
            "model_processing_consent": True,
        }
        await runtime.json("POST", "/instrument-authoring/preview", draft, status=409)
        monkeypatch.setattr(config, "AI_ENABLED", True)
        monkeypatch.setattr(config, "MASTERBRAIN_CALL_MODE", "external")
        monkeypatch.setattr(
            config, "CHAT_API_ENDPOINT", "http://synthetic-model.invalid"
        )
        await runtime.json(
            "POST",
            "/instrument-authoring/preview",
            {**draft, "model_processing_consent": False},
            status=422,
        )
        preview = await runtime.json("POST", "/instrument-authoring/preview", draft)
        await runtime.json(
            "POST",
            "/instrument-authoring",
            {
                **draft,
                "reason": "unreviewed",
                "preview_digest": preview["preview_digest"],
            },
            status=409,
        )
        approved = {**draft, "preview_digest": preview["preview_digest"]}
        results = await asyncio.gather(
            *(
                runtime.client.post("/instrument-authoring", json=approved)
                for _ in range(2)
            )
        )
        assert [r.status_code for r in results] == [200, 200]
        row = results[0].json()
        assert row["id"] == content["request"]["id"]
        assert content["authoring_token"] not in json.dumps(row)
        return content, prepared, draft, gateway

    content, prepared, draft, gateway = runtime.run(setup())
    sid = content["request"]["id"]
    headers = {"X-Airalogy-Authoring-Token": content["authoring_token"]}

    class APIClient:
        def call(self, operation, payload=None, *, turn_id=None):
            async def send():
                suffix = (
                    f"turns/{turn_id}/report" if operation == "report" else operation
                )
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.post(
                        f"/instrument-authoring/{sid}/{suffix}",
                        headers=headers,
                        json=payload or {},
                    )
                assert response.status_code == 200, response.text
                return response.json()

            return runtime.run(send())

    outcome = run(prepared["request_file"], client=APIClient(), tester=fixture_test)
    assert outcome["state"] == "draft_tested"
    assert Path(outcome["package"]).is_file()
    assert len(calls) == 2
    assert (
        calls[0][2]["usage_context"].operation_id
        != calls[1][2]["usage_context"].operation_id
    )
    assert "package_tests" in calls[1][1]["messages"][0]["content"]
    assert (
        run(prepared["request_file"], client=APIClient(), tester=fixture_test)
        == outcome
    )
    assert len(calls) == 2

    async def policies():
        nonlocal sid, gate
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as local:
            response = await local.post(
                f"/instrument-authoring/{sid}/status",
                headers={"X-Airalogy-Authoring-Token": "aigw_" + "A" * 43},
            )
            assert response.status_code == 401
            response = await local.get(
                f"/research-instrument-gateways/{gateway['id']}/commands",
                headers=headers,
            )
            assert response.status_code in (401, 403)
            status = (
                await local.post(f"/instrument-authoring/{sid}/status", headers=headers)
            ).json()
            previous = status["turns"][-1]
            response = await local.post(
                f"/instrument-authoring/{sid}/turns",
                headers=headers,
                json={"id": str(uuid4()), "previous_id": previous["id"]},
            )
            assert response.status_code == 409  # A passing draft cannot keep spending.
            changed = {**previous["report"], "archive_digest": "9" * 64}
            response = await local.post(
                f"/instrument-authoring/{sid}/turns/{previous['id']}/report",
                headers=headers,
                json=changed,
            )
            assert response.status_code == 409
            # Independently authorized short-lived session for concurrent call/cancel.
            request = copy.deepcopy(content["request"])
            request["id"] = str(uuid4())
            from app.services.instrument_authoring_contract import fingerprint

            request["fingerprint"] = fingerprint(request)
            row = await runtime.confirm(
                "/instrument-authoring", {**draft, "request": request}
            )
            sid = row["id"]
            gate = asyncio.Event()
            turn = {"id": str(uuid4()), "previous_id": None}
            pending = asyncio.create_task(
                local.post(
                    f"/instrument-authoring/{sid}/turns", headers=headers, json=turn
                )
            )
            for _ in range(100):
                await asyncio.sleep(0.01)
                if len(calls) == 3:
                    break
            assert len(calls) == 3
            repeat = await local.post(
                f"/instrument-authoring/{sid}/turns", headers=headers, json=turn
            )
            assert repeat.status_code == 200 and repeat.json()["state"] == "generating"
            assert len(calls) == 3
            await runtime.json(
                "POST",
                f"/instrument-authoring/{sid}/cancel",
                {
                    "request_fingerprint": request["fingerprint"],
                    "reason": "Cancel in-flight synthetic model",
                },
            )
            gate.set()
            assert (await pending).status_code == 409
            async with sessionmanager.session() as db:
                saved = await db.get(InstrumentAuthoringTurn, UUID(turn["id"]))
                assert saved.proposal is None  # Cancellation cannot resurrect output.
            assert (
                await local.post(
                    f"/instrument-authoring/{sid}/turns",
                    headers=headers,
                    json={"id": str(uuid4()), "previous_id": turn["id"]},
                )
            ).status_code == 409
            # Expiry/source drift/AI unavailability all fail before provider calls.
            for condition in ("expired", "scope", "transport", "ai", "budget"):
                request["id"] = str(uuid4())
                request["fingerprint"] = fingerprint(request)
                row = await runtime.confirm(
                    "/instrument-authoring",
                    {**draft, "request": copy.deepcopy(request)},
                )
                async with sessionmanager.session() as db:
                    grant = await db.get(InstrumentAuthoringSession, UUID(row["id"]))
                    if condition == "expired":
                        grant.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                    elif condition == "scope":
                        grant.scope_pin = {**grant.scope_pin, "gateway_revision": -1}
                    elif condition == "budget":
                        for i in range(1, 4):
                            db.add(
                                InstrumentAuthoringTurn(
                                    id=uuid4(),
                                    session_id=grant.id,
                                    ordinal=i,
                                    previous_id=None,
                                    state="failed",
                                    operation_id=f"synthetic-{i}",
                                    deadline=datetime.now(UTC),
                                    error="model_unavailable",
                                )
                            )
                    await db.commit()
                if condition == "ai":
                    monkeypatch.setattr(config, "AI_ENABLED", False)
                if condition == "transport":
                    monkeypatch.setattr(
                        config, "CHAT_API_ENDPOINT", "http://changed-model.invalid"
                    )
                before = len(calls)
                response = await local.post(
                    f"/instrument-authoring/{row['id']}/status", headers=headers
                )
                latest = response.json()["turns"]
                response = await local.post(
                    f"/instrument-authoring/{row['id']}/turns",
                    headers=headers,
                    json={
                        "id": str(uuid4()),
                        "previous_id": latest[-1]["id"] if latest else None,
                    },
                )
                assert response.status_code == 409, response.text
                assert len(calls) == before
                monkeypatch.setattr(config, "AI_ENABLED", True)
                monkeypatch.setattr(
                    config, "CHAT_API_ENDPOINT", "http://synthetic-model.invalid"
                )
            viewer = next(a for a in runtime.seed["accounts"] if a["key"] == "viewer")
            login = await local.post(
                "/signin_by_email",
                json={"email": viewer["email"], "password": viewer["password"]},
            )
            response = await local.get(
                f"/instrument-authoring/{sid}",
                headers={"Auth-Token": login.json()["token"]},
            )
            assert response.status_code == 403
        commands = await runtime.json(
            "GET", f"/research-instrument-gateways/{gateway['id']}/commands"
        )
        assert commands["items"] == []

    runtime.run(policies())
    gate = None
    exercise_authoring_browser(runtime, tmp_path, monkeypatch, draft, sdk_root)


def exercise_authoring_browser(runtime, tmp_path, monkeypatch, draft, sdk_root):
    """Actual browser/local server/API/DB; only model and sandbox outcomes injected."""
    from airalogy_instrument_gateway import authoring
    from airalogy_instrument_gateway.authoring_workspace import AuthoringWorkspace
    from airalogy_instrument_gateway.package_contract import sha256
    from airalogy_instrument_gateway.setup_cli import SetupServer
    from test_package_authoring import fixture_test, spec
    from test_package_installation import sdk

    root = tmp_path.resolve() / "private-authoring-browser"
    root.mkdir(mode=0o700)
    wheel = sdk()
    (root / "sdk.whl").write_bytes(wheel)
    (root / "spec.json").write_text(json.dumps(spec()))
    workspace = AuthoringWorkspace(root)
    server = SetupServer(workspace)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    repository = sdk_root.parents[1]

    def browser(stage):
        value = {
            "stage": stage,
            "root": str(root),
            "url": server.url,
            "screenshot": str(root / "synthetic-development-mobile.png"),
            "fields": {
                "platform_url": "http://127.0.0.1/api",
                "gateway_id": draft["request"]["gateway_id"],
                "resource_id": draft["request"]["resource_id"],
                "trusted_sdk_digest": sha256(wheel),
                "image": "sha256:" + "1" * 64,
                "max_iterations": 3,
                "duration_seconds": 900,
                "timeout_seconds": 30,
            },
            "files": {
                "spec": str(root / "spec.json"),
                "sdk_wheel": str(root / "sdk.whl"),
            },
        }
        result = subprocess.run(
            ["node", "tests/e2e/scripts/local-authoring-browser.mjs"],
            cwd=repository,
            env={**os.environ, "AIRALOGY_SYNTHETIC_BROWSER_INPUT": json.dumps(value)},
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    try:
        request = browser("prepare")
        runtime.run(
            runtime.confirm("/instrument-authoring", {**draft, "request": request})
        )
        path = root / request["id"] / "request.json"
        content = authoring.read_request(path)

        class APIClient:
            def call(self, operation, payload=None, *, turn_id=None):
                async def send():
                    suffix = (
                        f"turns/{turn_id}/report"
                        if operation == "report"
                        else operation
                    )
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        response = await client.post(
                            f"/instrument-authoring/{request['id']}/{suffix}",
                            headers={
                                "X-Airalogy-Authoring-Token": content["authoring_token"]
                            },
                            json=payload or {},
                        )
                    assert response.status_code == 200, response.text
                    return response.json()

                return runtime.run(send())

        original = authoring.run
        with monkeypatch.context() as local:
            local.setattr(authoring, "AuthoringClient", lambda _: APIClient())
            local.setattr(
                authoring,
                "run",
                lambda path, **kwargs: original(
                    path, client=APIClient(), tester=fixture_test, **kwargs
                ),
            )
            downloaded = browser("run")
        workspace.worker.join(timeout=5)
        assert not workspace.worker.is_alive()
        snapshot = runtime.run(
            runtime.json("GET", f"/instrument-authoring/{request['id']}")
        )
        assert len(snapshot["turns"]) == 1
        assert snapshot["turns"][0]["report"]["archive_digest"] == downloaded["sha256"]
        assert not snapshot["hardware_authorized"]
    finally:
        workspace.pause()
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
