import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.main import app
from app.models.access_control import AccessScopeType
from app.models.resource import InventoryEvent, ResourceLineage, ResourceRevision
from app.routers import resources as resources_router
from app.routers.access import GrantParams
from app.routers.resources import (
    ResourceTypeParams,
    SampleLineageParams,
    _lineage_data,
    _validation_issues,
    resource_capabilities,
)
from app.services import research_runtime
from app.services.resource_bindings import extract_resource_bindings
from app.services.resource_index import build_resource_indexes
from app.services.resource_lineage import (
    ResourceLineageError,
    ensure_lineage_is_acyclic,
)
from app.services.resource_units import UnitError, convert_quantity
from app.services.schema_governance import (
    SchemaGovernanceError,
    build_compatibility_report,
    find_migration_path,
    preview_declarative_migration,
    projection_not_collected,
)
from fastapi import HTTPException
from pydantic import ValidationError


def test_inventory_units_use_exact_decimal_and_reject_cross_dimension():
    assert convert_quantity("1.25", "mg", "ug") == Decimal("1250")
    assert convert_quantity("0.5", "mL", "uL") == Decimal("500")
    with pytest.raises(UnitError, match="cannot convert"):
        convert_quantity("1", "mg", "mL")


def test_model_serialization_uses_mapped_attribute_names():
    event = InventoryEvent(
        lab_id=uuid4(),
        kind="receipt",
        resource_id=uuid4(),
        quantity=Decimal("1"),
        unit="mL",
        actor_user_id=uuid4(),
        idempotency_key="serialization-test",
        event_metadata={"source": "test"},
    )

    payload = event.as_dict()

    assert payload["event_metadata"] == {"source": "test"}
    assert "metadata" not in payload


def test_resource_validation_uses_aimd_variable_schema():
    schema = {
        "steps": {},
        "vars": {
            "type": "object",
            "properties": {"construct_name": {"type": "string"}},
            "required": ["construct_name"],
        },
        "checks": {},
    }

    assert _validation_issues(schema, {}) == [
        {
            "path": "",
            "message": "'construct_name' is a required property",
        }
    ]
    assert _validation_issues(schema, {"construct_name": "pUC19"}) == []


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


def test_sample_capability_rejects_equipment_only_capabilities():
    with pytest.raises(ValidationError, match="equipment-only"):
        ResourceTypeParams(
            protocol_version_id=uuid4(),
            code="sample",
            name="Sample",
            capabilities={"sample": True, "booking": True},
            booking_policy="auto",
        )


def test_sample_lineage_rejects_self_reference():
    resource_id = uuid4()
    with pytest.raises(ValidationError, match="own lineage parent"):
        SampleLineageParams(
            parent_resource_id=resource_id,
            child_resource_id=resource_id,
            relationship="derived_from",
            reason="invalid",
            idempotency_key="self-edge",
        )


def test_sample_lineage_cycle_detection_walks_existing_graph():
    parent_id = uuid4()
    child_id = uuid4()
    intermediate_id = uuid4()
    db_session = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                SimpleNamespace(all=lambda: [intermediate_id]),
                SimpleNamespace(all=lambda: [parent_id]),
            ]
        )
    )

    with pytest.raises(ResourceLineageError, match="acyclic"):
        asyncio.run(
            ensure_lineage_is_acyclic(
                db_session,
                parent_resource_id=parent_id,
                child_resource_id=child_id,
            )
        )


def test_resource_lineage_model_accepts_manual_sample_provenance():
    edge = ResourceLineage(
        parent_resource_id=uuid4(),
        child_resource_id=uuid4(),
        relationship="aliquot_of",
        reason="Tube A was aliquoted into Tube B",
        created_by_user_id=uuid4(),
        idempotency_key="lineage-1",
    )

    assert edge.record_id is None
    assert edge.record_version is None
    assert edge.relationship == "aliquot_of"


def test_sample_lineage_redacts_an_inaccessible_connected_resource():
    parent_id = uuid4()
    child_id = uuid4()
    edge = ResourceLineage(
        parent_resource_id=parent_id,
        child_resource_id=child_id,
        record_id=uuid4(),
        record_version=2,
        source_action_id=uuid4(),
        relationship="derived_from",
        reason="Sensitive upstream identity",
        created_by_user_id=uuid4(),
        idempotency_key="private-edge",
    )

    payload = _lineage_data(
        edge,
        current_resource_id=child_id,
        resources={
            parent_id: SimpleNamespace(name="Restricted parent", code="SECRET"),
            child_id: SimpleNamespace(name="Visible child", code="SAMPLE-2"),
        },
        access={parent_id: False, child_id: True},
    )

    assert payload["parent_resource_id"] is None
    assert payload["parent_name"] is None
    assert payload["child_resource_id"] == child_id
    assert payload["reason"] == ""
    assert payload["record_id"] is None
    assert payload["source_action_id"] is None
    assert payload["created_by_user_id"] is None
    assert payload["redacted"] is True
    assert "idempotency_key" not in payload


def test_resource_resolver_lists_only_project_authorized_research_reservations(
    monkeypatch,
):
    lab_id = uuid4()
    project_id = uuid4()
    resource_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    resource = SimpleNamespace(
        id=resource_id,
        name="Shared reagent",
        code="REAGENT-1",
        status="active",
    )
    project = SimpleNamespace(id=project_id, lab_id=lab_id)
    typed = SimpleNamespace(id=uuid4())
    inventory = SimpleNamespace(
        id=uuid4(),
        container_id=uuid4(),
        quantity=Decimal("2.5"),
        unit="mL",
        expires_at=None,
    )
    action = SimpleNamespace(title="Reserve assay reagent")
    task = SimpleNamespace(id=uuid4(), title="Dose response")
    db_session = SimpleNamespace(
        get=AsyncMock(return_value=project),
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(all=lambda: []),
                SimpleNamespace(all=lambda: [(typed, inventory, action, task)]),
            ]
        ),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
    )
    has_access = AsyncMock(return_value=True)
    monkeypatch.setattr(
        resources_router,
        "_resource",
        AsyncMock(return_value=resource),
    )
    monkeypatch.setattr(
        resources_router,
        "_can_read_resource",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        research_runtime,
        "has_research_capability",
        has_access,
    )

    result = asyncio.run(
        resources_router.resolver_availability(
            lab_id=lab_id,
            resource_id=resource_id,
            current_user=user,
            db_session=db_session,
            project_id=project_id,
        )
    )

    has_access.assert_awaited_once_with(
        db_session,
        user=user,
        project=project,
        capability="research.run",
    )
    assert result["inventory_reservations"] == [
        {
            "id": inventory.id,
            "research_reservation_id": typed.id,
            "container_id": inventory.container_id,
            "quantity": inventory.quantity,
            "unit": inventory.unit,
            "expires_at": None,
            "task_id": task.id,
            "task_title": task.title,
            "action_title": action.title,
            "label": "Dose response · 2.5 mL",
        }
    ]


def test_resource_resolver_keeps_normal_inventory_available_without_research_access(
    monkeypatch,
):
    lab_id = uuid4()
    project_id = uuid4()
    resource = SimpleNamespace(
        id=uuid4(),
        name="Shared reagent",
        code="REAGENT-1",
        status="active",
    )
    project = SimpleNamespace(id=project_id, lab_id=lab_id)
    db_session = SimpleNamespace(
        get=AsyncMock(return_value=project),
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
    )
    monkeypatch.setattr(
        resources_router,
        "_resource",
        AsyncMock(return_value=resource),
    )
    monkeypatch.setattr(
        resources_router,
        "_can_read_resource",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        research_runtime,
        "has_research_capability",
        AsyncMock(return_value=False),
    )

    result = asyncio.run(
        resources_router.resolver_availability(
            lab_id=lab_id,
            resource_id=resource.id,
            current_user=SimpleNamespace(id=uuid4()),
            db_session=db_session,
            project_id=project_id,
        )
    )

    assert result["containers"] == []
    assert result["inventory_reservations"] == []
    assert db_session.execute.await_count == 1


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


def test_infrastructure_manager_can_open_shell_without_resource_read(monkeypatch):
    decision = SimpleNamespace(
        capabilities={"research.compute.manage"},
        as_dict=lambda: {
            "capabilities": ["research.compute.manage"],
            "role_keys": ["research_compute_manager"],
            "sources": [],
        },
    )
    monkeypatch.setattr(
        resources_router, "_decision", AsyncMock(return_value=decision)
    )

    result = asyncio.run(
        resource_capabilities(
            uuid4(), SimpleNamespace(id=uuid4()), SimpleNamespace()
        )
    )

    assert result["capabilities"] == ["research.compute.manage"]


def test_unrelated_member_cannot_open_infrastructure_shell(monkeypatch):
    decision = SimpleNamespace(capabilities={"research.read"})
    monkeypatch.setattr(
        resources_router, "_decision", AsyncMock(return_value=decision)
    )

    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            resource_capabilities(
                uuid4(), SimpleNamespace(id=uuid4()), SimpleNamespace()
            )
        )

    assert raised.value.status_code == 403


def test_openapi_exposes_resource_and_schema_governance_contracts():
    paths = app.openapi()["paths"]
    assert "/labs/{lab_id}/resource-library/resources" in paths
    assert "/labs/{lab_id}/resource-library/lineage/preview" in paths
    assert "/labs/{lab_id}/resource-library/lineage/confirm" in paths
    assert "/labs/{lab_id}/resource-library/capabilities" in paths
    assert "/labs/{lab_id}/resource-library/definition-versions" in paths
    assert "/labs/{lab_id}/resource-library/inventory/reservations" in paths
    assert "/labs/{lab_id}/resource-library/inventory/transfers" in paths
    assert "/labs/{lab_id}/resource-library/resolver/search" in paths
    assert (
        "/protocols/{protocol_id}/records/{record_id}/migration-preview"
        in paths
    )
