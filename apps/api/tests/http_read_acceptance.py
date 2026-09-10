"""Installed Gateway -> owned HTTP fixture -> real Platform, with receipt recovery.

Synthetic policy rows in a disposable DB, never real hardware qualification.
"""

import asyncio
import json
import os
import socket
import sys
from pathlib import Path
from uuid import UUID

import uvicorn

from app.database import sessionmanager
from app.main import app
from app.models.research_execution import ResearchInstrumentJob


def exercise_http_reader(runtime, tmp_path, monkeypatch):
    sdk_root = Path(__file__).resolve().parents[3] / "apps/instrument-gateway"
    monkeypatch.syspath_prepend(str(sdk_root / "src"))
    monkeypatch.syspath_prepend(str(sdk_root / "tests"))
    from http_reader_fixture import serve

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
        with serve() as (port, calls):
            exercise_managed_activation(
                runtime,
                tmp_path,
                monkeypatch,
                http_reader={
                    "port": port,
                    "platform_url": origin,
                    "calls": calls,
                    "paths": paths,
                    "sdk_root": sdk_root,
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
    assert store.load().result == RESULT
    async with sessionmanager.session() as db:
        saved = await db.get(ResearchInstrumentJob, UUID(job["id"]))
        assert saved.status == "completed"
        assert saved.result == RESULT
    before = list(fixture["calls"])
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
    paths = fixture["paths"]
    assert sum(path.endswith("/lease") for path in paths) == 1
    assert sum(path.endswith("/start") for path in paths) == 1
    assert sum(path.endswith("/complete") for path in paths) == 2
