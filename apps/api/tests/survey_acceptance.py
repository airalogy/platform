"""Actual Chromium capture -> scoped API/model wrapper -> independent draft assembly."""

import asyncio
import json
import subprocess
from importlib import import_module
from pathlib import Path
from uuid import uuid4

import httpx
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.config import config
from app.database import sessionmanager
from app.libs import masterbrain
from app.main import app
from sqlalchemy import text

from tests.exploration_acceptance import ROOT, node, target


def exercise_survey(runtime, tmp_path, monkeypatch, *, native=False):
    calls, gate, invalid = [], None, False
    owned_process = None

    async def provider(endpoint, payload, **kwargs):
        calls.append((endpoint, payload, kwargs))
        if gate:
            await gate.wait()
        prompt = payload["messages"][0]["content"]
        report = json.loads(
            next(
                line.split("=", 1)[1]
                for line in prompt.splitlines()
                if line.startswith("SURVEY=")
            )
        )
        identity = next(
            item
            for item in report["controls"]
            if item["locator"]
            and item["locator"]["name"]
            == ("app.identity" if native else "software-version")
        )
        status = next(
            item
            for item in report["controls"]
            if item["locator"]
            and item["locator"]["name"]
            == ("reader.status" if native else "reader-status")
        )
        proposal = {
            "summary": "Synthetic interpretation, not hardware qualification",
            "features": [
                {
                    "control_id": status["id"],
                    "interpretation": "Visible Ready text",
                    "basis": "observed",
                    "risk": "read_only",
                }
            ],
            "read_controls": [status["id"]],
            "identity_control": identity["id"],
            "route": "native_accessibility" if native else "browser",
            "limitations": ["No operation or physical readiness verified"],
            "missing_information": [],
        }
        if invalid:
            proposal["actions"] = ["invented click"]
        yield json.dumps(proposal)

    monkeypatch.setattr(masterbrain, "stream_request", provider)
    monkeypatch.setattr(config, "AI_ENABLED", True)
    monkeypatch.setattr(config, "MASTERBRAIN_CALL_MODE", "external")
    monkeypatch.setattr(config, "CHAT_API_ENDPOINT", "http://synthetic-model.invalid")

    async def exercise():
        nonlocal gate, invalid, owned_process
        resource, gateway = await target(runtime)
        cli = ROOT / "apps/instrument-interface/src/survey-cli.mjs"
        tmp_path.chmod(0o700)
        browser_arguments = (
            cli,
            "prepare",
            "--file",
            ROOT / "apps/instrument-gateway/examples/simulated-reader.html",
            "--application",
            "Airalogy Simulated Reader",
            "--version",
            "1.0",
            "--title",
            "Airalogy Simulated Reader — no hardware",
            "--scope-role",
            "main",
            "--workspace",
            tmp_path,
        )
        if native:
            native_cli = ROOT / "apps/instrument-interface/src/native-cli.mjs"
            built = await node(native_cli, "build", "--workspace", tmp_path)
            doctor = await node(native_cli, "doctor", "--build", built["build_file"])
            assert doctor["accessibility_trusted"] is True
            assert doctor["interactive_session"]["ready"] is True
            assert doctor["permissions_changed"] is False
            # Only the fixed, just-built, no-network/no-hardware synthetic app.
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
            await node(
                ROOT / "apps/instrument-interface/tests/native-fixture.mjs",
                "--build",
                built["build_file"],
                "--pid",
                owned_process.pid,
            )
            masks = tmp_path / "private-masks.json"
            masks.write_text('["private.note"]')
            masks.chmod(0o600)
            prepared = await node(
                native_cli,
                "prepare",
                "--build",
                built["build_file"],
                "--bundle",
                built["simulator_app"],
                "--pid",
                owned_process.pid,
                "--title",
                "Airalogy Native Reader — Simulation",
                "--redact",
                masks,
                "--workspace",
                tmp_path,
            )
        else:
            prepared = await node(*browser_arguments)
        captured = await node(
            cli,
            "run",
            prepared["request_file"],
            "--confirm",
            prepared["local_preview_digest"],
        )
        report = json.loads(Path(captured["report_file"]).read_text())
        if native:
            assert report["target"]["kind"] == "native_macos"
            assert "SYNTHETIC_PRIVATE" not in json.dumps(report)
            assert "SYNTHETIC_PASSWORD" not in json.dumps(report)
        draft = {
            "id": str(uuid4()),
            "gateway_id": gateway["id"],
            "resource_id": resource["id"],
            "goal": "Interpret this selected synthetic software",
            "report": report,
            "reason": "Synthetic survey acceptance",
            "model_processing_consent": True,
            "capture_reviewed": True,
        }
        monkeypatch.setattr(config, "AI_ENABLED", False)
        await runtime.json("POST", "/instrument-surveys/preview", draft, status=409)
        monkeypatch.setattr(config, "AI_ENABLED", True)
        await runtime.json(
            "POST",
            "/instrument-surveys/preview",
            {**draft, "capture_reviewed": False},
            status=422,
        )
        await runtime.json(
            "POST",
            "/instrument-surveys/preview",
            {**draft, "report": {"selection": "private request"}},
            status=422,
        )
        preview = await runtime.json("POST", "/instrument-surveys/preview", draft)
        assert preview["capture_digest"] == captured["report_digest"]
        await runtime.json(
            "POST",
            "/instrument-surveys",
            {**draft, "reason": "Changed", "preview_digest": preview["preview_digest"]},
            status=409,
        )
        approved = {**draft, "preview_digest": preview["preview_digest"]}
        responses = await asyncio.gather(
            *(
                runtime.client.post("/instrument-surveys", json=approved)
                for _ in range(2)
            )
        )
        assert [r.status_code for r in responses] == [200, 200]
        assert responses[0].json()["request"]["max_iterations"] == 1
        session_id = draft["id"]
        turn = {"id": str(uuid4())}
        generated = await runtime.json(
            "POST", f"/instrument-surveys/{session_id}/analyze", turn
        )
        assert generated["state"] == "generated" and len(calls) == 1, (
            generated["error"],
            len(calls),
        )
        assert (
            await runtime.json(
                "POST", f"/instrument-surveys/{session_id}/analyze", turn
            )
        )["proposal"] == generated["proposal"]
        await runtime.json(
            "POST",
            f"/instrument-surveys/{session_id}/analyze",
            {"id": str(uuid4())},
            status=409,
        )
        exported = await runtime.json("GET", f"/instrument-surveys/{session_id}/export")
        assert exported["capture_digest"] == captured["report_digest"]
        analysis_file = tmp_path / "analysis-export.json"
        analysis_file.write_text(json.dumps(exported))
        analysis_file.chmod(0o600)
        result = await node(
            cli,
            "assemble",
            prepared["request_file"],
            "--analysis",
            analysis_file,
            "--workspace",
            tmp_path,
        )
        assert result["actions_approved"] is False and result["browser_opened"] is False
        definition = json.loads(Path(result["definition_file"]).read_text())
        assert all(item["operations"] == ["read"] for item in definition["controls"])
        assert json.loads(Path(result["plan_file"]).read_text())["steps"] == []
        assert len(calls) == 1
        if native:
            preview_read = await node(
                native_cli, "preview", "--definition", result["definition_file"]
            )
            read = await node(
                native_cli,
                "read",
                "--definition",
                result["definition_file"],
                "--confirm",
                preview_read["sha256"],
                "--evidence",
                tmp_path,
                "--ack-new-read",
            )
            values = json.loads(Path(read["readback_file"]).read_text())
            assert "Ready" in values.values() and read["actions_executed"] == 0
        history = await runtime.json("GET", f"/instrument-surveys/{session_id}")
        assert not history["can_analyze"] and len(history["turns"]) == 1
        listed = await runtime.json(
            "GET",
            f"/instrument-surveys?gateway_id={gateway['id']}&resource_id={resource['id']}",
        )
        assert listed["items"][0]["id"] == session_id
        for purpose in ("instrument-authoring", "instrument-exploration"):
            await runtime.json("GET", f"/{purpose}/{session_id}", status=404)
        assert not (
            await runtime.json(
                "GET", f"/research-instrument-gateways/{gateway['id']}/commands"
            )
        )["items"]
        # No development bearer can read this user-only surface, and viewers remain denied.
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as local:
            assert (
                await local.get(
                    f"/instrument-surveys/{session_id}",
                    headers={"X-Airalogy-Interface-Token": "aiinterface_" + "A" * 43},
                )
            ).status_code in (401, 403)
            viewer = next(
                item for item in runtime.seed["accounts"] if item["key"] == "viewer"
            )
            login = await local.post(
                "/signin_by_email",
                json={"email": viewer["email"], "password": viewer["password"]},
            )
            assert (
                await local.get(
                    f"/instrument-surveys/{session_id}",
                    headers={"Auth-Token": login.json()["token"]},
                )
            ).status_code == 403
        # Paid-attempt reservation survives concurrent repeats and cancellation discards late output.
        fresh = {**draft, "id": str(uuid4())}
        fresh_row = await runtime.confirm("/instrument-surveys", fresh)
        gate = asyncio.Event()
        entered = asyncio.Event()
        pending_turn = {"id": str(uuid4())}
        url = f"/instrument-surveys/{fresh['id']}/analyze"
        pending = asyncio.create_task(runtime.client.post(url, json=pending_turn))
        try:
            for _ in range(200):
                if len(calls) == 2:
                    entered.set()
                    break
                await asyncio.sleep(0.01)
            assert entered.is_set()
            assert (await runtime.json("POST", url, pending_turn))[
                "state"
            ] == "generating"
            await runtime.json("POST", url, {"id": str(uuid4())}, status=409)
            await runtime.json(
                "POST",
                f"/instrument-surveys/{fresh['id']}/cancel",
                {
                    "request_fingerprint": fresh_row["request"]["fingerprint"],
                    "reason": "Stop synthetic interpretation",
                },
            )
            gate.set()
            assert (await pending).status_code == 409
            await runtime.json(
                "GET", f"/instrument-surveys/{fresh['id']}/export", status=409
            )
            assert len(calls) == 2
        finally:
            gate.set()
            await asyncio.gather(pending, return_exceptions=True)
            gate = None
        invalid = True
        bad = await runtime.confirm(
            "/instrument-surveys", {**draft, "id": str(uuid4())}
        )
        bad_turn = {"id": str(uuid4())}
        rejected = await runtime.json(
            "POST", f"/instrument-surveys/{bad['id']}/analyze", bad_turn
        )
        assert rejected["state"] == "failed" and rejected["error"] == "invalid_proposal"
        assert rejected["proposal"] is None and len(calls) == 3
        monkeypatch.setattr(config, "AI_ENABLED", False)
        assert (
            await runtime.json("GET", f"/instrument-surveys/{session_id}/export")
        ) == exported
        assert (
            await runtime.json(
                "POST", f"/instrument-surveys/{bad['id']}/analyze", bad_turn
            )
        )["state"] == "failed"
        assert len(calls) == 3

        # Exercise actual downgrade/upgrade in the disposable database, preserving
        # any pre-existing source/interface history and cascading only survey turns.
        def migrate(connection):
            preserved = connection.execute(
                text(
                    "SELECT id, purpose FROM instrument_authoring_sessions WHERE purpose != 'survey' ORDER BY id"
                )
            ).all()
            survey_ids = (
                connection.execute(
                    text(
                        "SELECT id FROM instrument_authoring_sessions WHERE purpose = 'survey'"
                    )
                )
                .scalars()
                .all()
            )
            assert survey_ids
            migration = import_module("migrations.versions.0057_instrument_survey")
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
                assert (
                    connection.execute(
                        text(
                            "SELECT count(*) FROM instrument_authoring_sessions WHERE purpose = 'survey'"
                        )
                    ).scalar()
                    == 0
                )
                assert (
                    connection.execute(
                        text(
                            "SELECT id, purpose FROM instrument_authoring_sessions WHERE purpose != 'survey' ORDER BY id"
                        )
                    ).all()
                    == preserved
                )
                for identifier in survey_ids:
                    assert (
                        connection.execute(
                            text(
                                "SELECT count(*) FROM instrument_authoring_turns WHERE session_id = :id"
                            ),
                            {"id": identifier},
                        ).scalar()
                        == 0
                    )
                migration.upgrade()
            constraint = connection.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_authoring_purpose'"
                )
            ).scalar()
            assert "survey" in constraint

        async with sessionmanager.connect() as connection:
            await connection.run_sync(migrate)

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
