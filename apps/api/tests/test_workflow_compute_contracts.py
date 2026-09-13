"""Pure v3 compatibility, declared Schema and computed-result scalar contracts."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services.workflow_compute_contracts import (
    compute_output_catalog,
    compute_result_fields,
    project_compute_outputs,
    validate_compute_method_inputs,
    validate_compute_result_schema,
)
from app.services.workflow_contracts import (
    WorkflowContractError,
    evaluate_workflow_condition,
    validate_workflow_graph,
    workflow_execution_digest,
    workflow_revision_digest,
)
from tests.test_workflow_analysis_contracts import graph as builtin_graph


def schema(value_type="number", **constraints):
    return {
        "type": "object",
        "properties": {
            "metrics": {
                "type": "object",
                "properties": {"mean": {"type": value_type, **constraints}},
                "required": ["mean"],
                "additionalProperties": False,
            }
        },
        "required": ["metrics"],
        "additionalProperties": False,
    }


def port(**changes):
    return {
        "output_id": "mean_dose",
        "path": ["metrics", "mean"],
        "value_type": "number",
        "unit": "mg",
        "nullable": False,
        **changes,
    }


def project(value, *, result_schema=None, outputs=None):
    result_schema = schema(unit="mg") if result_schema is None else result_schema
    outputs = [port()] if outputs is None else outputs
    return project_compute_outputs(
        result_schema,
        {"computed_result": {"metrics": {"mean": value}}},
        outputs,
        compute_output_catalog(result_schema, outputs),
    )


def compute_graph(**node_changes):
    graph = builtin_graph()
    graph["schema_version"] = 3
    graph["nodes"][1].update(
        analysis_kind="compute",
        analysis_outputs=[],
        compute_outputs=[port()],
    )
    graph["nodes"][1].update(node_changes)
    return graph


def test_v2_saved_json_and_both_golden_digests_remain_unchanged():
    value = validate_workflow_graph(builtin_graph())
    assert (
        workflow_revision_digest(value)
        == "fe344334f893b69e5f2469067b42642d787d1dfc08008dea9be201a5972e70a9"
    )
    assert (
        workflow_execution_digest(value)
        == "fa4cdee124614ab644df901c744d5e717ecc276d65bf603c756a9a4b0ae56fa0"
    )
    assert all(
        "analysis_kind" not in item and "compute_outputs" not in item
        for item in value.model_dump(mode="json")["nodes"]
    )


def test_v3_compute_ports_use_existing_binding_namespace_and_pin_digest():
    value = validate_workflow_graph(compute_graph())
    restored = validate_workflow_graph(value.model_dump(mode="json"))
    assert workflow_execution_digest(value) == workflow_execution_digest(restored)
    changed = compute_graph(compute_outputs=[port(path=["different", "mean"])])
    assert workflow_execution_digest(value) != workflow_execution_digest(
        validate_workflow_graph(changed)
    )


def test_v3_can_mix_builtin_and_compute_without_rewriting_builtin_nodes():
    value = compute_graph()
    builtin = deepcopy(builtin_graph()["nodes"][1])
    builtin["node_id"] = "builtin"
    value["nodes"].append(builtin)
    value["edges"].append(
        {
            "edge_id": "measure-to-builtin",
            "source_node_id": "measure",
            "target_node_id": "builtin",
        }
    )
    result = validate_workflow_graph(value).model_dump(mode="json")
    assert "analysis_kind" not in result["nodes"][-1]
    assert "compute_outputs" not in result["nodes"][-1]
    assert result["nodes"][-1]["analysis_outputs"] == builtin["analysis_outputs"]


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize(
    "fields",
    [{"analysis_kind": "compute"}, {"compute_outputs": []}, {"analysis_kind": None}],
)
def test_old_graph_versions_do_not_accept_new_compute_fields(version, fields):
    value = builtin_graph()
    value["schema_version"] = version
    value["nodes"][1].update(fields)
    with pytest.raises(ValidationError):
        validate_workflow_graph(value)


@pytest.mark.parametrize(
    "change",
    [
        {"analysis_kind": None},
        {
            "analysis_outputs": [
                {"output_id": "extra", "field": "dose", "statistic": "mean"}
            ]
        },
        {"compute_outputs": [port(), port()]},
        {"compute_outputs": [port(nullable=1)]},
        {"compute_outputs": [port(path="metrics.mean")]},
        {"compute_outputs": [port(path=["metrics", 0])]},
        {"compute_outputs": [port(path=[])]},
        {"compute_outputs": [port(value_type="string")]},
    ],
)
def test_compute_node_contract_rejects_ambiguous_or_invalid_ports(change):
    with pytest.raises(ValidationError):
        validate_workflow_graph(compute_graph(**change))


def test_explicit_report_only_compute_has_no_bindable_outputs():
    value = compute_graph(compute_outputs=[])
    with pytest.raises(ValidationError, match="undeclared"):
        validate_workflow_graph(value)
    value["bindings"] = []
    assert validate_workflow_graph(value).nodes[1].analysis_kind == "compute"
    assert project_compute_outputs(
        {"type": "object"}, {"computed_result": {}}, [], {}
    ) == {"analysis": {}}


def test_scalar_catalog_and_projection_are_derived_from_schema_not_result_order():
    value = schema(unit="mg")
    assert compute_result_fields(value) == [
        {
            "path": ["metrics", "mean"],
            "value_type": "number",
            "unit": "mg",
            "nullable": False,
            "title": "mean",
        }
    ]
    assert project(3.5) == {"analysis": {"mean_dose": 3.5}}
    copied = validate_compute_result_schema(value)
    copied["properties"].clear()
    assert value["properties"]


@pytest.mark.parametrize(
    "change",
    [
        {"value_type": "integer"},
        {"unit": "g"},
        {"nullable": True},
        {"path": ["mean"]},
        {"path": ["metrics", "0"]},
        {"path": ["metrics", "*"]},
    ],
)
def test_output_contract_cannot_override_or_guess_schema(change):
    with pytest.raises(WorkflowContractError):
        compute_output_catalog(schema(unit="mg"), [port(**change)])


@pytest.mark.parametrize(
    "value", [True, "3", None, float("nan"), float("inf"), 2**53, -(2**53)]
)
def test_invalid_numeric_results_never_become_scalar_values(value):
    with pytest.raises(WorkflowContractError):
        project(value)


def test_nullable_value_is_evidence_but_not_a_successful_condition():
    result_schema = schema(["number", "null"], unit="mg")
    outputs = [port(nullable=True)]
    result = project(None, result_schema=result_schema, outputs=outputs)
    assert result == {"analysis": {"mean_dose": None}}
    from app.services.workflow_contracts import WorkflowCondition

    with pytest.raises(WorkflowContractError):
        evaluate_workflow_condition(
            WorkflowCondition(
                path=["analysis", "mean_dose"],
                operator="eq",
                value_type="number",
                unit="mg",
                value=0,
            ),
            result,
            compute_output_catalog(result_schema, outputs),
        )


def test_optional_missing_is_not_null_or_defaulted():
    result_schema = schema(["number", "null"], unit="mg", default=0)
    result_schema["properties"]["metrics"].pop("required")
    with pytest.raises(WorkflowContractError, match="missing"):
        project_compute_outputs(
            result_schema,
            {"computed_result": {"metrics": {}}},
            [port(nullable=True)],
            compute_output_catalog(result_schema, [port(nullable=True)]),
        )


def test_local_refs_and_allof_keep_all_range_and_enum_constraints():
    value = schema(unit="mg")
    value["$defs"] = {
        "reading": {"type": "number", "unit": "mg", "minimum": 2, "enum": [2, 4, 8]}
    }
    value["properties"]["metrics"]["properties"]["mean"] = {
        "$ref": "#/$defs/reading",
        "allOf": [{"maximum": 5}],
        "minimum": 3,
    }
    assert project(4, result_schema=value) == {"analysis": {"mean_dose": 4}}
    for invalid in (2, 3, 8):
        with pytest.raises(WorkflowContractError, match="Schema"):
            project(invalid, result_schema=value)


def test_object_allof_and_sibling_conditionals_preserve_constraints():
    value = {
        "allOf": [
            schema(unit="mg"),
            {"properties": {"metrics": {"properties": {"mean": {"maximum": 5}}}}},
        ]
    }
    assert project(4, result_schema=value)
    with pytest.raises(WorkflowContractError):
        project(6, result_schema=value)
    value = schema(unit="mg")
    value["anyOf"] = [
        {"properties": {"metrics": {"properties": {"mean": {"const": 1}}}}},
        {"properties": {"metrics": {"properties": {"mean": {"const": 2}}}}},
    ]
    assert project(2, result_schema=value)
    with pytest.raises(WorkflowContractError):
        project(3, result_schema=value)


def test_literal_keys_and_var_are_not_protocol_wrappers_or_jsonpath():
    value = {
        "type": "object",
        "properties": {
            "var": {"type": "object", "properties": {"a.b/c~1": {"type": "integer"}}}
        },
    }
    output = port(path=["var", "a.b/c~1"], value_type="integer", unit=None)
    assert compute_result_fields(value)[0]["path"] == ["var", "a.b/c~1"]
    assert project_compute_outputs(
        value,
        {"computed_result": {"var": {"a.b/c~1": 5}}},
        [output],
        compute_output_catalog(value, [output]),
    ) == {"analysis": {"mean_dose": 5}}


@pytest.mark.parametrize(
    "ref",
    [
        "https://example.test/schema",
        "file:///tmp/schema",
        "relative.json",
        "#/$defs/missing",
        "#/bad~9",
    ],
)
def test_nonlocal_or_invalid_references_are_rejected_even_in_unused_defs(ref):
    value = schema(unit="mg")
    value["$defs"] = {"unused": {"$ref": ref}}
    with pytest.raises(WorkflowContractError):
        validate_compute_result_schema(value)


@pytest.mark.parametrize(
    "keyword",
    [
        "$id",
        "$anchor",
        "$dynamicAnchor",
        "$recursiveAnchor",
        "$dynamicRef",
        "$recursiveRef",
        "$vocabulary",
    ],
)
def test_alternate_reference_scopes_are_rejected(keyword):
    value = schema(unit="mg")
    value[keyword] = "x"
    with pytest.raises(WorkflowContractError):
        validate_compute_result_schema(value)


def test_arrays_files_and_ambiguous_scalar_union_are_not_exported():
    value = {
        "type": "object",
        "properties": {
            "array": {"type": "array", "items": {"type": "number"}},
            "file": {"type": "string", "airalogy_type": "FileId"},
            "mixed": {"anyOf": [{"type": "number"}, {"type": "string"}]},
        },
    }
    assert compute_result_fields(value) == []
    with pytest.raises(WorkflowContractError):
        compute_output_catalog(value, [port(path=["array", "0"], unit=None)])


def test_projection_validates_entire_schema_even_without_ports_and_checks_format():
    value = {
        "type": "object",
        "properties": {"date": {"type": "string", "format": "date-time"}},
        "required": ["date"],
    }
    assert project_compute_outputs(
        value, {"computed_result": {"date": "2026-09-13T00:00:00Z"}}, [], {}
    ) == {"analysis": {}}
    for result in ({}, {"date": "yesterday"}):
        with pytest.raises(WorkflowContractError):
            project_compute_outputs(value, {"computed_result": result}, [], {})


def test_compute_input_contract_compares_every_complete_schema_without_code_inference():
    contract = {"json_schema": schema(unit="mg"), "fields": {"var": ["metrics"]}}
    version = SimpleNamespace(**deepcopy(contract))
    equivalent = SimpleNamespace(
        **{key: deepcopy(contract[key]) for key in reversed(contract)}
    )
    assert validate_compute_method_inputs(contract, [version, equivalent]) is None
    for changed_key in ("json_schema", "fields"):
        changed = deepcopy(contract)
        changed[changed_key] = {}
        with pytest.raises(WorkflowContractError, match="differs"):
            validate_compute_method_inputs(
                contract, [version, SimpleNamespace(**changed)]
            )
    for versions in ([], [None]):
        with pytest.raises(WorkflowContractError):
            validate_compute_method_inputs(contract, versions)
