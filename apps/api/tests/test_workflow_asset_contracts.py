"""Pure v5 DataAsset slots: real JSON values, no storage/AI/permission shortcuts."""

import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.services.workflow_asset_contracts import (
    MAX_ASSET_JSON_BYTES,
    asset_field_catalog,
    asset_file_catalog,
    parse_asset_json,
    resolve_asset_value,
    validate_workflow_asset_targets,
)
from app.services.workflow_contracts import (
    WorkflowAssetBinding,
    WorkflowAssetInput,
    WorkflowContractError,
    WorkflowFieldSpec,
    topological_node_ids,
    validate_workflow_graph,
    workflow_execution_digest,
    workflow_revision_digest,
)
from tests.test_workflow_analysis_contracts import graph as v2_graph
from tests.test_workflow_compute_contracts import compute_graph as v3_graph
from tests.test_workflow_contracts import graph as v1_graph
from tests.test_workflow_contracts import protocol
from tests.test_workflow_file_contracts import graph as v4_graph

FILE_ID = "airalogy.id.file.00000000-0000-4000-8000-000000000001.json"


def binding(**changes):
    return {
        "binding_id": "dose",
        "input_id": "calibration",
        "source_path": ["json", "metrics", "dose"],
        "target_node_id": "measure",
        "target_path": ["var", "dose"],
        "value_type": "number",
        "unit": "mg",
        **changes,
    }


def graph(**changes):
    return {
        "schema_version": 5,
        "nodes": [protocol()],
        "edges": [],
        "bindings": [],
        "asset_inputs": [{"input_id": "calibration", "label": "Calibration"}],
        "asset_bindings": [binding()],
        **changes,
    }


def schema(value_type="number", **constraints):
    return {
        "type": "object",
        "properties": {
            "metrics": {
                "type": "object",
                "properties": {"dose": {"type": value_type, **constraints}},
                "required": ["dose"],
                "additionalProperties": False,
            }
        },
        "required": ["metrics"],
        "additionalProperties": False,
    }


def content(value):
    return json.dumps({"metrics": {"dose": value}}).encode()


def resolve(value, *, asset_schema=None, declaration=None):
    asset_schema = schema(unit="mg") if asset_schema is None else asset_schema
    return resolve_asset_value(
        binding() if declaration is None else declaration,
        parse_asset_json(content(value), asset_schema),
        asset_field_catalog(asset_schema),
    )


def test_resource_bound_single_root_requires_no_fake_action_or_control_edge():
    value = validate_workflow_graph(graph())
    assert topological_node_ids(value) == ["measure"]
    assert value.edges == value.bindings == []
    assert value.asset_inputs[0].model_dump() == {
        "input_id": "calibration",
        "label": "Calibration",
    }
    assert value.asset_bindings[0].cardinality == "one"
    validate_workflow_asset_targets(
        value,
        {
            "measure": {
                ("var", "dose"): WorkflowFieldSpec(value_type="number", unit="mg")
            }
        },
    )
    assert resolve(2.5) == 2.5


def test_v5_with_no_resources_and_repeated_protocol_roots_remains_valid():
    empty = validate_workflow_graph(graph(asset_inputs=[], asset_bindings=[]))
    assert empty.model_dump(mode="json")["asset_inputs"] == []
    assert empty.model_dump(mode="json")["asset_bindings"] == []
    value = validate_workflow_graph(
        graph(
            nodes=[protocol(), protocol("replicate")],
            asset_bindings=[
                binding(),
                binding(binding_id="replicate_dose", target_node_id="replicate"),
            ],
        )
    )
    assert topological_node_ids(value) == ["measure", "replicate"]
    assert value.nodes[0].protocol_id == value.nodes[1].protocol_id


@pytest.mark.parametrize("version", [1, 2, 3, 4])
@pytest.mark.parametrize(
    "added", [{"asset_inputs": []}, {"asset_bindings": []}, {"asset_inputs": None}]
)
def test_older_versions_reject_even_explicit_empty_asset_fields(version, added):
    with pytest.raises(ValidationError):
        validate_workflow_graph(v1_graph(schema_version=version, **added))


@pytest.mark.parametrize(
    ("factory", "revision_digest", "execution_digest"),
    [
        (
            v1_graph,
            "0d76ca7fdeb42042e8c925efce9b083208b397a174d4c7343696138041833ea0",
            "8566ef6dac479e7fbd45a29aa8dd333bba3db37441e90b9b213cd53b08f67523",
        ),
        (
            v2_graph,
            "fe344334f893b69e5f2469067b42642d787d1dfc08008dea9be201a5972e70a9",
            "fa4cdee124614ab644df901c744d5e717ecc276d65bf603c756a9a4b0ae56fa0",
        ),
        (
            v3_graph,
            "2a6cdbfb27ad286a95e7e3493331ec81eed36b39870337b5a6feb60a128fb335",
            "18fc06543d7e83002b30bce9fdba575b7fe723f6892e6326abd6d1f4527f31df",
        ),
        (
            v4_graph,
            "8f06a1c3e296f443876480b9368e132aef95a4d7c9b4cfbb5807df6b1d9ba3a8",
            "1cf2c251e2c3a9bef5448b83c15081ffe0f23891f420202f1018b398f281ce1a",
        ),
    ],
)
def test_v1_through_v4_golden_json_and_digests_remain_identical(
    factory, revision_digest, execution_digest
):
    value = validate_workflow_graph(factory())
    for serialized in (
        value.model_dump(),
        value.model_dump(mode="json"),
        json.loads(value.model_dump_json()),
    ):
        assert "asset_inputs" not in serialized
        assert "asset_bindings" not in serialized
    assert workflow_revision_digest(value) == revision_digest
    assert workflow_execution_digest(value) == execution_digest
    restored = validate_workflow_graph(json.loads(value.model_dump_json()))
    assert workflow_revision_digest(restored) == revision_digest
    assert workflow_execution_digest(restored) == execution_digest


def test_legacy_model_container_mutation_cannot_hide_new_resources_on_revalidation():
    value = validate_workflow_graph(v1_graph())
    value.asset_inputs.append(WorkflowAssetInput(input_id="hidden", label="Hidden"))
    with pytest.raises(ValidationError):
        validate_workflow_graph(value)


def test_resource_display_changes_do_not_change_execution_identity():
    first = graph(
        asset_inputs=[
            {"input_id": "calibration", "label": "Calibration"},
            {"input_id": "reference", "label": "Reference"},
        ],
        asset_bindings=[
            binding(),
            binding(
                binding_id="reference_dose",
                input_id="reference",
                target_path=["var", "reference_dose"],
            ),
        ],
    )
    second = deepcopy(first)
    second["asset_inputs"].reverse()
    second["asset_bindings"].reverse()
    second["asset_inputs"][0]["label"] = "Renamed display label"
    second["nodes"][0]["position"] = {"x": 40, "y": 150}
    assert workflow_revision_digest(
        validate_workflow_graph(first)
    ) != workflow_revision_digest(validate_workflow_graph(second))
    assert workflow_execution_digest(
        validate_workflow_graph(first)
    ) == workflow_execution_digest(validate_workflow_graph(second))
    second["asset_bindings"][0]["source_path"] = ["json", "metrics", "other"]
    assert workflow_execution_digest(
        validate_workflow_graph(first)
    ) != workflow_execution_digest(validate_workflow_graph(second))


@pytest.mark.parametrize(
    "changes",
    [
        {"asset_inputs": []},
        {"asset_bindings": []},
        {"asset_inputs": [{"input_id": "other", "label": "Other"}]},
        {"asset_inputs": [{"input_id": "calibration", "label": "Calibration"}] * 2},
        {"asset_inputs": [{"input_id": "calibration", "label": " "}]},
        {"asset_inputs": [{"input_id": "calibration", "label": 1}]},
        {
            "asset_inputs": [
                {
                    "input_id": "calibration",
                    "label": "Calibration",
                    "data_asset_version_id": "private-id",
                }
            ]
        },
        {"asset_inputs": ({"input_id": "calibration", "label": "Calibration"},)},
        {"asset_bindings": (binding(),)},
        {"asset_bindings": [binding(), binding()]},
        {"asset_bindings": [binding(target_node_id="unknown")]},
        {"nodes": [protocol(initial_values={"dose": None})]},
        {"nodes": [protocol(initial_values={"dose": 1})]},
    ],
)
def test_asset_slots_and_targets_reject_unknown_unused_duplicate_or_private_inputs(
    changes,
):
    with pytest.raises(ValidationError):
        validate_workflow_graph(graph(**changes))


@pytest.mark.parametrize(
    "identifier", ["", "1input", "Input", "input.name", "a" * 65, 1, None]
)
def test_asset_identifiers_are_stable_bounded_and_not_coerced(identifier):
    with pytest.raises(ValidationError):
        validate_workflow_graph(
            graph(asset_inputs=[{"input_id": identifier, "label": "Input"}])
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"source_path": []},
        {"source_path": ["json"]},
        {"source_path": "json.metrics.dose"},
        {"source_path": ("json", "dose")},
        {"source_path": ["var", "dose"]},
        {"source_path": ["json", 0]},
        {"source_path": ["json", ""]},
        {"source_path": ["json", " "]},
        {"source_path": ["json", "a" * 256]},
        {"source_path": ["json"] + ["key"] * 17},
        {"source_path": ["file", "other"], "value_type": "file", "unit": None},
        {"source_path": ["file"]},
        {"value_type": "file", "unit": None},
        {"target_path": ["analysis", "dose"]},
        {"target_path": ["var", "dose", "nested"]},
        {"target_path": ["var", ""]},
        {"target_path": ("var", "dose")},
        {"unit": " mg"},
        {"unit": " "},
        {"value_type": "boolean"},
        {"value_type": "object", "unit": None},
        {"cardinality": "many"},
        {"source_action_id": "not-a-resource"},
    ],
)
def test_asset_binding_paths_and_scalar_contracts_are_explicit(changes):
    with pytest.raises(ValidationError):
        WorkflowAssetBinding.model_validate(binding(**changes))


@pytest.mark.parametrize("collision", ["binding_id", "target_path"])
def test_binding_identity_and_target_conflicts_are_global_across_source_kinds(
    collision,
):
    ordinary = {
        "binding_id": "parent_dose",
        "source_node_id": "parent",
        "source_path": ["var", "dose"],
        "target_node_id": "measure",
        "target_path": ["var", "parent_dose"],
        "value_type": "number",
        "unit": "mg",
    }
    ordinary[collision] = binding()[collision]
    with pytest.raises(ValidationError):
        validate_workflow_graph(
            graph(
                nodes=[protocol("parent"), protocol()],
                edges=[
                    {
                        "edge_id": "next",
                        "source_node_id": "parent",
                        "target_node_id": "measure",
                    }
                ],
                bindings=[ordinary],
            )
        )


def test_analysis_nodes_cannot_be_asset_binding_targets():
    value = v2_graph()
    value.update(
        schema_version=5,
        asset_inputs=graph()["asset_inputs"],
        asset_bindings=[
            binding(
                binding_id="asset_dose", target_node_id=value["nodes"][1]["node_id"]
            )
        ],
    )
    with pytest.raises(ValidationError, match="Protocol target"):
        validate_workflow_graph(value)


def test_asset_slot_and_total_binding_limits_are_enforced_without_truncation():
    slots = [
        {"input_id": f"input_{index}", "label": f"Input {index}"} for index in range(32)
    ]
    bindings = [
        binding(
            binding_id=f"binding_{index}",
            input_id=slot["input_id"],
            target_path=["var", f"value_{index}"],
        )
        for index, slot in enumerate(slots)
    ]
    assert (
        len(
            validate_workflow_graph(
                graph(asset_inputs=slots, asset_bindings=bindings)
            ).asset_inputs
        )
        == 32
    )
    with pytest.raises(ValidationError):
        validate_workflow_graph(
            graph(
                asset_inputs=[*slots, {"input_id": "overflow", "label": "Overflow"}],
                asset_bindings=bindings,
            )
        )
    many = [
        binding(binding_id=f"binding_{index}", target_path=["var", f"value_{index}"])
        for index in range(128)
    ]
    assert (
        len(validate_workflow_graph(graph(asset_bindings=many)).asset_bindings) == 128
    )
    with pytest.raises(ValidationError, match="combined limit"):
        validate_workflow_graph(
            graph(
                nodes=[protocol("parent"), protocol()],
                edges=[
                    {
                        "edge_id": "next",
                        "source_node_id": "parent",
                        "target_node_id": "measure",
                    }
                ],
                asset_bindings=many,
                bindings=[
                    {
                        "binding_id": "ordinary",
                        "source_node_id": "parent",
                        "source_path": ["var", "dose"],
                        "target_node_id": "measure",
                        "target_path": ["var", "other"],
                        "value_type": "number",
                    }
                ],
            )
        )


@pytest.mark.parametrize(
    "catalog",
    [
        {},
        {"measure": {}},
        {"measure": {("var", "dose"): {"value_type": "number", "unit": "mg"}}},
        {
            "measure": {
                ("var", "dose"): WorkflowFieldSpec(value_type="integer", unit="mg")
            }
        },
        {
            "measure": {
                ("var", "dose"): WorkflowFieldSpec(value_type="number", unit="g")
            }
        },
        {"measure": {("var", "dose"): WorkflowFieldSpec(value_type="number")}},
        None,
    ],
)
def test_targets_require_a_trusted_exact_type_and_unit_catalog(catalog):
    with pytest.raises(WorkflowContractError):
        validate_workflow_asset_targets(validate_workflow_graph(graph()), catalog)


def test_whole_file_port_has_a_separate_catalog_and_never_resolves_a_json_fileid():
    declared = binding(source_path=["file"], value_type="file", unit=None)
    catalog = asset_file_catalog("json")
    assert catalog == {
        ("file",): WorkflowFieldSpec(value_type="file", file_extensions=["json"])
    }
    value = validate_workflow_graph(graph(asset_bindings=[declared]))
    validate_workflow_asset_targets(
        value, {"measure": {("var", "dose"): catalog[("file",)]}}
    )
    for payload in (FILE_ID, {"file": FILE_ID}, {"storage_object_key": "private/path"}):
        with pytest.raises(WorkflowContractError, match="runtime file receipt"):
            resolve_asset_value(declared, payload, catalog)


@pytest.mark.parametrize(
    "extension", [None, "", "JSON", ".json", "a/b", "x" * 33, {"filename": "file.json"}]
)
def test_file_catalog_does_not_infer_or_normalize_unverified_metadata(extension):
    with pytest.raises(WorkflowContractError):
        asset_file_catalog(extension)


@pytest.mark.parametrize(
    ("value", "value_type"),
    [
        (3, "number"),
        (2.5, "number"),
        (3, "integer"),
        (True, "boolean"),
        ("confirmed", "string"),
    ],
)
def test_actual_json_scalars_keep_their_exact_python_types(value, value_type):
    asset_schema = schema(value_type)
    result = resolve(
        value,
        asset_schema=asset_schema,
        declaration=binding(value_type=value_type, unit=None),
    )
    assert result == value and type(result) is type(value)


@pytest.mark.parametrize(
    "value",
    [
        True,
        "3",
        None,
        [],
        {},
        float("nan"),
        float("inf"),
        2**53,
        -(2**53),
        float(2**53),
    ],
)
def test_invalid_numeric_values_never_become_scientific_inputs(value):
    with pytest.raises(WorkflowContractError):
        resolve(value)


def test_nullable_and_missing_sources_fail_closed_without_defaults_or_repairs():
    asset_schema = schema(["number", "null"], unit="mg", default=12)
    catalog = asset_field_catalog(asset_schema)
    assert catalog[("json", "metrics", "dose")].nullable is True
    assert parse_asset_json(content(None), asset_schema)["metrics"]["dose"] is None
    with pytest.raises(WorkflowContractError, match="null"):
        resolve(None, asset_schema=asset_schema)
    asset_schema["properties"]["metrics"].pop("required")
    value = parse_asset_json(b'{"metrics":{}}', asset_schema)
    assert value == {"metrics": {}}
    with pytest.raises(WorkflowContractError, match="missing"):
        resolve_asset_value(binding(), value, asset_field_catalog(asset_schema))


def test_float_is_not_coerced_to_an_integer_despite_jsonschema_integral_numeric_semantics():
    asset_schema = schema("integer")
    value = parse_asset_json(content(3.0), asset_schema)
    with pytest.raises(WorkflowContractError, match="scalar type"):
        resolve_asset_value(
            binding(value_type="integer", unit=None),
            value,
            asset_field_catalog(asset_schema),
        )


@pytest.mark.parametrize("prefix", ["", " \n"])
def test_plain_strings_cannot_smuggle_file_references(prefix):
    with pytest.raises(WorkflowContractError, match="whole-file"):
        resolve(
            prefix + FILE_ID,
            asset_schema=schema("string"),
            declaration=binding(value_type="string", unit=None),
        )


def test_local_refs_preserve_sibling_allof_enum_range_and_additional_properties_constraints():
    value = schema(unit="mg")
    value["$defs"] = {
        "dose": {
            "type": "number",
            "unit": "mg",
            "minimum": 2,
            "maximum": 10,
            "enum": [2, 4, 8],
        }
    }
    value["properties"]["metrics"]["properties"]["dose"] = {
        "$ref": "#/$defs/dose",
        "exclusiveMinimum": 2,
        "allOf": [{"maximum": 6}],
    }
    original = deepcopy(value)
    assert resolve(4, asset_schema=value) == 4
    for invalid in (1, 2, 3, 8, 12):
        with pytest.raises(WorkflowContractError, match="complete fixed Schema"):
            parse_asset_json(content(invalid), value)
    with pytest.raises(WorkflowContractError):
        parse_asset_json(b'{"metrics":{"dose":4,"other":5}}', value)
    assert value == original


def test_local_pointer_escaped_and_literal_path_keys_are_not_dotted_or_index_expressions():
    value = {
        "type": "object",
        "properties": {
            "a.b": {
                "type": "object",
                "properties": {"0": {"$ref": "#/$defs/a~1b~0c"}},
                "required": ["0"],
            }
        },
        "$defs": {"a/b~c": {"type": "number"}},
    }
    parsed = parse_asset_json(b'{"a.b":{"0":5}}', value)
    catalog = asset_field_catalog(value)
    assert (
        resolve_asset_value(
            binding(source_path=["json", "a.b", "0"], unit=None), parsed, catalog
        )
        == 5
    )
    with pytest.raises(WorkflowContractError, match="unknown"):
        resolve_asset_value(
            binding(source_path=["json", "a", "b", "0"], unit=None), parsed, catalog
        )
    with pytest.raises(WorkflowContractError, match="missing"):
        resolve_asset_value(
            binding(source_path=["json", "a.b", "0"], unit=None), {"a.b": [5]}, catalog
        )


def test_schema_catalog_does_not_offer_arrays_untyped_unions_or_fileid_annotations_as_scalars():
    value = {
        "type": "object",
        "properties": {
            "good": {"type": ["number", "null"], "unit": "mg"},
            "array": {"type": "array", "items": {"type": "number"}},
            "guess": {},
            "mixed": {"anyOf": [{"type": "number"}, {"type": "string"}]},
            "file": {
                "type": "string",
                "airalogy_type": "FileId",
                "file_extension": "json",
            },
        },
    }
    assert asset_field_catalog(value) == {
        ("json", "good"): WorkflowFieldSpec(
            value_type="number", unit="mg", nullable=True
        )
    }
    assert ("file",) not in asset_field_catalog(value)


@pytest.mark.parametrize(
    "invalid_schema",
    [
        {},
        [],
        True,
        {"type": "array", "items": {"type": "number"}},
        {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object"},
        {"type": "object", "$id": "https://example.invalid/source"},
        {"type": "object", "$dynamicRef": "#node"},
        {
            "type": "object",
            "properties": {"value": {"$ref": "https://example.invalid/schema"}},
        },
        {"type": "object", "$defs": {"unused": {"$ref": "file:///private/data.json"}}},
        {"type": "object", "properties": {"value": {"$ref": "#/missing"}}},
        {
            "type": "object",
            "properties": {"value": {"$ref": "#/$defs/recursive"}},
            "$defs": {"recursive": {"$ref": "#/$defs/recursive"}},
        },
        {"type": "object", "unknownValidation": True},
        {
            "type": "object",
            "properties": {"value": {"type": "string", "format": "unknown-format"}},
        },
        {
            "type": "object",
            "properties": {
                "value": {"type": "number", "$defs": {"x": {}}, "$id": "new-scope"}
            },
        },
        {"type": "object", "minProperties": "1"},
    ],
)
def test_unsupported_or_nonlocal_schemas_fail_instead_of_claiming_validation(
    invalid_schema,
):
    with pytest.raises(WorkflowContractError):
        asset_field_catalog(invalid_schema)
    with pytest.raises(WorkflowContractError):
        parse_asset_json(b"{}", invalid_schema)


def test_complete_schema_checks_unbound_fields_and_formats_without_leaking_values():
    value = schema(unit="mg")
    value["properties"]["recorded_at"] = {"type": "string", "format": "date-time"}
    value["required"].append("recorded_at")
    valid = {"metrics": {"dose": 4}, "recorded_at": "2026-09-14T03:00:00Z"}
    assert parse_asset_json(json.dumps(valid).encode(), value) == valid
    valid["recorded_at"] = "private-invalid-date-value"
    with pytest.raises(WorkflowContractError) as error:
        parse_asset_json(json.dumps(valid).encode(), value)
    assert "private-invalid-date-value" not in str(error.value)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        "{}",
        bytearray(b"{}"),
        b"null",
        b"[]",
        b"12",
        b"{} {}",
        b"{",
        b"\xff",
        b"\xef\xbb\xbf{}",
        b'{"a":1,"a":2}',
        b'{"a":{"x":1,"x":2}}',
        b'{"a":1,"\\u0061":2}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b'{"value":1e999}',
        b'{"value":"\\ud800"}',
        b'{"value":9007199254740992}',
        b'{"value":9007199254740992.0}',
    ],
)
def test_actual_json_is_strict_bounded_and_never_silently_normalized(raw):
    with pytest.raises(WorkflowContractError):
        parse_asset_json(raw, {"type": "object"})


def test_json_size_depth_and_item_limits_fail_instead_of_truncating():
    for raw in (
        b" " * (MAX_ASSET_JSON_BYTES + 1),
        b'{"x":' * 30 + b"0" + b"}" * 30,
        json.dumps({"x": list(range(20_001))}).encode(),
    ):
        with pytest.raises(WorkflowContractError):
            parse_asset_json(raw, {"type": "object"})


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), 2**53, float(2**53), True, None, "4", [], {}]
)
def test_resolver_revalidates_caller_supplied_values_even_after_a_prior_parse(value):
    with pytest.raises(WorkflowContractError):
        resolve_asset_value(
            binding(),
            {"metrics": {"dose": value}},
            asset_field_catalog(schema(unit="mg")),
        )


def test_resolver_revalidates_mutated_binding_paths_and_exact_catalog_contract():
    declared = WorkflowAssetBinding.model_validate(binding())
    declared.source_path[0] = "unsafe"
    with pytest.raises(WorkflowContractError, match="Invalid"):
        resolve_asset_value(
            declared, {"metrics": {"dose": 4}}, asset_field_catalog(schema(unit="mg"))
        )
    for wrong in (
        {},
        asset_field_catalog(schema(unit="g")),
        asset_field_catalog(schema("integer", unit="mg")),
    ):
        with pytest.raises(WorkflowContractError):
            resolve_asset_value(binding(), {"metrics": {"dose": 4}}, wrong)
