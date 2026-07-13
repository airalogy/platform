from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.project import ProjectRole
from app.routers.access import GrantParams, GrantUpdateParams
from app.services.access_control import (
    AccessDecision,
    AccessSource,
    ROLE_CAPABILITIES,
    can_delegate,
    role_catalog,
)


def source(role_key: str) -> AccessSource:
    return AccessSource(
        source_type="test",
        role_key=role_key,
        scope_type="project",
        scope_id="project-id",
    )


def test_role_catalog_exposes_stable_capability_sets():
    catalog = {role["key"]: role for role in role_catalog()}

    assert set(catalog) == set(ROLE_CAPABILITIES)
    assert "access.manage" in catalog["lab_owner"]["capabilities"]
    assert catalog["lab_owner"]["grantable"] is False
    assert catalog["project_manager"]["grantable"] is True
    assert "record.read" in catalog["viewer"]["capabilities"]
    assert "record.create" not in catalog["viewer"]["capabilities"]


def test_decision_unions_multiple_roles_and_explains_sources():
    decision = AccessDecision()
    decision.add("viewer", source("viewer"))
    decision.add("recorder", source("recorder"))

    assert decision.allows("read_record")
    assert decision.allows("create_record")
    assert not decision.allows("delete_record")
    assert decision.strongest_project_role == ProjectRole.RECORDER
    assert {item["role_key"] for item in decision.as_dict()["sources"]} == {
        "viewer",
        "recorder",
    }


def test_delegation_requires_management_and_capability_ceiling():
    admin = AccessDecision()
    admin.add("lab_admin", source("lab_admin"))
    project_manager = AccessDecision()
    project_manager.add("project_manager", source("project_manager"))
    contributor = AccessDecision()
    contributor.add("contributor", source("contributor"))

    assert can_delegate(admin, "project_manager")
    assert not can_delegate(admin, "lab_admin")
    assert not can_delegate(admin, "lab_owner")
    assert can_delegate(project_manager, "contributor")
    assert not can_delegate(contributor, "viewer")
    assert not can_delegate(admin, "unknown")


def grant_payload(**overrides):
    payload = {
        "lab_id": uuid4(),
        "subject_type": "user",
        "user_id": uuid4(),
        "scope_type": "lab",
        "role_key": "viewer",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "overrides",
    [
        {"subject_type": "user", "user_id": None},
        {"subject_type": "team", "user_id": uuid4(), "group_id": 1},
        {"scope_type": "project", "project_id": None},
        {"scope_type": "lab", "project_id": uuid4()},
        {"role_key": "custom_role"},
        {"role_key": "lab_admin"},
    ],
)
def test_grant_shape_rejects_ambiguous_subjects_scopes_and_roles(overrides):
    with pytest.raises(ValidationError):
        GrantParams(**grant_payload(**overrides))


def test_protocol_grant_can_include_project_for_reference_validation():
    project_id = uuid4()
    params = GrantParams(
        **grant_payload(
            scope_type="protocol",
            project_id=project_id,
            protocol_id=uuid4(),
        )
    )

    assert params.project_id == project_id


def test_grant_update_validates_expiry_and_clear_conflicts():
    past = datetime.now(UTC) - timedelta(minutes=1)
    future = datetime.now(UTC) + timedelta(minutes=1)

    with pytest.raises(ValidationError):
        GrantUpdateParams(expires_at=past)
    with pytest.raises(ValidationError):
        GrantUpdateParams(expires_at=future, clear_expiry=True)

    assert GrantUpdateParams(expires_at=future).expires_at == future.replace(tzinfo=None)
