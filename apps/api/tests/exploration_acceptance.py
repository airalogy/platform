"""Actual API/DB + independent Node/browser or owned AppKit; synthetic model only."""

import asyncio
import copy
import json
import socket
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import uvicorn
from app.config import config
from app.database import sessionmanager
from app.libs import masterbrain
from app.main import app
from app.models.instrument_authoring import (
    InstrumentAuthoringSession,
    InstrumentAuthoringTurn,
)
from app.services.instrument_exploration import fingerprint

ROOT = Path(__file__).resolve().parents[3]


async def node(*arguments):
    process = await asyncio.create_subprocess_exec(
        "node",
        *map(str, arguments),
        cwd=ROOT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), 90)
    assert process.returncode == 0, stderr.decode()
    return json.loads(stdout)


async def target(runtime):
    base = f"/labs/{runtime.seed['lab']['id']}/resource-library"
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
            "code": "explore_" + uuid4().hex,
            "name": "Synthetic browser equipment",
            "capabilities": {"booking": True},
            "booking_policy": "auto",
        },
    )
    resource = await runtime.json(
        "POST",
        base + "/resources",
        {
            "resource_type_id": kind["id"],
            "name": "Synthetic interface target",
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
                "name": "Interface explorer " + uuid4().hex,
                "enabled": False,
            },
        )
    )["gateway"]
    return resource, gateway


def exercise_exploration(runtime, tmp_path, monkeypatch, *, native=False):
    calls, gate = [], None
    owned_process = None
    count_id = "sample_count" if native else "sample.count"
    result_id = "result" if native else "result.value"
    complete_state = "complete" if native else "completed"

    async def provider(endpoint, payload, **kwargs):
        calls.append((endpoint, payload, kwargs))
        if gate:
            await gate.wait()
        prompt = payload["messages"][0]["content"]
        observed = json.loads(
            next(
                line.split("=", 1)[1]
                for line in prompt.splitlines()
                if line.startswith("OBSERVATION=")
            )
        )
        proposal = {
            "kind": "finish" if observed["state"] == complete_state else "act",
            "action_index": None
            if observed["state"] == complete_state
            else 1
            if observed["values"][count_id] == "2"
            else 0,
            "summary": "Synthetic selected-control decision",
            "missing_information": [],
        }
        encoded = json.dumps(proposal)
        for start in range(0, len(encoded), 20):
            yield encoded[start : start + 20]

    monkeypatch.setattr(masterbrain, "stream_request", provider)
    monkeypatch.setattr(config, "AI_ENABLED", True)
    monkeypatch.setattr(config, "MASTERBRAIN_CALL_MODE", "external")
    monkeypatch.setattr(config, "CHAT_API_ENDPOINT", "http://synthetic-model.invalid")

    async def exercise():
        nonlocal gate, owned_process
        resource, gateway = await target(runtime)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen(16)
        address = f"http://127.0.0.1:{sock.getsockname()[1]}/"
        server = uvicorn.Server(
            uvicorn.Config(app, lifespan="off", log_level="error", access_log=False)
        )
        serving = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            for _ in range(200):
                if server.started:
                    break
                await asyncio.sleep(0.01)
            assert server.started
            if native:
                tmp_path.chmod(0o700)
                native_cli = "apps/instrument-interface/src/native-cli.mjs"
                built = await node(native_cli, "build", "--workspace", tmp_path)
                doctor = await node(
                    native_cli, "doctor", "--build", built["build_file"]
                )
                assert doctor["accessibility_trusted"] is True
                assert doctor["permissions_changed"] is False
                owned_process = await asyncio.to_thread(
                    subprocess.Popen,
                    [str(Path(built["simulator_app"]) / "Contents/MacOS/Simulator")],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                ready = await asyncio.wait_for(
                    asyncio.to_thread(owned_process.stdout.readline), 10
                )
                assert ready.startswith(b"SIMULATOR_READY")
                template = await node(
                    native_cli,
                    "simulation-template",
                    "--build",
                    built["build_file"],
                    "--pid",
                    owned_process.pid,
                    "--workspace",
                    tmp_path,
                )
                example = {
                    "definition": template["definition_file"],
                    "policy": template["policy_file"],
                }
            else:
                example = await node("scripts/instrument-interface-example.mjs")
            workspace = tmp_path / "private-exploration"
            workspace.mkdir(mode=0o700)
            cli = "apps/instrument-interface/src/exploration-cli.mjs"
            prepared = await node(
                cli,
                "prepare",
                "--definition",
                example["definition"],
                "--policy",
                example["policy"],
                "--workspace",
                workspace,
                "--platform-url",
                address,
                "--gateway-id",
                gateway["id"],
                "--resource-id",
                resource["id"],
            )
            content = json.loads(Path(prepared["request_file"]).read_text())
            request = content["request"]
            if native:
                assert request["spec"]["target"]["kind"] == "native_macos_simulation"
                assert built["simulator_app"] not in json.dumps(request)
                assert "started_seconds" not in json.dumps(request)
            draft = {
                "request": request,
                "reason": "Synthetic actual native/API acceptance"
                if native
                else "Synthetic actual browser/API acceptance",
                "model_processing_consent": True,
                "local_actions_reviewed": True,
            }
            monkeypatch.setattr(config, "AI_ENABLED", False)
            await runtime.json(
                "POST", "/instrument-exploration/preview", draft, status=409
            )
            monkeypatch.setattr(config, "AI_ENABLED", True)
            await runtime.json(
                "POST",
                "/instrument-exploration/preview",
                {**draft, "local_actions_reviewed": False},
                status=422,
            )
            preview = await runtime.json(
                "POST", "/instrument-exploration/preview", draft
            )
            await runtime.json(
                "POST",
                "/instrument-exploration",
                {
                    **draft,
                    "reason": "Changed reason",
                    "preview_digest": preview["preview_digest"],
                },
                status=409,
            )
            approved = {**draft, "preview_digest": preview["preview_digest"]}
            duplicate = await asyncio.gather(
                *(
                    runtime.client.post("/instrument-exploration", json=approved)
                    for _ in range(2)
                )
            )
            assert [response.status_code for response in duplicate] == [200, 200]
            assert content["token"] not in json.dumps(duplicate[0].json())
            outcome = await node(
                cli,
                "run",
                prepared["request_file"],
                "--confirm",
                prepared["local_preview_digest"],
            )
            assert outcome["state"] == "client_reported_success"
            assert outcome["hardware_qualified"] is False
            assert len(calls) == 3
            assert len({item[2]["usage_context"].operation_id for item in calls}) == 3
            history = await runtime.json(
                "GET", f"/instrument-exploration/{request['id']}"
            )
            assert history["effective_state"] == "cancelled"
            assert len(history["turns"]) == 3
            assert history["turns"][1]["report"]["after"]["values"][result_id] == "0.84"
            if native:
                assert "SYNTHETIC_PRIVATE" not in json.dumps(calls, default=str)
                assert "SYNTHETIC_PASSWORD" not in json.dumps(calls, default=str)
                assert built["simulator_app"] not in json.dumps(calls, default=str)
                # Independent read-only CLI, not the Aira completion claim.
                definition = json.loads(Path(example["definition"]).read_text())
                read_definition = {
                    "schema": "airalogy.native-read-definition.v1",
                    "id": "independent.acceptance",
                    "selection": definition["selection"],
                    "identity": definition["target"]["identity"],
                    "controls": [
                        next(
                            control
                            for control in definition["controls"]
                            if control["id"] == result_id
                        )
                    ],
                }
                read_file = tmp_path / "independent-read.json"
                read_file.write_text(json.dumps(read_definition))
                read_file.chmod(0o600)
                read_preview = await node(
                    native_cli, "preview", "--definition", read_file
                )
                readback = await node(
                    native_cli,
                    "read",
                    "--definition",
                    read_file,
                    "--confirm",
                    read_preview["sha256"],
                    "--evidence",
                    tmp_path,
                    "--ack-new-read",
                )
                assert (
                    json.loads(Path(readback["readback_file"]).read_text())[result_id]
                    == "0.84"
                )
                assert readback["actions_executed"] == 0
            assert history["turns"][2]["proposal"]["kind"] == "finish"
            assert all(
                item["input"]["observation"]["session_id"]
                == history["turns"][0]["input"]["observation"]["session_id"]
                for item in history["turns"]
            )
            # Recovery is real HTTP, uses saved reports, and cannot launch or spend a call.
            recovered = await node(cli, "sync", prepared["request_file"])
            assert (
                recovered["synced_reports"] == 2
                and recovered["browser_opened"] is False
            )
            assert len(calls) == 3
            assert recovered["native_actions_executed"] is False
            source_list = await runtime.json(
                "GET",
                f"/instrument-authoring?gateway_id={gateway['id']}&resource_id={resource['id']}",
            )
            assert source_list["items"] == []
            await runtime.json(
                "GET", f"/instrument-authoring/{request['id']}", status=404
            )
            assert (
                await runtime.json(
                    "GET", f"/research-instrument-gateways/{gateway['id']}/commands"
                )
            )["items"] == []
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as local:
                headers = {"X-Airalogy-Interface-Token": content["token"]}
                assert (
                    await local.post(
                        f"/instrument-authoring/{request['id']}/status",
                        headers={"X-Airalogy-Authoring-Token": content["token"]},
                    )
                ).status_code == 401
                assert (
                    await local.get(
                        f"/research-instrument-gateways/{gateway['id']}/commands",
                        headers=headers,
                    )
                ).status_code in (401, 403)
                viewer = next(
                    item for item in runtime.seed["accounts"] if item["key"] == "viewer"
                )
                login = await local.post(
                    "/signin_by_email",
                    json={"email": viewer["email"], "password": viewer["password"]},
                )
                response = await local.get(
                    f"/instrument-exploration/{request['id']}",
                    headers={"Auth-Token": login.json()["token"]},
                )
                assert response.status_code == 403
                # Fresh grant: reservation is idempotent and cancellation discards late output.
                fresh = copy.deepcopy(request)
                fresh["id"] = str(uuid4())
                fresh["fingerprint"] = fingerprint(fresh)
                await runtime.confirm(
                    "/instrument-exploration", {**draft, "request": fresh}
                )
                observation = history["turns"][0]["input"]["observation"]
                turn = {
                    "id": str(uuid4()),
                    "previous_id": None,
                    "observation": observation,
                    "evidence_digest": "9" * 64,
                }
                gate = asyncio.Event()
                url = f"/instrument-exploration/{fresh['id']}/turns"
                pending = asyncio.create_task(
                    local.post(url, headers=headers, json=turn)
                )
                for _ in range(200):
                    if len(calls) == 4:
                        break
                    await asyncio.sleep(0.01)
                assert len(calls) == 4
                repeat = await local.post(url, headers=headers, json=turn)
                assert (
                    repeat.status_code == 200 and repeat.json()["state"] == "generating"
                )
                changed = {**turn, "evidence_digest": "8" * 64}
                assert (
                    await local.post(url, headers=headers, json=changed)
                ).status_code == 409
                await runtime.json(
                    "POST",
                    f"/instrument-exploration/{fresh['id']}/cancel",
                    {
                        "request_fingerprint": fresh["fingerprint"],
                        "reason": "Cancel pending synthetic model",
                    },
                )
                gate.set()
                assert (await pending).status_code == 409
                async with sessionmanager.session() as db:
                    saved = await db.get(InstrumentAuthoringTurn, UUID(turn["id"]))
                    assert saved.proposal is None
                gate = None
                for condition in ["expired", "scope", "transport", "ai"]:
                    fresh["id"] = str(uuid4())
                    fresh["fingerprint"] = fingerprint(fresh)
                    await runtime.confirm(
                        "/instrument-exploration",
                        {**draft, "request": copy.deepcopy(fresh)},
                    )
                    async with sessionmanager.session() as db:
                        row = await db.get(
                            InstrumentAuthoringSession, UUID(fresh["id"])
                        )
                        if condition == "expired":
                            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                        elif condition == "scope":
                            row.scope_pin = {**row.scope_pin, "gateway_revision": -1}
                        await db.commit()
                    if condition == "transport":
                        monkeypatch.setattr(
                            config, "CHAT_API_ENDPOINT", "http://changed.invalid"
                        )
                    if condition == "ai":
                        monkeypatch.setattr(config, "AI_ENABLED", False)
                    status = await local.post(
                        f"/instrument-exploration/{fresh['id']}/status", headers=headers
                    )
                    assert (
                        status.status_code == 200
                        and status.json()["can_proceed"] is False
                    )
                    response = await local.post(
                        f"/instrument-exploration/{fresh['id']}/turns",
                        headers=headers,
                        json={**turn, "id": str(uuid4())},
                    )
                    assert response.status_code == 409 and len(calls) == 4
                    monkeypatch.setattr(
                        config, "CHAT_API_ENDPOINT", "http://synthetic-model.invalid"
                    )
                    monkeypatch.setattr(config, "AI_ENABLED", True)
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, 10)
            sock.close()

    try:
        runtime.run(exercise())
    finally:
        if owned_process:
            owned_process.terminate()
            try:
                owned_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                owned_process.kill()
                owned_process.wait(timeout=5)
            owned_process.stdout.close()
