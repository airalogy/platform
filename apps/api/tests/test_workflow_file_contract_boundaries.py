"""Independent regressions for file port scope, unions and old graph payloads."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services.workflow_contracts import (
    WorkflowContractError,
    validate_workflow_graph,
)
from app.services.workflow_data import (
    protocol_field_catalog,
    resolve_workflow_bindings,
    validate_protocol_initial_values,
)
from app.services.workflow_file_contracts import protocol_file_spec
from tests.test_workflow_compute_contracts import compute_graph
from tests.test_workflow_file_contracts import FILE_ID, graph, schema, version


@pytest.mark.parametrize(
    "scope",
    [
        {"$id": "https://example.test/private-resource"},
        {"$anchor": "file"},
        {"$dynamicAnchor": "file"},
        {"$recursiveAnchor": True},
        {"$schema": "https://json-schema.org/draft/2019-09/schema"},
    ],
)
@pytest.mark.parametrize("location", ["field", "variables", "document"])
def test_unsupported_resource_scopes_are_excluded_for_sources_and_targets(
    scope, location
):
    value = version()
    if location == "field":
        value.json_schema["vars"]["properties"]["file"].update(scope)
    elif location == "variables":
        value.json_schema["vars"].update(scope)
    else:
        value.json_schema.update(scope)
    assert protocol_field_catalog(value, include_files=True) == {}
    assert protocol_field_catalog(value, include_files=True, for_target=True) == {}


def test_a_nested_resource_cannot_resolve_its_pointer_against_an_outer_resource():
    field = {
        "$id": "https://example.test/nested",
        "$defs": {"File": schema("pdf")},
        "$ref": "#/$defs/File",
    }
    outer = {
        "$defs": {"File": schema("csv")},
        "type": "object",
        "properties": {"file": field},
    }
    assert protocol_file_spec(field, [outer]) is None
    value = SimpleNamespace(version="1.0.0", json_schema={"vars": outer})
    assert protocol_field_catalog(value, include_files=True) == {}


def test_file_union_keeps_all_declared_extensions_but_never_accepts_plain_text():
    union = {"anyOf": [schema("pdf"), schema("csv"), {"type": "null"}]}
    spec = protocol_file_spec(union, [union])
    assert spec.nullable is True
    assert spec.file_extensions == ["csv", "pdf"]
    unsafe = {"anyOf": [union, {"type": "string"}]}
    assert protocol_file_spec(unsafe, [unsafe]) is None


@pytest.mark.parametrize("value", [None, True, 1, {}, [FILE_ID]])
def test_nullable_file_ports_never_convert_null_or_non_file_values_to_a_binding(value):
    catalog = protocol_field_catalog(
        version({"anyOf": [schema(), {"type": "null"}]}), include_files=True
    )
    assert catalog[("var", "file")].nullable
    with pytest.raises(WorkflowContractError):
        resolve_workflow_bindings(
            graph(),
            "target",
            {"source": {"var": {"file": value}}},
            {"source": catalog, "target": catalog},
        )


def test_target_enum_and_pattern_constraints_are_validated_beyond_the_extension():
    constrained = {"allOf": [schema(), {"enum": [FILE_ID]}, {"pattern": r"\.csv$"}]}
    value = version(constrained)
    assert protocol_field_catalog(value, include_files=True, for_target=True)
    validate_protocol_initial_values(value, {"file": FILE_ID})
    other = FILE_ID.replace("000000000001", "000000000002")
    with pytest.raises(WorkflowContractError):
        validate_protocol_initial_values(value, {"file": other})


def test_legacy_compute_payloads_do_not_acquire_file_defaults_or_allow_them_explicitly():
    original = compute_graph()
    graph_value = validate_workflow_graph(original)
    payload = graph_value.model_dump(mode="json")
    assert payload["schema_version"] == 3
    assert all("compute_file_outputs" not in node for node in payload["nodes"])
    assert validate_workflow_graph(deepcopy(payload)).model_dump(mode="json") == payload
    original["nodes"][1]["compute_file_outputs"] = []
    with pytest.raises(ValueError, match="schema_version 4"):
        validate_workflow_graph(original)


def test_compute_scalar_and_file_output_ids_cannot_collide():
    original = compute_graph()
    original["schema_version"] = 4
    original["nodes"][1]["compute_file_outputs"] = [
        {"output_id": "mean_dose", "mount_name": "mean.csv"}
    ]
    with pytest.raises(ValueError, match="output IDs must be unique"):
        validate_workflow_graph(original)
