"""Files are typed, version-gated references; neither text nor storage URLs."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.services.workflow_contracts import (
    WorkflowComputeFileOutput,
    WorkflowContractError,
    WorkflowFieldSpec,
    validate_workflow_graph,
    workflow_execution_digest,
)
from app.services.workflow_data import (
    protocol_field_catalog,
    resolve_workflow_bindings,
    validate_protocol_initial_values,
    validate_workflow_data,
)
from app.services.workflow_definitions import validate_initial_values
from app.services.workflow_file_contracts import (
    compute_file_output_catalog,
    parse_workflow_file_id,
    protocol_file_spec,
)

FILE_ID = "airalogy.id.file.00000000-0000-4000-8000-000000000001.csv"


def schema(extension="csv"):
    return {"type": "string", "airalogy_type": "FileId", "file_extension": extension}


def version(field=None):
    return SimpleNamespace(
        version="1.0.0",
        json_schema={
            "vars": {"type": "object", "properties": {"file": field or schema()}}
        },
    )


def graph(**changes):
    return validate_workflow_graph(
        {
            "schema_version": 4,
            "nodes": [
                {
                    "kind": "protocol",
                    "node_id": name,
                    "protocol_id": "00000000-0000-4000-8000-000000000002",
                    "protocol_version_id": "00000000-0000-4000-8000-000000000003",
                }
                for name in ("source", "target")
            ],
            "edges": [
                {
                    "edge_id": "next",
                    "source_node_id": "source",
                    "target_node_id": "target",
                }
            ],
            "bindings": [
                {
                    "binding_id": "file",
                    "source_node_id": "source",
                    "source_path": ["var", "file"],
                    "target_node_id": "target",
                    "target_path": ["var", "file"],
                    "value_type": "file",
                }
            ],
            **changes,
        }
    )


def test_file_catalog_is_opt_in_and_preserves_scalar_contract():
    assert protocol_field_catalog(version()) == {}
    catalog = protocol_field_catalog(version(), include_files=True, for_target=True)
    assert catalog[("var", "file")].model_dump(mode="json") == {
        "value_type": "file",
        "nullable": False,
        "unit": None,
        "file_extensions": ["csv"],
    }
    assert WorkflowFieldSpec(value_type="string").model_dump() == {
        "value_type": "string",
        "nullable": False,
        "unit": None,
    }


@pytest.mark.parametrize(
    "field",
    [
        schema(),
        {"type": "string", "airalogy_type": "FileIdCSV"},
        {
            "allOf": [
                {"type": "string"},
                {"airalogy_type": "FileId", "file_extension": "csv"},
            ]
        },
        {"anyOf": [schema(), {"type": "null"}]},
        {"oneOf": [schema(), {"type": "null"}]},
        {
            "type": ["string", "null"],
            "airalogy_type": "FileId",
            "file_extension": "csv",
        },
    ],
)
def test_file_annotations_and_nullable_branches(field):
    spec = protocol_file_spec(field, [field])
    assert spec.value_type == "file" and spec.file_extensions == ["csv"]


def test_local_refs_and_full_target_assertions_are_preserved():
    document = {
        "$defs": {"File": schema()},
        "type": "object",
        "properties": {
            "file": {"$ref": "#/$defs/File", "minLength": 64},
        },
    }
    v = SimpleNamespace(version="1.0.0", json_schema={"vars": document})
    assert protocol_field_catalog(v, include_files=True)[
        ("var", "file")
    ].file_extensions == ["csv"]
    with pytest.raises(WorkflowContractError, match="pinned Protocol Schema"):
        validate_protocol_initial_values(v, {"file": FILE_ID})


@pytest.mark.parametrize(
    "field",
    [
        {"type": "string"},
        {"type": "string", "file_extension": "csv"},
        {"type": "string", "airalogy_type": "DataAsset"},
        {"type": "string", "airalogy_type": "FileIdSomethingUnknown"},
        {"type": "array", "items": schema()},
        {"anyOf": [schema(), {"type": "string"}]},
        {"allOf": [schema(), {"airalogy_type": "FileIdPDF"}]},
        {**schema(), "contentEncoding": "base64"},
        {**schema(), "unit": "mg"},
        {**schema(), "file_extension": "../csv"},
        {"$ref": "https://example.test/file"},
        {"$dynamicRef": "#file"},
        {**schema(), "if": {}, "then": {}},
    ],
)
def test_ambiguous_or_unsupported_files_are_not_exposed(field):
    assert protocol_file_spec(field, [field]) is None


def test_conflicting_local_definitions_and_recursive_schemas_fail_closed():
    field = {"$ref": "#/$defs/File"}
    assert (
        protocol_file_spec(
            field, [{"$defs": {"File": schema()}}, {"$defs": {"File": schema("pdf")}}]
        )
        is None
    )
    document = {"$defs": {"File": {"$ref": "#/$defs/File"}}}
    assert protocol_file_spec(field, [document]) is None
    nested = schema()
    for _ in range(20):
        nested = {"allOf": [nested]}
    assert protocol_file_spec(nested, [nested]) is None


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        [FILE_ID],
        "https://example.test/file.csv",
        "/tmp/file.csv",
        FILE_ID + "?token=private",
        FILE_ID.replace(".csv", ".CSV"),
        FILE_ID.replace(".csv", ".tar.gz"),
        FILE_ID + "\n",
    ],
)
def test_only_canonical_file_ids_are_accepted(value):
    with pytest.raises(WorkflowContractError):
        parse_workflow_file_id(value)


def test_file_binding_checks_both_extensions_and_preserves_value_receipt():
    catalog = protocol_field_catalog(version(), include_files=True)
    result = resolve_workflow_bindings(
        graph(),
        "target",
        {"source": {"var": {"file": FILE_ID}}},
        {"source": catalog, "target": catalog},
    )
    assert result.initial_values == {"file": FILE_ID}
    assert result.bindings[0]["value_type"] == "file"
    assert len(result.bindings[0]["value_digest"]) == 64
    assert parse_workflow_file_id(FILE_ID) == (
        UUID("00000000-0000-4000-8000-000000000001"),
        "csv",
    )
    with pytest.raises(WorkflowContractError, match="extensions conflict"):
        validate_workflow_data(
            graph(),
            {
                "source": catalog,
                "target": protocol_field_catalog(
                    version(schema("pdf")), include_files=True
                ),
            },
        )
    generic = {("var", "file"): WorkflowFieldSpec(value_type="file")}
    with pytest.raises(WorkflowContractError, match="extension conflicts"):
        resolve_workflow_bindings(
            graph(),
            "target",
            {"source": {"var": {"file": FILE_ID.replace(".csv", ".pdf")}}},
            {"source": generic, "target": catalog},
        )


def test_static_files_need_runtime_authorization_not_just_schema_validity():
    with pytest.raises(ValueError, match="authorized upstream binding"):
        validate_initial_values(version(), {"file": FILE_ID})
    validate_initial_values(version(), {"file": FILE_ID}, allow_files=True)


@pytest.mark.parametrize("schema_version", [1, 2, 3])
def test_files_cannot_enter_legacy_graphs_and_empty_defaults_keep_digests(
    schema_version,
):
    with pytest.raises(
        (ValidationError, WorkflowContractError), match="schema_version 4"
    ):
        graph(schema_version=schema_version)
    old = graph(schema_version=schema_version, bindings=[])
    data = old.model_dump(mode="json")
    assert all("compute_file_outputs" not in node for node in data["nodes"])
    assert workflow_execution_digest(old) == workflow_execution_digest(
        validate_workflow_graph(deepcopy(data))
    )


def test_compute_file_ports_use_exact_declared_mount_not_result_json_paths():
    recipe = {
        "kind": "compute",
        "output_files": [{"mount_name": "summary.csv", "required": True}],
    }
    port = WorkflowComputeFileOutput(output_id="summary", mount_name="summary.csv")
    assert compute_file_output_catalog(recipe, [port])[
        ("analysis", "summary")
    ].file_extensions == ["csv"]
    with pytest.raises(WorkflowContractError, match="declared manifest"):
        compute_file_output_catalog(
            recipe, [port.model_copy(update={"mount_name": "private.csv"})]
        )
    with pytest.raises(ValidationError):
        WorkflowComputeFileOutput(output_id="summary", mount_name="../private.csv")
    with pytest.raises(WorkflowContractError):
        compute_file_output_catalog({"kind": "builtin"}, [port])


def test_file_specs_cannot_masquerade_as_unit_bearing_scalar_fields():
    with pytest.raises((ValidationError, WorkflowContractError)):
        WorkflowFieldSpec(value_type="file", unit="mg")
    with pytest.raises((ValidationError, WorkflowContractError)):
        WorkflowFieldSpec(value_type="string", file_extensions=["csv"])


def test_one_source_file_can_fill_two_fields_without_overwriting_the_source():
    payload = graph().model_dump(mode="json")
    payload["bindings"].append({
        **payload["bindings"][0], "binding_id": "second", "target_path": ["var", "second"],
    })
    g = validate_workflow_graph(payload)
    catalog = protocol_field_catalog(version(), include_files=True)
    target = {**catalog, ("var", "second"): catalog[("var", "file")]}
    outputs = {"source": {"var": {"file": FILE_ID}}}
    original = deepcopy(outputs)
    first = FILE_ID.replace("000000000001", "000000000011")
    second = FILE_ID.replace("000000000001", "000000000012")
    result = resolve_workflow_bindings(
        g, "target", outputs, {"source": catalog, "target": target},
        file_values_by_binding={"file": first, "second": second},
    )
    assert result.initial_values == {"file": first, "second": second}
    assert outputs == original
    for invalid in ({"file": first}, {"file": first, "second": second, "unknown": first}):
        with pytest.raises(WorkflowContractError, match="exact target binding set"):
            resolve_workflow_bindings(g, "target", outputs, {"source": catalog, "target": target}, file_values_by_binding=invalid)
