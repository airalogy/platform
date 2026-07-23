from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.main import app
from app.models.access_control import AccessScopeType
from app.models.resource import ResourceRevision
from app.routers.access import GrantParams
from app.services.resource_bindings import extract_resource_bindings
from app.services.resource_index import build_resource_indexes
from app.services.resource_units import UnitError, convert_quantity
from app.services.schema_governance import (
    SchemaGovernanceError,
    build_compatibility_report,
    find_migration_path,
    preview_declarative_migration,
    projection_not_collected,
)


def test_inventory_units_use_exact_decimal_and_reject_cross_dimension():
    assert convert_quantity("1.25", "mg", "ug") == Decimal("1250")
    assert convert_quantity("0.5", "mL", "uL") == Decimal("500")
    with pytest.raises(UnitError, match="cannot convert"):
        convert_quantity("1", "mg", "mL")


def test_resource_ref_bindings_keep_role_quantity_container_and_booking():
    fields = {
        "vars": [
            {
                "id": "sample",
                "type": "ResourceRef[Sample]",
                "kwargs": {
                    "resource_role": "input",
                    "quantity_field": "amount",
                    "container_required": True,
                },
            },
            {
                "id": "instrument",
                "type": "ResourceRef[Instrument] | None",
                "kwargs": {
                    "resource_role": "equipment",
                    "booking_required": True,
                },
            },
        ]
    }
    data = {
        "var": {
            "amount": "2.5",
            "sample": {
                "id": str(uuid4()),
                "container_id": str(uuid4()),
                "unit": "mL",
            },
            "instrument": {
                "id": str(uuid4()),
                "booking_id": str(uuid4()),
            },
        }
    }

    bindings = extract_resource_bindings(fields, data)

    assert [item.role for item in bindings] == ["input", "equipment"]
    assert bindings[0].quantity == Decimal("2.5")
    assert bindings[0].unit == "mL"
    assert bindings[0].container_required is True
    assert bindings[1].booking_required is True


def test_resource_index_projects_scalar_reference_and_list_values():
    revision = ResourceRevision(
        id=uuid4(),
        resource_id=uuid4(),
        resource_type_revision_id=uuid4(),
        revision=1,
        data={
            "name": "pUC19",
            "concentration": "12.5",
            "active": True,
            "tags": ["cloning", "ampicillin"],
            "owner": {"entity": "user", "id": "user-1", "label": "Ada"},
        },
        created_by_user_id=uuid4(),
    )

    rows = build_resource_indexes(
        resource_type_id=uuid4(),
        resource_id=revision.resource_id,
        revision=revision,
    )
    indexed = {(row.path, row.ordinal): row for row in rows}

    assert indexed[("name", 0)].value_text == "pUC19"
    assert indexed[("concentration", 0)].value_numeric == Decimal("12.5")
    assert indexed[("active", 0)].value_boolean is True
    assert indexed[("tags", 1)].value_text == "ampicillin"
    assert indexed[("owner", 0)].ref_id == "user-1"


def test_schema_release_requires_semver_matching_breaking_change():
    previous = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
    }
    breaking = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "code": {"type": "string"},
        },
        "required": ["code"],
    }

    with pytest.raises(SchemaGovernanceError, match="require"):
        build_compatibility_report(
            previous,
            breaking,
            previous_version="1.0.0",
            current_version="1.1.0",
        )
    report = build_compatibility_report(
        previous,
        breaking,
        previous_version="1.0.0",
        current_version="2.0.0",
    )
    assert report["actual_bump"] == "major"
    assert report["semver_valid"] is True


def test_declarative_migration_preserves_original_and_marks_not_collected():
    source = {
        "type": "object",
        "properties": {
            "var": {
                "type": "object",
                "properties": {"old_name": {"type": "string"}},
            }
        },
    }
    target = {
        "type": "object",
        "properties": {
            "var": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "new_measurement": {"type": "number"},
                },
            }
        },
    }
    manifest = {
        "version": "airalogy.migration.v1",
        "from": "1.0.0",
        "to": "2.0.0",
        "operations": [
            {"op": "rename", "from": "var.old_name", "to": "var.name"}
        ],
    }
    original = {"var": {"old_name": "pUC19"}}

    preview = preview_declarative_migration(
        original,
        manifest,
        source_schema=source,
        target_schema=target,
    )

    assert original == {"var": {"old_name": "pUC19"}}
    assert preview["data"] == {"var": {"name": "pUC19"}}
    assert "var.new_measurement" in preview["not_collected"]
    assert projection_not_collected(source, target) == [
        "var.name",
        "var.new_measurement",
    ]


def test_migration_path_uses_shortest_deterministic_published_route():
    manifests = [
        {"from": "1.0.0", "to": "1.1.0"},
        {"from": "1.1.0", "to": "2.0.0"},
        {"from": "1.0.0", "to": "1.5.0"},
        {"from": "1.5.0", "to": "2.0.0"},
        {"from": "1.0.0", "to": "2.0.0"},
    ]

    assert find_migration_path(manifests, "1.0.0", "2.0.0") == [
        {"from": "1.0.0", "to": "2.0.0"}
    ]
    assert find_migration_path(manifests[:-1], "1.0.0", "2.0.0") == [
        {"from": "1.0.0", "to": "1.1.0"},
        {"from": "1.1.0", "to": "2.0.0"},
    ]


@pytest.mark.parametrize(
    ("scope_type", "field"),
    [
        (AccessScopeType.RESOURCE_TYPE, "resource_type_id"),
        (AccessScopeType.RESOURCE, "resource_id"),
        (AccessScopeType.LOCATION, "location_id"),
    ],
)
def test_resource_grant_scopes_require_exact_target(scope_type, field):
    payload = {
        "lab_id": uuid4(),
        "subject_type": "user",
        "user_id": uuid4(),
        "scope_type": scope_type,
        field: uuid4(),
        "role_key": "resource_operator",
    }
    params = GrantParams(**payload)
    assert getattr(params, field) is not None

    payload[field] = None
    with pytest.raises(ValidationError):
        GrantParams(**payload)


def test_openapi_exposes_resource_and_schema_governance_contracts():
    paths = app.openapi()["paths"]
    assert "/labs/{lab_id}/resource-library/resources" in paths
    assert "/labs/{lab_id}/resource-library/definition-versions" in paths
    assert "/labs/{lab_id}/resource-library/inventory/reservations" in paths
    assert "/labs/{lab_id}/resource-library/inventory/transfers" in paths
    assert "/labs/{lab_id}/resource-library/resolver/search" in paths
    assert (
        "/protocols/{protocol_id}/records/{record_id}/migration-preview"
        in paths
    )
