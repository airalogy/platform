import asyncio
import hashlib
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.instrument_installation import InstrumentDeviceBinding
from app.routers import instrument_installations as routes
from app.services.instrument_installation_contract import (
    IDENTITY_FIELDS,
    digest,
    request_fingerprint,
    validate_descriptor,
    validate_receipt,
)
from app.services.instrument_installations import (
    assert_manual_execution_allowed,
    managed_instrument_scope,
)


def test_managed_execution_query_keeps_claimed_revocations_and_both_scopes():
    from sqlalchemy.dialects import postgresql

    gateway, resource = uuid4(), uuid4()
    sql = str(
        managed_instrument_scope(gateway, resource).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert str(gateway) in sql and str(resource) in sql
    assert "started_at IS NOT NULL" in sql
    assert "state IN ('installing', 'installed')" in sql
    assert "expires_at >" in sql


@pytest.mark.parametrize("managed", [True, False])
def test_only_unmanaged_execution_passes(managed):
    db = SimpleNamespace(scalar=AsyncMock(return_value=managed))
    if managed:
        with pytest.raises(HTTPException, match="qualification"):
            asyncio.run(assert_manual_execution_allowed(db, uuid4(), uuid4()))
    else:
        asyncio.run(assert_manual_execution_allowed(db, uuid4(), uuid4()))


@pytest.mark.parametrize("operation", ["lease", "start"])
def test_runtime_cannot_bypass_managed_qualification(monkeypatch, operation):
    from app.routers import research_instrument_jobs as jobs

    gateway = SimpleNamespace(id=uuid4(), enabled=True)
    db = SimpleNamespace(scalar=AsyncMock(return_value=True), commit=AsyncMock())
    monkeypatch.setattr(jobs, "_authenticate_gateway", AsyncMock(return_value=gateway))
    if operation == "lease":
        call = jobs.lease_instrument_job("runtime-credential", db)
    else:
        job = SimpleNamespace(status="leased", resource_id=uuid4())
        monkeypatch.setattr(
            jobs,
            "_gateway_job_context",
            AsyncMock(
                return_value=(
                    job,
                    SimpleNamespace(status="queued"),
                    SimpleNamespace(status="waiting_for_instrument"),
                    SimpleNamespace(status="active"),
                )
            ),
        )
        monkeypatch.setattr(jobs, "_ensure_live_lease", lambda _: None)
        monkeypatch.setattr(jobs, "_lock_idle_equipment", AsyncMock(return_value=True))
        call = jobs.start_instrument_job(
            uuid4(), jobs.GatewayStart(), "runtime", "lease", db
        )
    with pytest.raises(HTTPException, match="qualification"):
        asyncio.run(call)
    db.commit.assert_not_awaited()


def descriptor():
    value = {key: "a" * 64 for key in IDENTITY_FIELDS}
    value.update(
        python_version="3.13.6",
        platform="linux",
        architecture="x86_64",
        entry_point="synthetic.reader",
    )
    value["installation_id"] = digest(
        {"schema": "airalogy.inactive-installation.v1", **value}
    )
    value["local_preview_digest"] = "b" * 64
    return value


def request():
    value = {
        "schema": "airalogy.installation-request.v1",
        "id": str(uuid4()),
        "lab_id": str(uuid4()),
        "gateway_id": str(uuid4()),
        "credential_digest": "c" * 64,
        "descriptor": descriptor(),
    }
    return {**value, "fingerprint": request_fingerprint(value)}


@pytest.mark.parametrize(
    "change",
    [
        {"installation_token": "secret"},
        {"schema": "airalogy.private-installation.v1"},
        {"id": "invalid"},
        {"fingerprint": "0" * 64},
        {"descriptor": {}},
    ],
)
def test_public_request_rejects_private_files_and_modified_identity(change):
    with pytest.raises(ValidationError):
        routes.InstallationDraft(
            request={**request(), **change},
            resource_id=uuid4(),
            release_id=uuid4(),
            reason="Review",
            fingerprint_confirmed=True,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"platform": "win32"},
        {"python_version": "3.13"},
        {"sdk_digest": "invalid"},
        {"configuration_digest": "b" * 64},
        {"paths": []},
    ],
)
def test_exact_environment_and_descriptor_are_pinned(change):
    with pytest.raises(ValueError):
        validate_descriptor({**descriptor(), **change})


@pytest.mark.parametrize(
    "change",
    [
        {"hardware_authorized": True},
        {"activation_performed": 0},
        {"installed_file_count": True},
        {"installed_bytes": 600 * 1024 * 1024},
        {"files": []},
    ],
)
def test_receipt_is_bounded_private_and_never_confers_execution(change):
    value = {
        "schema": "airalogy.installation-receipt.v1",
        "descriptor": descriptor(),
        "local_receipt_digest": "a" * 64,
        "installed_file_count": 2,
        "installed_bytes": 100,
        "activation_performed": False,
        "hardware_authorized": False,
    }
    assert validate_receipt(value) == value
    with pytest.raises(ValueError):
        validate_receipt({**value, **change})


def test_snapshot_hides_installation_and_runtime_credential_hashes():
    row = InstrumentDeviceBinding(
        id=uuid4(),
        installer_token_digest="secret",
        gateway_credential_pin="hmac-key",
        creator_auth_version=4,
        state="authorized",
        expires_at=routes.utcnow() - timedelta(seconds=1),
    )
    snapshot = routes._snapshot(row)
    assert snapshot["state"] == "expired"
    assert not snapshot["hardware_authorized"] and not snapshot["activation_performed"]
    assert (
        not {"installer_token_digest", "gateway_credential_pin", "creator_auth_version"}
        & snapshot.keys()
    )


@pytest.mark.parametrize("enabled,active", [(True, None), (False, uuid4())])
def test_disabled_gateway_and_idle_equipment_are_both_required(enabled, active):
    db = SimpleNamespace(scalar=AsyncMock(return_value=active))
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            routes._idle(db, SimpleNamespace(id=uuid4(), enabled=enabled), uuid4())
        )
    assert error.value.status_code == 409


@pytest.mark.parametrize(
    "change", ["source", "equipment", "credential", "expiry", "revoke", "owner"]
)
def test_installer_rechecks_grant_and_current_authority(monkeypatch, change):
    token = "aiinstall_" + "a" * 43
    user, version, release = (
        SimpleNamespace(id=uuid4()),
        SimpleNamespace(id=uuid4()),
        SimpleNamespace(revision=2),
    )
    gateway = SimpleNamespace(token_digest="runtime-pin")
    row = SimpleNamespace(
        installer_token_digest=hashlib.sha256(token.encode()).hexdigest(),
        created_by_user_id=user.id,
        creator_auth_version=0,
        lab_id=uuid4(),
        gateway_id=uuid4(),
        resource_id=uuid4(),
        release_id=uuid4(),
        state="authorized",
        expires_at=routes.utcnow() + timedelta(minutes=5),
        gateway_credential_pin="runtime-pin",
        resource_revision_id=version.id,
        release_revision=2,
    )
    if change == "source":
        release.revision += 1
    elif change == "equipment":
        version.id = uuid4()
    elif change == "credential":
        gateway.token_digest = "rotated"
    elif change == "expiry":
        row.expires_at = routes.utcnow() - timedelta(seconds=1)
    elif change == "revoke":
        row.state = "revoked"
    db = SimpleNamespace(get=AsyncMock(side_effect=[row, user]), refresh=AsyncMock())
    monkeypatch.setattr(
        routes,
        "get_auth_version",
        AsyncMock(return_value=1 if change == "owner" else 0),
    )
    monkeypatch.setattr(
        routes,
        "_context",
        AsyncMock(return_value=(gateway, object(), version, release)),
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(routes._local(db, uuid4(), token))
    assert error.value.status_code == (403 if change == "owner" else 409)
