"""Installed Gateway -> owned HTTP/export fixture -> real Platform and recovery.

Synthetic policy rows in a disposable DB, never real hardware qualification.
"""

import asyncio
import hashlib
import json
import os
import socket
import sys
from contextlib import nullcontext
from pathlib import Path
from uuid import UUID, uuid4

import uvicorn

from app.database import sessionmanager
from app.main import app
from app.models.research_execution import ResearchInstrumentJob


def exercise_http_reader(runtime, tmp_path, monkeypatch):
    return _exercise_reader(runtime, tmp_path, monkeypatch)


def exercise_export_reader(runtime, tmp_path, monkeypatch):
    return _exercise_reader(runtime, tmp_path, monkeypatch, export_files=True)


def exercise_http_controlled_reader(runtime, tmp_path, monkeypatch):
    return _exercise_reader(runtime, tmp_path, monkeypatch, http_controlled=True)


def exercise_interface_worker(runtime, tmp_path, monkeypatch, *, demonstration=False):
    return _exercise_reader(
        runtime,
        tmp_path,
        monkeypatch,
        interface_worker=True,
        demonstration=demonstration,
    )


def exercise_native_read(runtime, tmp_path, monkeypatch):
    return _exercise_reader(
        runtime, tmp_path, monkeypatch, interface_worker=True, native_read=True
    )


def _exercise_reader(
    runtime,
    tmp_path,
    monkeypatch,
    *,
    export_files=False,
    http_controlled=False,
    interface_worker=False,
    native_read=False,
    demonstration=False,
):
    sdk_root = Path(__file__).resolve().parents[3] / "apps/instrument-gateway"
    monkeypatch.syspath_prepend(str(sdk_root / "src"))
    monkeypatch.syspath_prepend(str(sdk_root / "tests"))
    from http_reader_fixture import serve

    if http_controlled:
        from http_controlled_fixture import serve

    from tests.activation_acceptance import exercise_managed_activation

    paths, lost = [], [False]

    async def endpoint(scope, receive, send):
        if scope["type"] != "http":
            return await app(scope, receive, send)
        paths.append(scope["path"])
        if scope["path"].endswith("/complete") and not lost[0]:
            messages = []

            async def collect(message):
                messages.append(message)

            await app(scope, receive, collect)
            if messages[0]["status"] == 200:
                lost[0] = True
                # The actual DB commit occurred. Simulate an unavailable receipt
                # at the HTTP boundary, not an acquisition failure or fake API.
                body = b'{"detail":"Synthetic unavailable acknowledgement"}'
                await send(
                    {
                        "type": "http.response.start",
                        "status": 503,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
            for message in messages:
                await send(message)
            return
        await app(scope, receive, send)

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
    service = uvicorn.Server(
        uvicorn.Config(
            endpoint, lifespan="off", ws="none", log_level="error", access_log=False
        )
    )

    async def start():
        task = asyncio.create_task(service.serve(sockets=[listener]))
        for _ in range(200):
            if service.started:
                return task
            if task.done():
                await task
                raise AssertionError("Synthetic Platform server stopped")
            await asyncio.sleep(0.01)
        service.should_exit = True
        await task
        raise AssertionError("Synthetic Platform server did not start")

    task = runtime.run(start())
    try:
        with (
            nullcontext((None, []))
            if export_files or interface_worker
            else serve() as (port, calls)
        ):
            fixture = {
                "port": port,
                "platform_url": origin,
                "calls": calls,
                "paths": paths,
                "sdk_root": sdk_root,
                "http_controlled": http_controlled,
                "interface_worker": interface_worker,
                "native_read": native_read,
            }
            if interface_worker:
                from interface_worker_fixture import prepare_worker

                if native_read:
                    from native_read_fixture import (
                        prepare_native_reader as prepare_worker,
                    )

                fixture.update(
                    prepare_worker(**({"demonstration": True} if demonstration else {}))
                )
            if export_files:
                from test_export_read import publish

                source = tmp_path.resolve() / "owned-export-inbox"
                source.mkdir(mode=0o700)
                export_id = str(uuid4())
                publish(source, export_id)
                raw_files = {
                    name: (source / export_id / name).read_bytes()
                    for name in ("result.csv", "export.json")
                }
                fixture.update(
                    export_root=source,
                    export_id=export_id,
                    raw_files=raw_files,
                    expected_result={
                        "export_id": export_id,
                        "sample_reference": "sample-A",
                        "source_kind": "file_export",
                        "scientific_validation": False,
                        "file_count": 2,
                        "byte_size": sum(len(raw) for raw in raw_files.values()),
                        "manifest_sha256": hashlib.sha256(
                            raw_files["export.json"]
                        ).hexdigest(),
                    },
                )
            exercise_managed_activation(
                runtime,
                tmp_path,
                monkeypatch,
                **{
                    "interface_worker"
                    if interface_worker
                    else "export_reader"
                    if export_files
                    else "http_controlled"
                    if http_controlled
                    else "http_reader": fixture
                },
            )
            assert lost[0]
    finally:

        async def finish():
            service.should_exit = True
            await asyncio.wait_for(task, 10)

        runtime.run(finish())
        listener.close()


async def run_installed_http_reader(runtime, root, activation, token, job, fixture):
    return await run_installed_reader(runtime, root, activation, token, job, fixture)


def expected_interface_result(job_id, fixture):
    if fixture.get("native_read"):
        return {
            "operation_id": job_id,
            "definition_digest": fixture["definition_digest"],
            "values": {"reader.status": "Ready", "reader.result": "No result"},
            "observation_only": True,
            "simulation_only": True,
        }
    return {
        "operation_id": job_id,
        "workflow_digest": fixture["workflow_digest"],
        "value": 0.84,
        "unit": "synthetic_unit",
        "simulation_only": True,
    }


async def run_installed_reader(runtime, root, activation, token, job, fixture):
    from airalogy_instrument_gateway.credentials import write_credentials
    from airalogy_instrument_gateway.state import StateStore
    from http_reader_fixture import RESULT

    credential_path = root / "gateway.json"
    write_credentials(
        credential_path,
        {
            "schema": "airalogy.gateway-credential.v1",
            "platform_url": fixture["platform_url"],
            "gateway_token": token,
            "lab_id": activation["lab_id"],
            "gateway_id": activation["gateway_id"],
        },
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PYTHON", "AIRALOGY_GATEWAY_", "LD_", "DYLD_"))
    }
    environment["PYTHONPATH"] = str(fixture["sdk_root"] / "src")

    async def command(operation, *extra, status=0):
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "airalogy_instrument_gateway.activation_cli",
            operation,
            "--request",
            str(root / "private.json"),
            "--credentials",
            str(credential_path),
            "--activation",
            activation["pin"]["id"],
            *(
                ["--output-root", str(fixture["export_root"])]
                if "export_root" in fixture
                else []
            ),
            *extra,
            env=environment,
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(child.communicate(), 45)
        except BaseException:
            if child.returncode is None:
                child.terminate()
                await child.wait()
            raise
        assert child.returncode == status, stderr.decode()
        assert token.encode() not in stdout + stderr
        return json.loads(stdout) if stdout.strip() else None

    assert not fixture["calls"]
    preview = await command("preview")
    assert not fixture["calls"]  # Preview/installation never probed the instrument.
    await command(
        "run",
        "--confirm-digest",
        preview["preview_digest"],
        "--startup-authorized",
        "--once",
        status=2,
    )
    store = StateStore(root / "state.json")
    assert store.load().phase == "completion_pending"
    expected = RESULT
    if fixture.get("http_controlled"):
        expected = {
            "operation_id": job["id"],
            "sample_count": 2,
            "value": 1.25,
            "unit": "synthetic_unit",
            "simulation_only": True,
        }
    if "export_root" in fixture:
        expected = fixture["expected_result"]
    if fixture.get("interface_worker"):
        expected = expected_interface_result(job["id"], fixture)
    assert store.load().result == expected
    async with sessionmanager.session() as db:
        saved = await db.get(ResearchInstrumentJob, UUID(job["id"]))
        assert saved.status == "completed"
        assert saved.result == expected
    before = list(fixture["calls"])
    if "export_root" in fixture:
        source = fixture["export_root"]
        directory = source / fixture["export_id"]
        for name in ("result.csv", "export.json"):
            (directory / name).unlink()  # Owned fixture, never a user's export.
        directory.rmdir()
        source.rmdir()
    elif fixture.get("interface_worker"):
        from interface_worker_fixture import invocations

        worker_before = invocations(fixture)
        executed = [item for item in worker_before if item[1] == "execute"]
        assert len(executed) == 1 and executed[0][2] == job["id"]
        assert any(item[1] == "probe" for item in worker_before)
    elif fixture.get("http_controlled"):
        assert before.count(("PUT", "/v1/parameters")) == 1
        assert before.count(("POST", "/v1/start")) == 1
        assert any(
            method == "GET" and path.startswith("/v1/result?")
            for method, path in before
        )
    else:
        assert sum(path.startswith("/v1/result?") for path, _ in before) == 1
        assert any(path == "/v1/identity" for path, _ in before)
    recovery = await command("preview", "--recover")
    assert not recovery["startup_may_initialize_equipment"]
    await command(
        "run",
        "--confirm-digest",
        recovery["preview_digest"],
        "--startup-authorized",
        "--recover",
        "--once",
    )
    assert store.load() is None
    assert fixture["calls"] == before  # No HTTP reread or identity/driver startup.
    if fixture.get("interface_worker"):
        assert (
            invocations(fixture) == worker_before
        )  # No Node/browser launch or action replay.
    if "export_root" in fixture:
        from app.models.knowledge import ResearchFile
        from app.models.research_asset import DataAsset, DataAssetVersion

        delivered = await runtime.json(
            "GET", f"/research-instrument-jobs/{job['id']}/outputs"
        )
        assert delivered["state"] == "delivered"
        assert {item["name"] for item in delivered["items"]} == {
            "result.csv",
            "export.json",
        }
        async with sessionmanager.session() as db:
            for item in delivered["items"]:
                asset = await db.get(DataAsset, UUID(item["data_asset_id"]))
                assert (
                    asset.status == "draft"
                    and str(asset.project_id) == runtime.seed["project"]["id"]
                )
                raw = fixture["raw_files"][item["name"]]
                version = await db.get(
                    DataAssetVersion, UUID(item["data_asset_version_id"])
                )
                assert version.checksum == hashlib.sha256(raw).hexdigest()
                assert version.byte_size == len(raw)
                assert version.source["job_id"] == job["id"]
                file = await db.get(ResearchFile, version.research_file_id)
                assert file.visibility == "project"
                assert str(file.project_id) == runtime.seed["project"]["id"]
                if item["name"] == "result.csv":
                    assert version.version_metadata["captured_at"] == (
                        "2026-09-11T12:29:00+08:00"
                    )
                    assert version.version_metadata["original_units"] == [
                        "signal: synthetic_unit"
                    ]
                    assert version.version_metadata["conversion_rules"] == []
                token = await runtime.json(
                    "POST", f"/knowledge/files/{file.id}/token", {"mode": "preview"}
                )
                response = await runtime.client.get(token["url"])
                assert response.status_code == 200 and response.content == raw
    paths = fixture["paths"]
    assert sum(path.endswith("/lease") for path in paths) == 1
    assert sum(path.endswith("/start") for path in paths) == 1
    assert sum(path.endswith("/complete") for path in paths) == 2
