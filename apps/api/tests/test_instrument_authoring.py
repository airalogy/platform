"""Source-only development boundaries and bounded existing Aira transport."""

import asyncio
import copy
import json
from datetime import timedelta
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.libs import masterbrain
from app.routers.instrument_authoring import Cancel, Confirm, Draft, Report, _preview
from app.services.instrument_authoring_contract import fingerprint
from app.services.research_runtime import utcnow


def authoring_request(risk="read_only"):
    root = Path(__file__).resolve().parents[3]
    example = root / "apps/instrument-gateway/examples/adapter-package"
    manifest = json.loads((example / "manifest.json").read_text())
    manifest["provenance"]["kind"] = "aira"
    command = manifest["commands"][0]
    command["risk"] = risk
    command["device_confirmation_required"] = risk in ("medium", "high")
    command["safety_contract"].update(
        operator_presence_required=risk == "high",
        emergency_stop_required=risk == "high",
    )
    value = {
        "schema": "airalogy.authoring-request.v1",
        "id": str(uuid4()),
        "gateway_id": str(uuid4()),
        "resource_id": str(uuid4()),
        "credential_digest": "1" * 64,
        "max_iterations": 2,
        "duration_seconds": 120,
        "sandbox": {
            "sdk_digest": "2" * 64,
            "image": "sha256:" + "3" * 64,
            "timeout_seconds": 30,
        },
        "spec": {
            "goal": "Synthetic development consent test, not hardware qualification",
            "manifest": manifest,
            "factory": "synthetic_reader:create_adapter",
            "materials": [{"name": "synthetic.txt", "text": "Owned fixture only"}],
            "tests": {
                "tests/test_reader.py": (example / "tests/test_reader.py").read_text()
            },
            "licenses": {"licenses/LICENSE.txt": (root / "LICENSE").read_text()},
            "initial_sources": {},
        },
    }
    value["fingerprint"] = fingerprint(value)
    return value


@pytest.mark.parametrize("risk", ["low", "medium", "high"])
def test_controlled_draft_needs_strict_separate_consent_and_pinned_review(risk):
    fields = {
        "request": authoring_request(risk),
        "reason": "Independent source-only review",
        "model_processing_consent": True,
    }
    for consent in (False, "true", "false", 1, None):
        with pytest.raises(ValidationError):
            Draft(**fields, controlled_source_consent=consent)
        with pytest.raises(ValidationError):
            Confirm(
                **fields, controlled_source_consent=consent, preview_digest="4" * 64
            )
    approved = Draft(**fields, controlled_source_consent=True)
    preview = _preview(approved, {"fixture": "pin"})
    assert preview["source_review"]["requires_controlled_source_consent"] is True
    assert preview["source_review"]["execution_authorized"] is False
    assert preview["source_review"]["commands"][0]["risk"] == risk
    assert preview["hardware_authorized"] is False
    changed = copy.deepcopy(fields)
    changed["request"]["spec"]["manifest"]["commands"][0]["stop"] = (
        "Changed stopping requirement"
    )
    changed["request"]["fingerprint"] = fingerprint(changed["request"])
    assert (
        _preview(Draft(**changed, controlled_source_consent=True), {"fixture": "pin"})[
            "preview_digest"
        ]
        != preview["preview_digest"]
    )


def test_existing_read_only_authorization_keeps_its_shape_and_explicit_ai_consent():
    draft = Draft(
        request=authoring_request(),
        reason="Reviewed read-only draft",
        model_processing_consent=True,
    )
    assert draft.controlled_source_consent is False
    assert (
        _preview(draft, {})["source_review"]["requires_controlled_source_consent"]
        is False
    )


@pytest.mark.parametrize("purpose", ["source", "interface", "survey"])
def test_shared_history_adds_source_review_only_to_source_sessions(
    monkeypatch, purpose
):
    from app.routers import instrument_authoring

    async def no_turns(db, session_id):
        return []

    monkeypatch.setattr(instrument_authoring, "_turns", no_turns)
    request = (
        authoring_request("medium")
        if purpose == "source"
        else {"spec": {"goal": "Observe only"}}
    )
    row = SimpleNamespace(
        id=uuid4(),
        purpose=purpose,
        request=request,
        state="open",
        expires_at=utcnow() + timedelta(minutes=1),
        as_dict=lambda: {"purpose": purpose, "request": request},
    )
    snapshot = asyncio.run(instrument_authoring._snapshot(None, row))
    assert ("source_review" in snapshot) == (purpose == "source")
    assert snapshot["hardware_authorized"] is False
    assert snapshot["request"] == request
    if purpose == "source":
        assert snapshot["source_review"]["requires_controlled_source_consent"] is True


def test_shared_authoring_contract_and_migration_registration():
    root = Path(__file__).resolve().parents[3]
    source = (
        root
        / "apps/instrument-gateway/src/airalogy_instrument_gateway/authoring_contract.py"
    ).read_text()
    generated = (
        root / "apps/api/app/services/instrument_authoring_contract.py"
    ).read_text()
    assert (
        source.replace(
            "from .package_contract import (",
            "from .instrument_package_contract import (",
        )
        in generated
    )
    migration = import_module("migrations.versions.0055_instrument_authoring")
    from migrations.model_registry import MODEL_MODULES

    assert "app.models.instrument_authoring" in MODEL_MODULES
    assert migration.down_revision == "0054_instrument_outputs"
    assert len(migration.TABLE_NAMES) == 2


def test_test_receipts_cannot_claim_build_as_passing_sandbox():
    report = {
        "candidate_digest": "1" * 64,
        "archive_digest": "2" * 64,
        "sdk_digest": "3" * 64,
        "image": "sha256:" + "4" * 64,
        "phase": "sandbox",
        "passed": True,
        "failure_reason": "",
        "untrusted_test_output": "",
    }
    assert Report(**report).passed
    for change in (
        {"phase": "build"},
        {"archive_digest": None},
        {"passed": False},
        {"passed": "true"},
        {"failure_reason": "failed"},
    ):
        with pytest.raises(ValidationError):
            Report(**{**report, **change})
    with pytest.raises(ValidationError):
        Cancel(request_fingerprint="1" * 64, reason="  ")


def test_existing_aira_transport_response_has_incremental_byte_limit(monkeypatch):
    captured = []

    async def fixture_stream(endpoint, payload, **kwargs):
        captured.append((endpoint, payload, kwargs))
        yield '{"source":"'
        for _ in range(20):
            yield "文" * 10
        yield '"}'

    monkeypatch.setattr(masterbrain, "stream_request", fixture_stream)
    with pytest.raises(ValueError, match="streaming response limit"):
        asyncio.run(
            masterbrain.aira_structured_proposal(
                "selected synthetic context", max_response_bytes=60
            )
        )
    assert captured[0][0] == "endpoints/chat/qa/language"
    assert captured[0][1]["model"]["enable_search"] is False
    result = asyncio.run(
        masterbrain.aira_structured_proposal(
            "selected synthetic context", max_response_bytes=1000
        )
    )
    assert result["source"] == "文" * 200
