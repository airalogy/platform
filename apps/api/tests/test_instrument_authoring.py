"""Source-only development boundaries and bounded existing Aira transport."""

import asyncio
from importlib import import_module
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.libs import masterbrain
from app.routers.instrument_authoring import Cancel, Report


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
