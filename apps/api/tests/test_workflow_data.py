"""Exact scalar bindings share the existing local Protocol Schema interpreter."""

import copy
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.services.workflow_contracts import (
    MAX_WORKFLOW_BINDINGS,
    WorkflowBinding,
    WorkflowContractError,
    WorkflowFieldSpec,
    validate_workflow_graph,
    workflow_execution_digest,
)
from app.services.workflow_data import (
    protocol_field_catalog,
    protocol_prefill_schema,
    resolve_workflow_bindings,
    validate_protocol_initial_values,
    validate_workflow_data,
)


def version(properties=None, *, schema=None):
    return SimpleNamespace(
        version="1.2.3",
        json_schema=schema
        if schema is not None
        else {"vars": {"type": "object", "properties": properties or {}}},
    )


def node(node_id, **changes):
    return {
        "node_id": node_id,
        "kind": "protocol",
        "protocol_id": str(uuid4()),
        "protocol_version_id": str(uuid4()),
        **changes,
    }


def edge(source="source", target="target", **changes):
    return {
        "edge_id": f"{source}-to-{target}",
        "source_node_id": source,
        "target_node_id": target,
        **changes,
    }


def binding(**changes):
    return {
        "binding_id": "transfer",
        "source_node_id": "source",
        "source_path": ["var", "yield"],
        "target_node_id": "target",
        "target_path": ["var", "dose"],
        "value_type": "number",
        "unit": "mg",
        "cardinality": "one",
        **changes,
    }


def graph(*, nodes=None, edges=None, bindings=None):
    return validate_workflow_graph(
        {
            "schema_version": 1,
            "nodes": nodes if nodes is not None else [node("source"), node("target")],
            "edges": edges if edges is not None else [edge()],
            "bindings": bindings if bindings is not None else [binding()],
        }
    )


def catalogs(
    *,
    source_type="number",
    target_type="number",
    source_unit="mg",
    target_unit="mg",
    nullable=False,
):
    return {
        "source": {
            ("var", "yield"): WorkflowFieldSpec(
                value_type=source_type, unit=source_unit, nullable=nullable
            )
        },
        "target": {
            ("var", "dose"): WorkflowFieldSpec(
                value_type=target_type, unit=target_unit, nullable=nullable
            )
        },
    }


@pytest.mark.parametrize(
    "wrapper", ["vars", "research_variable", "root", "properties_var"]
)
def test_catalog_reuses_historical_schema_shapes_and_literal_keys(wrapper):
    variables = {
        "type": "object",
        "properties": {
            "yield.with/slash~": {"type": "number", "unit": " mg "},
            "accepted": {"type": "boolean"},
            "group": {"type": ["string", "null"]},
            "replicates": {"type": "integer"},
        },
    }
    schema = (
        {wrapper: variables}
        if wrapper in {"vars", "research_variable"}
        else variables
        if wrapper == "root"
        else {"type": "object", "properties": {"var": variables}}
    )
    original = copy.deepcopy(schema)
    result = protocol_field_catalog(version(schema=schema))
    assert result[("var", "yield.with/slash~")].unit == "mg"
    assert result[("var", "accepted")].value_type == "boolean"
    assert result[("var", "group")].nullable is True
    assert result[("var", "replicates")].value_type == "integer"
    assert schema == original


def test_catalog_shared_local_defs_scope_and_nullable_ref():
    schema = {
        "vars": {
            "type": "object",
            "properties": {
                "yield": {"anyOf": [{"$ref": "#/$defs/Measurement"}, {"type": "null"}]}
            },
            "$defs": {"Measurement": {"type": "number", "unit": "mg"}},
        },
        "$defs": {"Measurement": {"type": "string"}},
    }
    result = protocol_field_catalog(version(schema=schema))
    assert result[("var", "yield")] == WorkflowFieldSpec(
        value_type="number", nullable=True, unit="mg"
    )
    # A source's scalar type is visible, but conflicting definition documents
    # must not be guessed when preparing a target's full validation Schema.
    assert protocol_field_catalog(version(schema=schema), for_target=True) == {}


@pytest.mark.parametrize(
    "wrapper", ["vars", "research_variable", "root", "properties_var"]
)
def test_prefill_historical_roots_preserve_partial_required_and_ranges(wrapper):
    variables = {
        "type": "object",
        "properties": {
            "dose.with/slash~": {"type": "number", "minimum": 2, "maximum": 5},
            "later": {"type": "string"},
        },
        "required": ["dose.with/slash~", "later"],
    }
    schema = (
        {wrapper: variables}
        if wrapper in {"vars", "research_variable"}
        else variables
        if wrapper == "root"
        else {
            "type": "object",
            "properties": {"var": variables, "step": {"type": "object"}},
            "required": ["var", "step"],
            "additionalProperties": False,
        }
    )
    original = copy.deepcopy(schema)
    asset = version(schema=schema)
    validate_protocol_initial_values(asset, {"dose.with/slash~": 3})
    validate_protocol_initial_values(asset, {})
    for invalid in (0, 6, True, None, "3"):
        with pytest.raises(WorkflowContractError, match="pinned Protocol Schema"):
            validate_protocol_initial_values(asset, {"dose.with/slash~": invalid})
    with pytest.raises(WorkflowContractError, match="unknown"):
        validate_protocol_initial_values(asset, {"unknown": 3})
    assert schema == original


@pytest.mark.parametrize(
    "wrapper", ["vars", "research_variable", "root", "properties_var"]
)
def test_prefill_local_ref_root_and_target_ref_siblings_are_conjunctive(wrapper):
    variables = {
        "type": "object",
        "properties": {
            "dose": {"$ref": "#/$defs/Dose", "minimum": 5, "maximum": 20},
            "later": {"type": "string"},
        },
        "required": ["dose", "later"],
    }
    definitions = {"Dose": {"type": "number", "minimum": 2, "maximum": 10}}
    if wrapper == "root":
        schema = {
            "$ref": "#/$defs/Variables",
            "$defs": {**definitions, "Variables": variables},
        }
    elif wrapper == "properties_var":
        schema = {
            "type": "object",
            "properties": {"var": {"$ref": "#/$defs/Variables"}},
            "$defs": {**definitions, "Variables": variables},
        }
    else:
        schema = {
            wrapper: {"$ref": "#/$defs/Variables"},
            "$defs": {**definitions, "Variables": variables},
        }
    asset = version(schema=schema)
    validate_protocol_initial_values(asset, {"dose": 7})
    for invalid in (1, 3, 12, 21):
        with pytest.raises(WorkflowContractError):
            validate_protocol_initial_values(asset, {"dose": invalid})
    assert "$ref" not in json.dumps(protocol_prefill_schema(asset))
    assert (
        protocol_field_catalog(asset, for_target=True)[("var", "dose")].value_type
        == "number"
    )


def test_prefill_allof_at_root_keeps_repeated_property_constraints():
    asset = version(
        schema={
            "allOf": [
                {
                    "type": "object",
                    "properties": {"dose": {"type": "number", "minimum": 5}},
                    "required": ["dose"],
                },
                {
                    "type": "object",
                    "properties": {
                        "dose": {"type": "number", "maximum": 10},
                        "later": {"type": "string"},
                    },
                    "required": ["later"],
                },
            ],
        }
    )
    validate_protocol_initial_values(asset, {"dose": 7})
    for invalid in (4, 11):
        with pytest.raises(WorkflowContractError):
            validate_protocol_initial_values(asset, {"dose": invalid})


@pytest.mark.parametrize(
    "field,valid,invalid",
    [
        (
            {
                "type": "number",
                "allOf": [
                    {"minimum": 5},
                    {"minimum": 1},
                    {"maximum": 10},
                    {"maximum": 20},
                ],
            },
            7,
            [3, 12],
        ),
        ({"type": "number", "anyOf": [{"maximum": 2}, {"minimum": 8}]}, 1, [5]),
        ({"type": "number", "oneOf": [{"maximum": 5}, {"minimum": 3}]}, 1, [4]),
        ({"type": "number", "enum": [2, 4, 6], "minimum": 3}, 4, [2, 5]),
        (
            {
                "type": "integer",
                "multipleOf": 3,
                "exclusiveMinimum": 0,
                "exclusiveMaximum": 10,
            },
            6,
            [0, 5, 12, True],
        ),
        (
            {"type": "string", "format": "date"},
            "2026-09-13",
            ["2026-13-13", "tomorrow"],
        ),
        (
            {"type": "string", "format": "date-time"},
            "2026-09-13T10:20:30Z",
            ["2026-09-13", "not a timestamp"],
        ),
        (
            {"type": "string", "pattern": "^[A-Z]+$", "minLength": 2, "maxLength": 4},
            "AB",
            ["A", "ABCDE", "ab"],
        ),
        ({"type": "string", "const": "accepted"}, "accepted", ["rejected"]),
        ({"type": "number", "not": {"const": 3}}, 4, [3]),
    ],
)
def test_prefill_keeps_full_scalar_assertions(field, valid, invalid):
    asset = version({"value": field})
    validate_protocol_initial_values(asset, {"value": valid})
    for value in invalid:
        with pytest.raises(WorkflowContractError):
            validate_protocol_initial_values(asset, {"value": value})


def test_prefill_static_nested_values_keep_required_and_array_assertions():
    asset = version(
        {
            "configuration": {
                "type": "object",
                "properties": {
                    "replicates": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 1},
                        "minItems": 2,
                        "uniqueItems": True,
                    },
                },
                "required": ["replicates"],
                "additionalProperties": False,
            },
        }
    )
    validate_protocol_initial_values(asset, {"configuration": {"replicates": [1, 2]}})
    for value in (
        {},
        {"replicates": [1]},
        {"replicates": [1, 1]},
        {"replicates": [1, 0]},
        {"replicates": [1, 2], "extra": 3},
    ):
        with pytest.raises(WorkflowContractError):
            validate_protocol_initial_values(asset, {"configuration": value})


@pytest.mark.parametrize(
    "unsupported",
    [
        {"type": "number", "$ref": "https://example.invalid/schema"},
        {"type": "number", "$ref": "file:///private/secret.json"},
        {"type": "number", "$ref": "#missing-anchor"},
        {"type": "number", "$dynamicRef": "#value"},
        {"type": "number", "$id": "https://example.invalid/schema"},
        {"type": "number", "$schema": "http://json-schema.org/draft-07/schema#"},
        {"type": "string", "format": "unknown-custom-format"},
        {"type": "number", "customConstraint": 7},
    ],
)
def test_prefill_unsupported_selected_fields_fail_closed_without_blocking_others(
    unsupported,
):
    asset = version({"safe": {"type": "number"}, "unsupported": unsupported})
    validate_protocol_initial_values(asset, {"safe": 3})
    with pytest.raises(WorkflowContractError):
        validate_protocol_initial_values(asset, {"unsupported": 3})
    assert set(protocol_field_catalog(asset, for_target=True)) == {("var", "safe")}


def test_prefill_local_reference_scope_collision_is_not_guessed():
    asset = version(
        schema={
            "vars": {
                "type": "object",
                "properties": {"dose": {"$ref": "#/$defs/Dose"}},
                "$defs": {"Dose": {"type": "number", "maximum": 10}},
            },
            "$defs": {"Dose": {"type": "number", "maximum": 5}},
        }
    )
    with pytest.raises(
        WorkflowContractError, match="conflicting local definition scopes"
    ):
        validate_protocol_initial_values(asset, {"dose": 7})
    assert protocol_field_catalog(asset, for_target=True) == {}


@pytest.mark.parametrize(
    "envelope",
    [
        {"$schema": "http://json-schema.org/draft-07/schema#"},
        {"$id": "https://example.invalid/schema"},
        {"$vocabulary": {"https://example.invalid/vocabulary": True}},
    ],
)
def test_prefill_does_not_ignore_envelope_reference_scope_or_dialect(envelope):
    asset = version(
        schema={
            "vars": {"type": "object", "properties": {"dose": {"type": "number"}}},
            **envelope,
        }
    )
    with pytest.raises(WorkflowContractError):
        validate_protocol_initial_values(asset, {"dose": 3})
    assert protocol_field_catalog(asset, for_target=True) == {}


def test_prefill_wrapper_own_defs_resolve_without_dropping_ranges():
    asset = version(
        schema={
            "type": "object",
            "properties": {
                "var": {
                    "type": "object",
                    "properties": {"dose": {"$ref": "#/$defs/Dose"}},
                    "$defs": {"Dose": {"type": "number", "minimum": 5}},
                }
            },
        }
    )
    validate_protocol_initial_values(asset, {"dose": 7})
    with pytest.raises(WorkflowContractError):
        validate_protocol_initial_values(asset, {"dose": 3})


@pytest.mark.parametrize(
    "constraint",
    [
        {"minProperties": 2},
        {"if": {"required": ["step"]}, "then": {"required": ["quiz"]}},
    ],
)
def test_prefill_does_not_silently_project_complex_record_wrapper_constraints(
    constraint,
):
    asset = version(
        schema={
            "type": "object",
            "properties": {
                "var": {"type": "object", "properties": {"dose": {"type": "number"}}}
            },
            **constraint,
        }
    )
    with pytest.raises(WorkflowContractError, match="wrapper constraint"):
        validate_protocol_initial_values(asset, {"dose": 3})
    assert protocol_field_catalog(asset, for_target=True) == {}


def test_prefill_rejects_cyclic_local_refs_and_preserves_no_schema_empty_start():
    cyclic = version(
        schema={
            "type": "object",
            "properties": {"dose": {"$ref": "#/$defs/Dose"}},
            "$defs": {"Dose": {"$ref": "#/$defs/Dose"}},
        }
    )
    with pytest.raises(WorkflowContractError, match="bounds"):
        validate_protocol_initial_values(cyclic, {"dose": 3})
    validate_protocol_initial_values(SimpleNamespace(json_schema=None), {})
    with pytest.raises(WorkflowContractError):
        validate_protocol_initial_values(SimpleNamespace(json_schema=None), {"dose": 3})


def test_prefill_error_does_not_include_private_input_values():
    private = "a private experiment identifier"
    with pytest.raises(WorkflowContractError) as error:
        validate_protocol_initial_values(
            version({"value": {"type": "integer"}}), {"value": private}
        )
    assert private not in str(error.value)


def test_prefill_ref_siblings_preserve_unevaluated_properties_annotations():
    asset = version(
        schema={
            "$ref": "#/$defs/Variables",
            "unevaluatedProperties": False,
            "$defs": {
                "Variables": {
                    "type": "object",
                    "properties": {"dose": {"type": "number"}},
                }
            },
        }
    )
    validate_protocol_initial_values(asset, {"dose": 3})
    with pytest.raises(WorkflowContractError):
        validate_protocol_initial_values(asset, {"dose": 3, "unknown": 2})


@pytest.mark.parametrize("has_unsupported", [False, True])
def test_target_catalog_prepares_whole_original_schema_only_once(
    monkeypatch, has_unsupported
):
    import app.services.workflow_data as data

    prepared_calls = []
    compile_selections = []
    original_prepare = data._prepare_prefill_schema
    original_compile = data._prepared_prefill_schema

    def prepare(asset):
        prepared_calls.append(asset)
        return original_prepare(asset)

    def compile_prepared(prepared, selected):
        compile_selections.append(selected)
        return original_compile(prepared, selected)

    monkeypatch.setattr(data, "_prepare_prefill_schema", prepare)
    monkeypatch.setattr(data, "_prepared_prefill_schema", compile_prepared)
    properties = {f"value_{index}": {"type": "number"} for index in range(20)}
    if has_unsupported:
        properties["unsupported"] = {"type": "string", "format": "unknown-format"}
    asset = version(properties)
    result = protocol_field_catalog(asset, for_target=True)
    assert len(result) == 20
    assert prepared_calls == [asset]
    assert compile_selections[0] is None
    if not has_unsupported:
        assert compile_selections == [None]


@pytest.mark.parametrize(
    "invalid",
    [
        "2026-02-30T10:20:30Z",
        "2026-09-13T10:20:30",
        "2026-09-13T10:20:30+01:60",
        "2026-09-13T10:20:60Z",
    ],
)
def test_prefill_timestamp_format_rejects_invalid_dates_offsets_and_unsupported_leap_seconds(
    invalid,
):
    with pytest.raises(WorkflowContractError):
        validate_protocol_initial_values(
            version({"value": {"type": "string", "format": "date-time"}}),
            {"value": invalid},
        )


@pytest.mark.parametrize(
    "unsupported",
    [
        {"type": "array", "items": {"type": "number"}},
        {"type": "object", "properties": {"x": {"type": "number"}}},
        {"type": ["number", "string"]},
        {"$ref": "https://example.invalid/schema"},
        {"$dynamicRef": "#value"},
        {"type": "string", "airalogy_type": "FileId", "file_extension": "pdf"},
        {"type": "string", "airalogy_type": "FileIdPDF"},
        {"type": "string", "airalogy_type": "ResourceRef"},
        {"type": "string", "airalogy_type": "EntityRef"},
        {"type": "string", "airalogy_type": "DataAsset"},
        {"type": "string", "format": "binary"},
        {"type": "string", "contentMediaType": "application/pdf"},
        {"type": "string", "contentEncoding": "base64"},
        {"type": "string", "format": {}},
        {"type": "string", "unit": "mg"},
    ],
)
def test_unsupported_and_asset_fields_are_not_exposed_as_scalar_bindings(unsupported):
    result = protocol_field_catalog(
        version({"yield": {"type": "number"}, "unsupported": unsupported})
    )
    assert set(result) == {("var", "yield")}


@pytest.mark.parametrize("keyword", ["anyOf", "oneOf", "allOf"])
def test_file_annotation_inside_local_ref_alternative_is_not_lost(keyword):
    # FileId and text share a JSON scalar type. None of the alternatives may
    # grant a file access path merely because the merged analysis type is string.
    schema = {
        "type": "object",
        "properties": {"attachment": {"$ref": "#/$defs/Mixed"}},
        "$defs": {
            "Mixed": {keyword: [{"type": "string"}, {"$ref": "#/$defs/File"}]},
            "File": {
                "type": "string",
                "airalogy_type": "FileId",
                "file_extension": "pdf",
            },
        },
    }
    assert protocol_field_catalog(version(schema=schema)) == {}


@pytest.mark.parametrize(
    "schema", [None, [], {"vars": []}, {"type": "array"}, {"$ref": "#/$defs/Missing"}]
)
def test_missing_unsupported_schema_does_not_block_unbound_protocol_graph(schema):
    result = protocol_field_catalog(SimpleNamespace(version="1", json_schema=schema))
    assert result == {}
    unbound = graph(bindings=[])
    validate_workflow_data(unbound, {"source": result, "target": result})
    assert resolve_workflow_bindings(unbound, "target", {}, {}).initial_values == {}
    with pytest.raises(WorkflowContractError, match="unknown"):
        validate_workflow_data(graph(), {"source": result, "target": result})


@pytest.mark.parametrize(
    "changes",
    [
        {"source_path": ["yield"]},
        {"source_path": ["data", "var", "yield"]},
        {"source_path": ["var", "list", "0"]},
        {"source_path": ["var", 0]},
        {"target_path": ["initial_values", "dose"]},
        {"target_path": ["var", ""]},
        {"source_path": ("var", "yield")},
        {"cardinality": "many"},
        {"value_type": "file"},
        {"source_node_id": "target"},
        {"value_type": "boolean", "unit": "mg"},
        {"expression": "source.value * 2"},
    ],
)
def test_binding_contract_rejects_unsupported_paths_cardinality_and_expressions(
    changes,
):
    with pytest.raises(ValidationError):
        WorkflowBinding.model_validate(binding(**changes))


@pytest.mark.parametrize(
    "case",
    [
        "duplicate_id",
        "duplicate_target",
        "unknown_source",
        "unknown_target",
        "indirect",
        "no_edge",
        "static_collision",
        "analysis",
        "too_many",
    ],
)
def test_graph_checks_binding_structure_separately_from_control_dependencies(case):
    kwargs = {}
    if case == "duplicate_id":
        kwargs["bindings"] = [binding(), binding(target_path=["var", "other"])]
    elif case == "duplicate_target":
        kwargs["bindings"] = [binding(), binding(binding_id="second")]
    elif case in {"unknown_source", "unknown_target"}:
        kwargs["bindings"] = [
            binding(**{case.replace("unknown_", "") + "_node_id": "unknown"})
        ]
    elif case == "indirect":
        kwargs["nodes"] = [node("source"), node("middle"), node("target")]
        kwargs["edges"] = [edge("source", "middle"), edge("middle", "target")]
    elif case == "no_edge":
        kwargs["edges"] = []
    elif case == "static_collision":
        kwargs["nodes"] = [
            node("source"),
            node("target", initial_values={"dose": None}),
        ]
    elif case == "analysis":
        kwargs["nodes"] = [
            {
                "node_id": "source",
                "kind": "analysis",
                "pipeline_revision_id": str(uuid4()),
            },
            node("target"),
        ]
    else:
        kwargs["bindings"] = [
            binding(binding_id=f"b{i}", target_path=["var", f"field{i}"])
            for i in range(MAX_WORKFLOW_BINDINGS + 1)
        ]
    with pytest.raises(ValidationError):
        graph(**kwargs)


@pytest.mark.parametrize(
    "changes",
    [
        {"source_type": "integer"},
        {"target_type": "integer"},
        {"source_unit": "g"},
        {"target_unit": "g"},
        {"source_unit": None},
        {"target_unit": None},
    ],
)
def test_types_and_units_must_match_both_sides_exactly_without_conversion(changes):
    with pytest.raises(WorkflowContractError, match="type|unit"):
        validate_workflow_data(graph(), catalogs(**changes))


def test_resolution_is_flat_merged_immutable_draft_with_full_value_receipts():
    fixed = graph(
        nodes=[
            node("source"),
            node("target", initial_values={"note": "Reviewed context"}),
        ]
    )
    output = {"var": {"yield": 3.5}}
    original = copy.deepcopy(output)
    result = resolve_workflow_bindings(fixed, "target", {"source": output}, catalogs())
    assert result.initial_values == {"dose": 3.5, "note": "Reviewed context"}
    assert result.bindings == [
        {**binding(), "value": 3.5, "value_digest": hashlib.sha256(b"3.5").hexdigest()}
    ]
    assert isinstance(result.bindings[0], dict)
    assert json.loads(json.dumps(result.model_dump())) == result.model_dump()
    assert output == original
    assert fixed.nodes[1].initial_values == {"note": "Reviewed context"}
    result.initial_values["note"] = "Local edit only"
    assert fixed.nodes[1].initial_values["note"] == "Reviewed context"


@pytest.mark.parametrize(
    "value_type,value",
    [
        ("number", 0),
        ("number", -2.5),
        ("integer", 7),
        ("boolean", False),
        ("string", "研究结论"),
        ("string", ""),
    ],
)
def test_actual_values_keep_supported_scalar_types_and_zero_is_not_missing(
    value_type, value
):
    unit = "mg" if value_type == "number" else None
    fixed = graph(bindings=[binding(value_type=value_type, unit=unit)])
    fields = catalogs(
        source_type=value_type,
        target_type=value_type,
        source_unit=unit,
        target_unit=unit,
    )
    result = resolve_workflow_bindings(
        fixed, "target", {"source": {"var": {"yield": value}}}, fields
    )
    assert type(result.initial_values["dose"]) is type(value)
    assert result.initial_values["dose"] == value


@pytest.mark.parametrize(
    "output",
    [
        {},
        {"var": {}},
        {"var": {"yield": None}},
        {"var": {"yield": True}},
        {"var": {"yield": "3.5"}},
        {"var": {"yield": []}},
        {"var": {"yield": float("nan")}},
        {"var": {"yield": float("inf")}},
        {"record": {"data": {"var": {"yield": 3.5}}}},
    ],
)
def test_missing_null_wrong_shapes_and_type_coercion_fail_closed(output):
    with pytest.raises(WorkflowContractError):
        resolve_workflow_bindings(
            graph(), "target", {"source": output}, catalogs(nullable=True)
        )


def test_missing_authorized_source_does_not_guess_another_record_or_latest_value():
    with pytest.raises(WorkflowContractError, match="authorized completed source"):
        resolve_workflow_bindings(
            graph(), "target", {"unrelated": {"var": {"yield": 100}}}, catalogs()
        )


@pytest.mark.parametrize(
    "value",
    [
        2**53,
        -(2**53),
        float(2**53),
        "airalogy.id.file.11111111-1111-1111-1111-111111111111.pdf",
        " airalogy.id.file.11111111-1111-1111-1111-111111111111.pdf ",
        "x" * (128 * 1024),
    ],
)
def test_unsafe_numeric_precision_file_ids_and_excessive_values_are_rejected(value):
    value_type = "string" if isinstance(value, str) else "number"
    unit = None if value_type == "string" else "mg"
    fixed = graph(bindings=[binding(value_type=value_type, unit=unit)])
    fields = catalogs(
        source_type=value_type,
        target_type=value_type,
        source_unit=unit,
        target_unit=unit,
    )
    with pytest.raises(WorkflowContractError):
        resolve_workflow_bindings(
            fixed, "target", {"source": {"var": {"yield": value}}}, fields
        )


def test_condition_catalog_is_shared_and_false_binding_edge_never_borrows_its_value():
    predicate = {
        "path": ["var", "yield"],
        "value_type": "number",
        "unit": "mg",
        "operator": "gt",
        "value": 5,
    }
    fixed = graph(edges=[edge(condition=predicate)])
    validate_workflow_data(fixed, catalogs())
    with pytest.raises(WorkflowContractError, match="not selected"):
        resolve_workflow_bindings(
            fixed, "target", {"source": {"var": {"yield": 3}}}, catalogs()
        )
    assert resolve_workflow_bindings(
        fixed, "target", {"source": {"var": {"yield": 6}}}, catalogs()
    ).initial_values == {"dose": 6}


def test_binding_array_reorder_does_not_change_execution_identity():
    fixed = graph(
        bindings=[
            binding(),
            binding(binding_id="another", target_path=["var", "second_dose"]),
        ]
    )
    reordered = fixed.model_dump(mode="json")
    reordered["bindings"].reverse()
    assert workflow_execution_digest(fixed) == workflow_execution_digest(
        validate_workflow_graph(reordered)
    )


def test_literal_source_and_target_field_names_are_never_split_into_nested_paths():
    source_key, target_key = "yield.with/slash~", "dose.with/slash~"
    fixed = graph(
        bindings=[
            binding(source_path=["var", source_key], target_path=["var", target_key])
        ]
    )
    fields = {
        "source": protocol_field_catalog(
            version({source_key: {"type": "number", "unit": "mg"}})
        ),
        "target": protocol_field_catalog(
            version({target_key: {"type": "number", "unit": "mg"}})
        ),
    }
    result = resolve_workflow_bindings(
        fixed, "target", {"source": {"var": {source_key: 3}}}, fields
    )
    assert result.initial_values == {target_key: 3}


def test_mutated_nested_binding_is_revalidated_before_resolution():
    fixed = graph()
    fixed.bindings[0].source_path[0] = "other"
    with pytest.raises(ValidationError):
        resolve_workflow_bindings(
            fixed, "target", {"source": {"var": {"yield": 3}}}, catalogs()
        )
