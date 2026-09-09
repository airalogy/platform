import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.instrument_qualification import InstrumentQualification
from app.services import instrument_qualifications as service
from app.services.access_control import ROLE_CAPABILITIES


def report():
    now = datetime.now(UTC)
    return {
        "id": str(uuid4()),
        "scope": "simulation",
        "evidence_origin": "manual_observation",
        "target": {
            key: "Synthetic fixture" for key in service.QualificationTarget.model_fields
        },
        "commands": [
            {
                "key": "fixture.read",
                "version": "1.0.0",
                "checks": [
                    {
                        "kind": kind,
                        "method": "Independent synthetic comparison",
                        "expected": "42",
                        "observed": "42",
                        "passed": True,
                    }
                    for kind in ["identity", "output", "completion"]
                ],
            }
        ],
        "evidence_file_ids": [],
        "assessed_at": now.isoformat(),
        "expires_at": (now + timedelta(days=1)).isoformat(),
        "reason": "Synthetic software acceptance, not a real instrument",
        "independent_review_confirmed": False,
        "physical_tests_authorized": False,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"scope": "read_only"},
        {"scope": "controlled"},
        {"hardware_authorized": True},
        {"independent_review_confirmed": 1},
        {"evidence_origin": "ai_guess"},
        {"assessed_at": "2026-09-09T10:00:00"},
        {"target": {}},
    ],
)
def test_qualification_requires_bounded_explicit_human_evidence(change):
    with pytest.raises(ValidationError):
        service.QualificationDraft.model_validate({**report(), **change})


def test_self_tests_and_duplicate_or_missing_checks_cannot_qualify():
    value = report()
    value.update(
        scope="read_only",
        evidence_origin="package_self_test",
        independent_review_confirmed=True,
        physical_tests_authorized=True,
    )
    with pytest.raises(ValidationError, match="self-tests"):
        service.QualificationDraft.model_validate(value)
    value = report()
    value["commands"][0]["checks"][1]["kind"] = "identity"
    with pytest.raises(ValidationError, match="unique"):
        service.QualificationDraft.model_validate(value)
    value = report()
    value["commands"] *= 2
    with pytest.raises(ValidationError, match="unique"):
        service.QualificationDraft.model_validate(value)


def test_qualification_pins_command_scope_and_real_safety_checks():
    assert not service.command_simulation_only(
        {"output_schema": {"properties": {"simulation_only": True}}}
    )
    value = report()
    value.update(
        scope="read_only",
        independent_review_confirmed=True,
        physical_tests_authorized=True,
    )
    draft = service.QualificationDraft.model_validate(value)
    command = {
        "key": "fixture.read",
        "version": "1.0.0",
        "risk": "read_only",
        "output_schema": {},
    }
    assert service.validate_command_assessments(draft, {"commands": [command]}) == [
        command
    ]
    for modified in [
        {**command, "version": "2.0.0"},
        {**command, "risk": "medium"},
        {
            **command,
            "output_schema": {"properties": {"simulation_only": {"const": True}}},
        },
    ]:
        with pytest.raises(ValueError):
            service.validate_command_assessments(draft, {"commands": [modified]})
    value["scope"] = "controlled"
    with pytest.raises(ValueError, match="safe-stop"):
        service.validate_command_assessments(
            service.QualificationDraft.model_validate(value),
            {"commands": [{**command, "risk": "medium"}]},
        )
    for kind in ["parameter_readback", "safe_stop", "manual_takeover", "interlocks"]:
        value["commands"][0]["checks"].append(
            {**value["commands"][0]["checks"][0], "kind": kind}
        )
    service.validate_command_assessments(
        service.QualificationDraft.model_validate(value),
        {"commands": [{**command, "risk": "medium"}]},
    )


@pytest.mark.parametrize(
    "scope,state",
    [
        ("simulation", "simulation_only"),
        ("read_only", "qualified"),
        ("controlled", "qualified"),
    ],
)
def test_valid_record_still_does_not_grant_execution(monkeypatch, scope, state):
    row = InstrumentQualification(
        id=uuid4(),
        scope=scope,
        outcome="passed",
        revoked_at=None,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        pins={"descriptor": {}, "receipt": {}},
        evidence_files=[],
    )
    monkeypatch.setattr(service, "binding_invalid_reason", AsyncMock(return_value=None))
    assert (
        asyncio.run(
            service.qualification_state(
                None, row, SimpleNamespace(descriptor={}, receipt={})
            )
        )
        == state
    )
    # No activation pointer or execution boolean is present in the acceptance model.
    assert "hardware_authorized" not in row.as_dict()


@pytest.mark.parametrize(
    "change,expected",
    [
        ("revoked", "revoked"),
        ("failed", "failed"),
        ("expired", "expired"),
        ("descriptor", "installation_changed"),
        ("receipt", "installation_changed"),
        ("equipment", "equipment_changed"),
        ("evidence", "evidence_unavailable"),
    ],
)
def test_qualification_invalidation_is_evaluated_not_a_sticky_boolean(
    monkeypatch, change, expected
):
    row = SimpleNamespace(
        scope="read_only",
        outcome="passed",
        revoked_at=None,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        pins={"descriptor": {}, "receipt": {}},
        evidence_files=[],
    )
    binding = SimpleNamespace(descriptor={}, receipt={})
    if change == "revoked":
        row.revoked_at = datetime.now(UTC)
    elif change == "failed":
        row.outcome = "failed"
    elif change == "expired":
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif change in {"descriptor", "receipt"}:
        setattr(binding, change, {"changed": True})
    elif change == "evidence":
        row.evidence_files = [{"id": str(uuid4()), "sha256": "a" * 64}]
    monkeypatch.setattr(
        service,
        "binding_invalid_reason",
        AsyncMock(return_value="equipment_changed" if change == "equipment" else None),
    )
    assert (
        asyncio.run(
            service.qualification_state(
                SimpleNamespace(get=AsyncMock(return_value=None)), row, binding
            )
        )
        == expected
    )


def test_qualification_capability_is_distinct_from_custody_or_bookings():
    assert "equipment.qualify" in ROLE_CAPABILITIES["lab_owner"]
    assert "equipment.qualify" in ROLE_CAPABILITIES["lab_admin"]
    assert "equipment.qualify" not in ROLE_CAPABILITIES["resource_custodian"]
    assert "equipment.qualify" not in ROLE_CAPABILITIES["resource_operator"]


def test_failed_observations_remain_valid_failed_evidence():
    value = deepcopy(report())
    value["commands"][0]["checks"][0].update(
        passed=False, observed="Unexpected identity"
    )
    parsed = service.QualificationDraft.model_validate(value)
    assert not all(
        check.passed for command in parsed.commands for check in command.checks
    )


@pytest.mark.parametrize(
    "change,expected",
    [
        (None, None),
        ("gateway", "gateway_identity_changed"),
        ("resource", "equipment_changed"),
        ("release", "source_changed"),
        ("digest", "source_changed"),
        ("archive", "source_unavailable"),
        ("lab", "equipment_changed"),
    ],
)
def test_current_binding_authority_and_versions_are_checked(change, expected):
    lab, revision = uuid4(), uuid4()
    binding = SimpleNamespace(
        state="installed",
        receipt={"installed": True},
        lab_id=lab,
        gateway_id=uuid4(),
        gateway_credential_pin="credential",
        resource_id=uuid4(),
        resource_revision_id=revision,
        release_id=uuid4(),
        release_revision=2,
        descriptor={"archive_digest": "a" * 64, "manifest_digest": "b" * 64},
    )
    gateway = SimpleNamespace(lab_id=lab, revoked_at=None, token_digest="credential")
    resource = SimpleNamespace(
        lab_id=lab, archived_at=None, status="active", current_revision_id=revision
    )
    release = SimpleNamespace(
        lab_id=lab,
        state="approved",
        revision=2,
        archive_digest="a" * 64,
        manifest_digest="b" * 64,
        research_file_id=uuid4(),
    )
    file = SimpleNamespace(lab_id=lab, scope_type="lab", archived_at=None)
    if change == "gateway":
        gateway.token_digest = "changed"
    elif change == "resource":
        resource.current_revision_id = uuid4()
    elif change == "lab":
        resource.lab_id = uuid4()
    elif change == "release":
        release.state = "revoked"
    elif change == "digest":
        release.archive_digest = "c" * 64
    elif change == "archive":
        file.archived_at = datetime.now(UTC)
    db = SimpleNamespace(get=AsyncMock(side_effect=[gateway, resource, release, file]))
    assert asyncio.run(service.binding_invalid_reason(db, binding)) == expected
