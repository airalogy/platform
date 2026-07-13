from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.access_control import AccessSubjectType
from app.models.group import OrganizationalUnitType
from app.models.project import ProjectRole
from app.main import app
from app.routers.access import (
    GrantParams,
    GrantUpdateParams,
    OrganizationalUnitCreateParams,
)
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


def test_openapi_exposes_only_canonical_organizational_unit_contract():
    schema = app.openapi()

    assert "/access/organizational-units" in schema["paths"]
    assert "/access/labs/{lab_id}/organizational-units" in schema["paths"]
    assert not any("/access/teams" in path for path in schema["paths"])
    assert schema["components"]["schemas"]["AccessSubjectType"]["enum"] == [
        "user",
        "org_unit",
    ]


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


def test_organizational_unit_grant_uses_canonical_subject_fields():
    params = GrantParams(
        **grant_payload(
            subject_type="org_unit",
            user_id=None,
            org_unit_id=7,
        )
    )

    assert params.subject_type == AccessSubjectType.ORG_UNIT
    assert params.org_unit_id == 7
    assert params.group_id == 7


def test_legacy_team_grant_is_normalized_at_the_api_boundary():
    params = GrantParams(
        **grant_payload(
            subject_type="team",
            user_id=None,
            group_id=9,
        )
    )

    assert params.subject_type == AccessSubjectType.ORG_UNIT
    assert params.org_unit_id == 9
    assert params.group_id == 9


def test_organizational_unit_grant_rejects_conflicting_identifiers():
    with pytest.raises(ValidationError):
        GrantParams(
            **grant_payload(
                subject_type="org_unit",
                user_id=None,
                org_unit_id=7,
                group_id=9,
            )
        )


def test_organizational_unit_create_params_normalize_parent_and_type():
    parent_id = 5
    params = OrganizationalUnitCreateParams(
        lab_id=uuid4(),
        uid="molecular_biology",
        name="Molecular Biology",
        parent_unit_id=parent_id,
    )

    assert params.unit_type == OrganizationalUnitType.RESEARCH_GROUP
    assert params.parent_unit_id == parent_id
    assert params.parent_group_id == parent_id


def test_organizational_unit_create_params_reject_invalid_type():
    with pytest.raises(ValidationError):
        OrganizationalUnitCreateParams(
            lab_id=uuid4(),
            uid="molecular_biology",
            name="Molecular Biology",
            unit_type="division",
        )


def test_grant_update_validates_expiry_and_clear_conflicts():
    past = datetime.now(UTC) - timedelta(minutes=1)
    future = datetime.now(UTC) + timedelta(minutes=1)

    with pytest.raises(ValidationError):
        GrantUpdateParams(expires_at=past)
    with pytest.raises(ValidationError):
        GrantUpdateParams(expires_at=future, clear_expiry=True)

    assert GrantUpdateParams(expires_at=future).expires_at == future.replace(tzinfo=None)
