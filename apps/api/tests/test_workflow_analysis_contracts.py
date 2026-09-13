"""Published builtin Workflow methods reuse deterministic scientific contracts."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services.analysis_engine import AnalysisRecipe, compute_analysis
from app.services.workflow_analysis_contracts import (
    analysis_output_catalog,
    project_analysis_outputs,
    validate_analysis_method_inputs,
)
from app.services.workflow_contracts import (
    WorkflowAnalysisOutput,
    WorkflowAnalysisRecordSource,
    WorkflowCondition,
    WorkflowContractError,
    WorkflowFieldSpec,
    evaluate_workflow_condition,
    validate_workflow_graph,
    workflow_execution_digest,
    workflow_revision_digest,
)
from app.services.workflow_data import resolve_workflow_bindings, validate_workflow_data

PROTOCOL = "11111111-1111-1111-1111-111111111111"
VERSION = "22222222-2222-2222-2222-222222222222"
PUBLICATION = "33333333-3333-3333-3333-333333333333"


def version(properties=None):
    return SimpleNamespace(
        version="1.0.0",
        protocol_id=PROTOCOL,
        json_schema={
            "vars": {
                "type": "object",
                "properties": properties
                or {
                    "dose": {"type": "number", "unit": "mg"},
                    "arm": {"type": "string", "enum": ["control", "treated"]},
                },
            }
        },
    )


def recipe(**changes):
    return AnalysisRecipe.model_validate({"numeric_fields": ["dose"], **changes})


def output(**changes):
    return {
        "output_id": "mean_dose",
        "field": "dose",
        "statistic": "mean",
        "group": {},
        **changes,
    }


def protocol(node_id):
    return {
        "node_id": node_id,
        "kind": "protocol",
        "protocol_id": PROTOCOL,
        "protocol_version_id": VERSION,
    }


def analysis(**changes):
    return {
        "node_id": "analyze",
        "kind": "analysis",
        "method_publication_id": PUBLICATION,
        "record_sources": [{"source_node_id": "measure", "cardinality": "one"}],
        "input_policy": "all_declared",
        "analysis_outputs": [output()],
        **changes,
    }


def edge(source, target):
    return {
        "edge_id": f"{source}-to-{target}",
        "source_node_id": source,
        "target_node_id": target,
    }


def graph(**changes):
    return {
        "schema_version": 2,
        "nodes": [protocol("measure"), analysis(), protocol("followup")],
        "edges": [edge("measure", "analyze"), edge("analyze", "followup")],
        "bindings": [
            {
                "binding_id": "dose",
                "source_node_id": "analyze",
                "source_path": ["analysis", "mean_dose"],
                "target_node_id": "followup",
                "target_path": ["var", "dose"],
                "value_type": "number",
                "unit": "mg",
                "cardinality": "one",
            }
        ],
        **changes,
    }


def rows(values, *, groups=None):
    return [
        {
            "record_id": f"record-{index}",
            "record_version": 1,
            "protocol_version": "1.0.0",
            "data": {
                "var": {
                    "dose": value,
                    **({"arm": groups[index]} if groups is not None else {}),
                }
            },
        }
        for index, value in enumerate(values)
    ]


def run(
    values=(2, 4), *, definition=None, outputs=None, input_version=None, groups=None
):
    definition = definition or recipe()
    outputs = [output()] if outputs is None else outputs
    fields = validate_analysis_method_inputs(definition, [input_version or version()])
    catalog = analysis_output_catalog(definition, fields, outputs)
    result = compute_analysis(definition, rows(values, groups=groups), fields)
    return definition, result, outputs, catalog


def test_workflow_v1_canonical_json_and_both_historical_digests_are_unchanged():
    item = validate_workflow_graph(
        {
            "schema_version": 1,
            "nodes": [protocol("measure")],
            "edges": [],
            "bindings": [],
        }
    )
    assert item.model_dump(mode="json") == {
        "schema_version": 1,
        "nodes": [
            {
                **protocol("measure"),
                "title": "",
                "position": None,
                "initial_values": {},
                "pipeline_revision_id": None,
            }
        ],
        "edges": [],
        "bindings": [],
    }
    assert (
        workflow_revision_digest(item)
        == "0d76ca7fdeb42042e8c925efce9b083208b397a174d4c7343696138041833ea0"
    )
    assert (
        workflow_execution_digest(item)
        == "8566ef6dac479e7fbd45a29aa8dd333bba3db37441e90b9b213cd53b08f67523"
    )


def test_v2_analysis_preserves_publication_inputs_and_explicit_outputs_in_digest():
    item = validate_workflow_graph(graph())
    saved = item.model_dump(mode="json")
    assert saved["nodes"][1]["method_publication_id"] == PUBLICATION
    assert saved["nodes"][1]["record_sources"] == [
        {"source_node_id": "measure", "cardinality": "one"}
    ]
    changed = deepcopy(saved)
    changed["nodes"][1]["analysis_outputs"][0]["statistic"] = "median"
    assert workflow_execution_digest(item) != workflow_execution_digest(
        validate_workflow_graph(changed)
    )
    changed = deepcopy(saved)
    changed["nodes"][1]["position"] = {"x": 1.0, "y": 2.0}
    assert workflow_execution_digest(item) == workflow_execution_digest(
        validate_workflow_graph(changed)
    )
    assert workflow_revision_digest(item) != workflow_revision_digest(
        validate_workflow_graph(changed)
    )


def test_v2_same_protocol_cards_are_distinct_explicit_record_sources():
    item = validate_workflow_graph(
        graph(
            nodes=[
                protocol("measure"),
                protocol("replicate"),
                analysis(
                    record_sources=[
                        {"source_node_id": "measure"},
                        {"source_node_id": "replicate"},
                    ],
                    analysis_outputs=[],
                ),
            ],
            edges=[edge("measure", "analyze"), edge("replicate", "analyze")],
            bindings=[],
        )
    )
    assert len(item.nodes[-1].record_sources) == 2
    assert item.nodes[-1].analysis_outputs == []
    assert item.nodes[0].protocol_id == item.nodes[1].protocol_id


@pytest.mark.parametrize(
    "change",
    [
        {"method_publication_id": None},
        {"pipeline_revision_id": PUBLICATION},
        {"record_sources": []},
        {"input_policy": None},
        {"input_policy": "active_only"},
        {
            "record_sources": [
                {"source_node_id": "measure"},
                {"source_node_id": "measure"},
            ]
        },
        {"record_sources": [{"source_node_id": "measure", "cardinality": "many"}]},
        {"record_sources": [{"source_node_id": "measure", "latest": True}]},
        {"record_sources": [{"source_node_id": "unknown"}]},
        {"record_sources": [{"source_node_id": "analyze"}]},
        {"record_sources": [{"source_node_id": "followup"}]},
        {"initial_values": {"dose": 3}},
        {"protocol_id": PROTOCOL},
        {"analysis_outputs": [output(), output()]},
    ],
)
def test_v2_analysis_rejects_private_implicit_duplicate_and_wrong_kind_inputs(change):
    with pytest.raises(ValidationError):
        validate_workflow_graph(
            graph(nodes=[protocol("measure"), analysis(**change), protocol("followup")])
        )


def test_v1_rejects_new_analysis_capabilities_instead_of_silently_upgrading():
    with pytest.raises(ValidationError, match="schema_version 2"):
        validate_workflow_graph(graph(schema_version=1))


def test_mutated_legacy_node_cannot_hide_new_analysis_inputs_during_revalidation():
    item = validate_workflow_graph(
        {
            "schema_version": 1,
            "nodes": [protocol("measure")],
            "edges": [],
            "bindings": [],
        }
    )
    item.nodes[0].record_sources.append(
        WorkflowAnalysisRecordSource(source_node_id="measure")
    )
    with pytest.raises(ValidationError):
        validate_workflow_graph(item)


@pytest.mark.parametrize(
    "changes",
    [
        {"source_path": ["var", "mean_dose"]},
        {"source_path": ["analysis", "unknown"]},
        {"source_path": ["analysis", "groups", "0"]},
        {"source_node_id": "measure", "source_path": ["analysis", "mean_dose"]},
        {
            "source_node_id": "measure",
            "source_path": ["var", "dose"],
            "target_node_id": "analyze",
        },
    ],
)
def test_analysis_bindings_require_declared_source_ports_and_protocol_targets(changes):
    candidate = graph()
    candidate["bindings"][0].update(changes)
    with pytest.raises(ValidationError):
        validate_workflow_graph(candidate)


@pytest.mark.parametrize(
    "other",
    [
        {"other": {"type": "number", "unit": "mg"}},
        {"dose": {"type": "string", "unit": "mg"}},
        {"dose": {"type": "number", "unit": "g"}},
        {"dose": {"type": "number"}},
        {"dose": {"type": "integer", "unit": "mg"}},
        {"dose": {"type": "number", "unit": "mg", "enum": [2, 4]}},
    ],
)
def test_every_input_schema_is_checked_before_combined_catalog(other):
    with pytest.raises(WorkflowContractError, match="missing or incompatible"):
        validate_analysis_method_inputs(recipe(), [version(), version(other)])


def test_method_inputs_require_at_least_one_explicit_version():
    with pytest.raises(WorkflowContractError):
        validate_analysis_method_inputs(recipe(), [])


def test_method_recipe_filters_and_groups_are_validated_in_every_source_schema():
    with pytest.raises(WorkflowContractError):
        validate_analysis_method_inputs(
            recipe(group_by=["arm"]),
            [version(), version({"dose": {"type": "number", "unit": "mg"}})],
        )
    with pytest.raises(WorkflowContractError):
        validate_analysis_method_inputs(
            recipe(filters=[{"field": "arm", "op": "eq", "value": True}]), [version()]
        )


@pytest.mark.parametrize("source_type", ["number", "integer"])
def test_output_catalog_has_exact_types_units_and_nullable_statistics(source_type):
    definition = recipe()
    fields = validate_analysis_method_inputs(
        definition, [version({"dose": {"type": source_type, "unit": " mg "}})]
    )
    statistics = [
        "count",
        "missing",
        "invalid",
        "mean",
        "median",
        "min",
        "max",
        "sum",
        "sample_stddev",
    ]
    result = analysis_output_catalog(
        definition,
        fields,
        [output(output_id=statistic, statistic=statistic) for statistic in statistics],
    )
    for statistic in statistics:
        spec = result[("analysis", statistic)]
        count = statistic in {"count", "missing", "invalid"}
        assert spec.unit == (None if count else "mg")
        assert spec.nullable is not count
        assert spec.value_type == (
            "integer"
            if count
            else source_type
            if statistic in {"min", "max", "sum"}
            else "number"
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"field": "unknown"},
        {"field": "arm"},
        {"group": {"arm": "control"}},
    ],
)
def test_output_catalog_rejects_nonselected_statistics_fields_and_unexpected_group(
    changes,
):
    with pytest.raises(WorkflowContractError):
        analysis_output_catalog(
            recipe(),
            validate_analysis_method_inputs(recipe(), [version()]),
            [output(**changes)],
        )


@pytest.mark.parametrize(
    "group", [{}, {"other": "control"}, {"arm": True}, {"arm": "unknown"}]
)
def test_grouped_output_requires_complete_strict_typed_enum_group(group):
    definition = recipe(group_by=["arm"])
    with pytest.raises(WorkflowContractError):
        analysis_output_catalog(
            definition,
            validate_analysis_method_inputs(definition, [version()]),
            [output(group=group)],
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"group": []},
        {"group": {"arm": float("nan")}},
        {"statistic": "execute_python"},
        {"expression": "result[0]"},
        {"field": " "},
    ],
)
def test_output_declaration_is_bounded_finite_and_not_executable(changes):
    with pytest.raises(ValidationError):
        WorkflowAnalysisOutput.model_validate(output(**changes))


def test_real_builtin_result_projects_and_binds_to_protocol_without_ai():
    definition, result, outputs, catalog = run()
    projected = project_analysis_outputs(definition, result, outputs, catalog)
    assert projected == {"analysis": {"mean_dose": 3}}
    item = validate_workflow_graph(graph())
    fields = {
        "analyze": catalog,
        "followup": {
            ("var", "dose"): WorkflowFieldSpec(value_type="number", unit="mg")
        },
    }
    validate_workflow_data(item, fields)
    resolved = resolve_workflow_bindings(
        item, "followup", {"analyze": projected}, fields
    )
    assert resolved.initial_values == {"dose": 3}
    assert resolved.bindings[0]["source_path"] == ["analysis", "mean_dose"]
    predicate = WorkflowCondition(
        path=["analysis", "mean_dose"],
        value_type="number",
        operator="gte",
        value=3,
        unit="mg",
    )
    assert evaluate_workflow_condition(predicate, projected, catalog) is True


def test_group_projection_is_stable_when_report_group_order_changes():
    definition, result, outputs, catalog = run(
        (2, 10, 4),
        definition=recipe(group_by=["arm"]),
        outputs=[output(group={"arm": "control"})],
        groups=["control", "treated", "control"],
    )
    expected = {"analysis": {"mean_dose": 3}}
    assert project_analysis_outputs(definition, result, outputs, catalog) == expected
    result["groups"].reverse()
    assert project_analysis_outputs(definition, result, outputs, catalog) == expected


def test_missing_group_is_not_replaced_with_first_group_or_zero():
    definition, result, outputs, catalog = run(
        (10,),
        definition=recipe(group_by=["arm"]),
        outputs=[output(group={"arm": "control"})],
        groups=["treated"],
    )
    with pytest.raises(WorkflowContractError, match="exactly one"):
        project_analysis_outputs(definition, result, outputs, catalog)


def test_explicit_missing_group_is_distinct_and_can_be_selected():
    definition, result, outputs, catalog = run(
        (2, 10),
        definition=recipe(group_by=["arm"]),
        outputs=[output(group={"arm": None})],
        groups=[None, "treated"],
    )
    assert project_analysis_outputs(definition, result, outputs, catalog) == {
        "analysis": {"mean_dose": 2}
    }


def test_null_statistics_remain_null_evidence_and_cannot_bind_to_protocol():
    definition, result, outputs, catalog = run((None,))
    projected = project_analysis_outputs(definition, result, outputs, catalog)
    assert projected == {"analysis": {"mean_dose": None}}
    fields = {
        "analyze": catalog,
        "followup": {
            ("var", "dose"): WorkflowFieldSpec(value_type="number", unit="mg")
        },
    }
    with pytest.raises(WorkflowContractError, match="null"):
        resolve_workflow_bindings(
            validate_workflow_graph(graph()), "followup", {"analyze": projected}, fields
        )


def test_single_record_sample_stddev_is_nullable_and_report_only_node_needs_no_ports():
    definition, result, outputs, catalog = run(
        (2,), outputs=[output(statistic="sample_stddev")]
    )
    assert (
        project_analysis_outputs(definition, result, outputs, catalog)["analysis"][
            "mean_dose"
        ]
        is None
    )
    assert project_analysis_outputs(definition, result, [], {}) == {"analysis": {}}


@pytest.mark.parametrize(
    "mutation",
    [
        "engine",
        "unit",
        "type",
        "duplicate_group",
        "missing_stat",
        "wrong_stat_type",
        "wrong_group_type",
        "extra_group_field",
    ],
)
def test_projection_rejects_changed_or_ambiguous_result_contracts(mutation):
    definition, result, outputs, catalog = run(
        (2, 4),
        definition=recipe(group_by=["arm"]),
        outputs=[output(group={"arm": "control"})],
        groups=["control", "control"],
    )
    if mutation == "engine":
        result["engine_version"] = "other-engine"
    elif mutation == "unit":
        result["fields"][0]["unit"] = "g"
    elif mutation == "type":
        result["fields"][0]["type"] = "string"
    elif mutation == "duplicate_group":
        result["groups"].append(deepcopy(result["groups"][0]))
    elif mutation == "missing_stat":
        del result["groups"][0]["fields"]["dose"]["mean"]
    elif mutation == "wrong_stat_type":
        result["groups"][0]["fields"]["dose"]["mean"] = True
    elif mutation == "wrong_group_type":
        result["groups"][0]["key"][0]["type"] = "number"
    elif mutation == "extra_group_field":
        result["groups"][0]["key"][0]["extra"] = "ignored?"
    with pytest.raises(WorkflowContractError):
        project_analysis_outputs(definition, result, outputs, catalog)


def test_filter_only_fields_need_not_be_exposed_in_report_for_projection():
    definition = recipe(filters=[{"field": "arm", "op": "eq", "value": "control"}])
    definition, result, outputs, catalog = run(
        (2, 10), definition=definition, groups=["control", "treated"]
    )
    assert result["counts"] == {"total": 2, "included": 1, "filtered_out": 1}
    assert project_analysis_outputs(definition, result, outputs, catalog) == {
        "analysis": {"mean_dose": 2}
    }


def test_analysis_binding_rejects_condition_false_instead_of_borrowing_output():
    definition, result, outputs, catalog = run()
    projected = project_analysis_outputs(definition, result, outputs, catalog)
    candidate = graph()
    candidate["edges"][1]["condition"] = {
        "path": ["analysis", "mean_dose"],
        "value_type": "number",
        "operator": "gt",
        "value": 10,
        "unit": "mg",
    }
    fields = {
        "analyze": catalog,
        "followup": {
            ("var", "dose"): WorkflowFieldSpec(value_type="number", unit="mg")
        },
    }
    with pytest.raises(WorkflowContractError, match="not selected"):
        resolve_workflow_bindings(
            validate_workflow_graph(candidate),
            "followup",
            {"analyze": projected},
            fields,
        )
