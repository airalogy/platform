"""Selected local metadata -> scoped model attempt -> explicit current identity check."""

import json
import sys
from pathlib import Path
from uuid import uuid4

import httpx

from app.config import config
from app.libs import masterbrain
from app.main import app
from tests.exploration_acceptance import ROOT, node, target


def exercise_application_selection(runtime, tmp_path, monkeypatch):
    calls = []
    invalid = False

    async def provider(endpoint, payload, **kwargs):
        calls.append(payload)
        prompt = payload["messages"][0]["content"]
        report = json.loads(
            next(
                line.split("=", 1)[1]
                for line in prompt.splitlines()
                if line.startswith("CANDIDATES=")
            )
        )
        assert "bundle_path" not in json.dumps(report)
        assert str(tmp_path) not in prompt
        yield json.dumps(
            {
                "summary": "Candidate based on declared metadata only",
                "recommendations": [
                    {
                        "candidate_id": "candidate_99"
                        if invalid
                        else report["candidates"][0]["id"],
                        "rationale": "The declared name describes the selected reader",
                        "evidence_fields": ["name"],
                    }
                ],
                "limitations": ["Not verified functions or vendor identity"],
                "missing_information": ["Confirm exact instrument and vendor"],
            }
        )

    monkeypatch.setattr(masterbrain, "stream_request", provider)
    monkeypatch.setattr(config, "AI_ENABLED", True)
    monkeypatch.setattr(config, "MASTERBRAIN_CALL_MODE", "external")
    monkeypatch.setattr(config, "CHAT_API_ENDPOINT", "http://synthetic-model.invalid")

    async def exercise():
        nonlocal invalid
        resource, gateway = await target(runtime)
        tmp_path.chmod(0o700)
        cli = ROOT / "apps/instrument-interface/src/native-cli.mjs"
        local = built = None
        if sys.platform == "darwin":
            built = await node(cli, "build", "--workspace", tmp_path)
            discovery = await node(
                cli,
                "prepare-discovery",
                "--directory",
                Path(built["simulator_app"]).parent,
                "--workspace",
                tmp_path,
            )
            await node(
                cli,
                "discover",
                "--request",
                discovery["request_file"],
                "--confirm",
                discovery["preview_digest"],
            )
            local = await node(
                cli,
                "prepare-selection",
                "--request",
                discovery["request_file"],
                "--indices",
                "1",
                "--workspace",
                tmp_path,
            )
            report = json.loads(Path(local["candidates_file"]).read_text())
        else:
            # Linux CI still exercises the actual API/governance chain; native
            # metadata and code-signature checks run on macOS, never emulated.
            report = json.loads(
                (
                    ROOT
                    / "apps/instrument-interface/tests/fixtures/application-candidates.json"
                ).read_text()
            )
        draft = {
            "id": str(uuid4()),
            "gateway_id": gateway["id"],
            "resource_id": resource["id"],
            "goal": "Find candidate reader control software",
            "report": report,
            "reason": "Review synthetic selected metadata",
            "model_processing_consent": True,
            "capture_reviewed": True,
        }
        await runtime.json(
            "POST",
            "/instrument-surveys/preview",
            {**draft, "report": {**report, "bundle_path": "/private/never-upload"}},
            status=422,
        )
        await runtime.json(
            "POST",
            "/instrument-surveys/preview",
            {**draft, "capture_reviewed": False},
            status=422,
        )
        preview = await runtime.json("POST", "/instrument-surveys/preview", draft)
        if local:
            assert preview["capture_digest"] == local["capture_digest"]
        assert not preview["hardware_authorized"]
        await runtime.json(
            "POST",
            "/instrument-surveys",
            {**draft, "reason": "Changed", "preview_digest": preview["preview_digest"]},
            status=409,
        )
        saved = await runtime.confirm("/instrument-surveys", draft)
        assert saved["request"]["schema"] == "airalogy.application-selection.v1"
        session_id = saved["id"]
        turn = {"id": str(uuid4())}
        output = await runtime.json(
            "POST", f"/instrument-surveys/{session_id}/analyze", turn
        )
        assert output["state"] == "generated" and len(calls) == 1, output
        assert (
            await runtime.json(
                "POST", f"/instrument-surveys/{session_id}/analyze", turn
            )
        )["proposal"] == output["proposal"]
        await runtime.json(
            "POST",
            f"/instrument-surveys/{session_id}/analyze",
            {"id": str(uuid4())},
            status=409,
        )
        assert len(calls) == 1
        exported = await runtime.json("GET", f"/instrument-surveys/{session_id}/export")
        assert exported["schema"] == "airalogy.application-selection-export.v1"
        assert exported["capture_digest"] == preview["capture_digest"]
        if local:
            analysis_file = tmp_path / "candidate-analysis.json"
            analysis_file.write_text(json.dumps(exported))
            analysis_file.chmod(0o600)
            resolved = await node(
                cli,
                "inspect-selection",
                "--selection",
                local["selection_file"],
                "--candidate",
                "candidate_1",
                "--analysis",
                analysis_file,
                "--build",
                built["build_file"],
            )
            assert (
                resolved["inspection"]["bundle"]["bundle_path"]
                == built["simulator_app"]
            )
            assert resolved["inspection"]["running"] == []
            assert (
                not resolved["applications_opened"]
                and not resolved["ui_actions_approved"]
                and not resolved["hardware_qualified"]
            )
        history = await runtime.json("GET", f"/instrument-surveys/{session_id}")
        assert not history["can_analyze"] and len(history["turns"]) == 1
        for other in ("instrument-authoring", "instrument-exploration"):
            await runtime.json("GET", f"/{other}/{session_id}", status=404)
        assert not (
            await runtime.json(
                "GET", f"/research-instrument-gateways/{gateway['id']}/commands"
            )
        )["items"]
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as outsider:
            assert (
                await outsider.get(f"/instrument-surveys/{session_id}")
            ).status_code == 401
            viewer = next(
                item for item in runtime.seed["accounts"] if item["key"] == "viewer"
            )
            login = await outsider.post(
                "/signin_by_email",
                json={"email": viewer["email"], "password": viewer["password"]},
            )
            assert (
                await outsider.get(
                    f"/instrument-surveys/{session_id}",
                    headers={"Auth-Token": login.json()["token"]},
                )
            ).status_code == 403
        invalid = True
        fresh = await runtime.confirm(
            "/instrument-surveys", {**draft, "id": str(uuid4())}
        )
        failed = await runtime.json(
            "POST", f"/instrument-surveys/{fresh['id']}/analyze", {"id": str(uuid4())}
        )
        assert (
            failed["state"] == "failed"
            and failed["error"] == "invalid_proposal"
            and failed["proposal"] is None
        )
        await runtime.json(
            "GET", f"/instrument-surveys/{fresh['id']}/export", status=409
        )
        monkeypatch.setattr(config, "AI_ENABLED", False)
        await runtime.json(
            "POST",
            "/instrument-surveys/preview",
            {**draft, "id": str(uuid4())},
            status=409,
        )
        assert (
            await runtime.json("GET", f"/instrument-surveys/{session_id}/export")
        ) == exported
        if local:
            manual = await node(
                cli,
                "inspect-selection",
                "--selection",
                local["selection_file"],
                "--candidate",
                "candidate_1",
                "--build",
                built["build_file"],
            )
            assert (
                manual["analysis_digest"] is None and not manual["applications_opened"]
            )
            assert manual["inspection"]["bundle"] == resolved["inspection"]["bundle"]
        assert len(calls) == 2

    runtime.run(exercise())
