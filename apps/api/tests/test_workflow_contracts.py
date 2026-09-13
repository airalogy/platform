"""Manual Workflow contracts do not depend on an AI proposal or a database."""

from copy import deepcopy
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.services.workflow_contracts import (
    MAX_WORKFLOW_EDGES,
    MAX_WORKFLOW_NODES,
    WorkflowCondition,
    WorkflowContractError,
    WorkflowEdgeOutcome,
    WorkflowFieldSpec,
    WorkflowGraph,
    evaluate_all_active_join,
    evaluate_workflow_condition,
    topological_node_ids,
    validate_workflow_conditions,
    validate_workflow_graph,
    workflow_execution_digest,
    workflow_revision_digest,
)

PROTOCOL_ID = "11111111-1111-1111-1111-111111111111"
VERSION_ID = "22222222-2222-2222-2222-222222222222"
OTHER_VERSION_ID = "33333333-3333-3333-3333-333333333333"
PIPELINE_REVISION_ID = "44444444-4444-4444-4444-444444444444"


def protocol(node_id="measure", **kwargs):
    return {
        "node_id": node_id,
        "kind": "protocol",
        "protocol_id": PROTOCOL_ID,
        "protocol_version_id": VERSION_ID,
        **kwargs,
    }


def edge(source, target, **kwargs):
    return {
        "edge_id": f"{source}-to-{target}",
        "source_node_id": source,
        "target_node_id": target,
        **kwargs,
    }


def graph(nodes=None, edges=None, **kwargs):
    return {
        "schema_version": 1,
        "nodes": nodes if nodes is not None else [protocol()],
        "edges": edges if edges is not None else [],
        "bindings": [],
        **kwargs,
    }


def condition(**kwargs):
    return WorkflowCondition.model_validate(
        {
            "path": ["var", "yield"],
            "value_type": "number",
            "operator": "gte",
            "value": 5,
            "unit": "mg",
            **kwargs,
        }
    )


def catalog(value_type="number", unit="mg", **kwargs):
    return {
        ("var", "yield"): WorkflowFieldSpec(value_type=value_type, unit=unit, **kwargs)
    }


def test_single_protocol_requires_no_ai_decision_or_artificial_second_node():
    result = validate_workflow_graph(graph())
    assert result.schema_version == 1
    assert len(result.nodes) == 1
    assert result.nodes[0].protocol_id == UUID(PROTOCOL_ID)
    assert result.nodes[0].protocol_version_id == UUID(VERSION_ID)
    assert result.edges == []
    assert result.bindings == []
    assert topological_node_ids(result) == ["measure"]


def test_parallel_same_protocol_occurrences_and_different_versions_are_distinct():
    result = validate_workflow_graph(
        graph(
            [
                protocol("replicate_b"),
                protocol("replicate_a"),
                protocol("repeat_new_version", protocol_version_id=OTHER_VERSION_ID),
            ]
        )
    )
    assert len({node.node_id for node in result.nodes}) == 3
    assert len({node.protocol_id for node in result.nodes}) == 1
    assert len({node.protocol_version_id for node in result.nodes}) == 2
    assert topological_node_ids(result) == [
        "repeat_new_version",
        "replicate_a",
        "replicate_b",
    ]


def test_analysis_node_pins_exact_pipeline_revision_without_copying_private_recipe():
    result = validate_workflow_graph(
        graph(
            [
                protocol(),
                {
                    "node_id": "analyze",
                    "kind": "analysis",
                    "pipeline_revision_id": PIPELINE_REVISION_ID,
                },
            ],
            [edge("measure", "analyze")],
        )
    )
    assert result.nodes[1].pipeline_revision_id == UUID(PIPELINE_REVISION_ID)
    assert "source_snapshot" not in result.nodes[1].model_dump()


@pytest.mark.parametrize(
    "invalid",
    [
        {"node_id": "measure", "kind": "protocol", "protocol_id": PROTOCOL_ID},
        {"node_id": "measure", "kind": "protocol", "protocol_version_id": VERSION_ID},
        protocol(protocol_version_id="latest"),
        protocol(pipeline_revision_id=PIPELINE_REVISION_ID),
        {"node_id": "analyze", "kind": "analysis"},
        {
            "node_id": "analyze",
            "kind": "analysis",
            "pipeline_revision_id": PIPELINE_REVISION_ID,
            "protocol_id": PROTOCOL_ID,
        },
        {
            "node_id": "analyze",
            "kind": "analysis",
            "pipeline_revision_id": PIPELINE_REVISION_ID,
            "initial_values": {"secret": "value"},
        },
        protocol(kind="arbitrary_python"),
        protocol(protocol_version="1.0.0"),
        protocol(source_code="print('not an executable contract')"),
    ],
)
def test_node_rejects_unpinned_cross_kind_and_unrecognized_fields(invalid):
    with pytest.raises(ValidationError):
        validate_workflow_graph(graph([invalid]))


@pytest.mark.parametrize("invalid_id", ["", "1node", "Node", "node.id", "a" * 65, 1])
def test_node_identifiers_are_bounded_and_not_coerced(invalid_id):
    with pytest.raises(ValidationError):
        validate_workflow_graph(graph([protocol(invalid_id)]))


@pytest.mark.parametrize("schema_version", [True, False, "1", 1.0, 5, None])
def test_schema_version_requires_exact_supported_integer(schema_version):
    with pytest.raises(ValidationError):
        validate_workflow_graph(graph(schema_version=schema_version))


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (graph([]), "at least 1"),
        (graph([protocol("a")] * 2), "node IDs must be unique"),
        (
            graph([protocol("a"), protocol("b")], [edge("a", "unknown")]),
            "unknown node",
        ),
        (
            graph([protocol("a"), protocol("b")], [edge("unknown", "b")]),
            "unknown node",
        ),
        (graph([protocol("a")], [edge("a", "a")]), "themselves"),
        (
            graph(
                [protocol("a"), protocol("b"), protocol("c")],
                [
                    edge("a", "b", edge_id="duplicate"),
                    edge("b", "c", edge_id="duplicate"),
                ],
            ),
            "edge IDs must be unique",
        ),
        (
            graph(
                [protocol("a"), protocol("b")],
                [edge("a", "b"), edge("a", "b", edge_id="same-dependency")],
            ),
            "dependencies must be unique",
        ),
        (
            graph(
                [protocol("a"), protocol("b")],
                [edge("a", "b"), edge("b", "a")],
            ),
            "cycle",
        ),
        (
            graph(
                [protocol("root"), protocol("a"), protocol("b"), protocol("c")],
                [edge("a", "b"), edge("b", "c"), edge("c", "a")],
            ),
            "cycle",
        ),
        (graph([protocol(f"n{i}") for i in range(MAX_WORKFLOW_NODES + 1)]), "at most"),
        (graph(bindings=[{"source_node_id": "measure"}]), "Field required"),
        (graph(untrusted_execution="execute automatically"), "Extra inputs"),
    ],
)
def test_graph_rejects_unsafe_structure_and_incomplete_bindings(payload, message):
    with pytest.raises(ValidationError, match=message):
        validate_workflow_graph(payload)


def test_topological_order_handles_sequence_parallel_and_join_independent_of_ui_order():
    value = validate_workflow_graph(
        graph(
            [protocol(name) for name in ["finish", "b", "start", "a"]],
            [
                edge("b", "finish"),
                edge("start", "b"),
                edge("a", "finish"),
                edge("start", "a"),
            ],
        )
    )
    assert topological_node_ids(value) == ["start", "a", "b", "finish"]


def test_revision_seals_layout_while_execution_digest_ignores_layout_and_array_order():
    original = graph([protocol("a"), protocol("b")], [edge("a", "b")])
    layout = deepcopy(original)
    layout["nodes"].reverse()
    layout["nodes"][0]["title"] = "重测 / Repeat measurement"
    layout["nodes"][0]["position"] = {"x": 300, "y": -25.5}
    first, second = map(validate_workflow_graph, [original, layout])
    assert workflow_revision_digest(first) != workflow_revision_digest(second)
    assert workflow_execution_digest(first) == workflow_execution_digest(second)
    assert topological_node_ids(first) == topological_node_ids(second)


@pytest.mark.parametrize(
    "field,value",
    [("protocol_version_id", OTHER_VERSION_ID), ("initial_values", {"dose": 2})],
)
def test_execution_digest_seals_exact_version_and_inputs(field, value):
    first = validate_workflow_graph(graph())
    second = validate_workflow_graph(graph([protocol(**{field: value})]))
    assert workflow_execution_digest(first) != workflow_execution_digest(second)


def test_helpers_revalidate_mutated_nested_containers_in_frozen_models():
    value = validate_workflow_graph(graph())
    value.nodes.append(value.nodes[0])
    for helper in [
        validate_workflow_graph,
        topological_node_ids,
        workflow_revision_digest,
        workflow_execution_digest,
    ]:
        with pytest.raises(ValidationError, match="node IDs must be unique"):
            helper(value)


@pytest.mark.parametrize(
    "invalid",
    [float("nan"), float("inf"), {"key": object()}, (1, 2), {1: "bad"}, "x" * 140_000],
)
def test_initial_values_require_bounded_finite_json(invalid):
    with pytest.raises(ValidationError):
        validate_workflow_graph(graph([protocol(initial_values={"value": invalid})]))


def test_initial_value_depth_is_bounded_without_recursion_failure():
    nested = {}
    for _ in range(30):
        nested = {"child": nested}
    with pytest.raises(ValidationError, match="structural limit"):
        validate_workflow_graph(graph([protocol(initial_values=nested)]))


@pytest.mark.parametrize(
    "position",
    [
        {"x": float("nan"), "y": 1},
        {"x": "1", "y": 1},
        {"x": True, "y": 1},
        {"x": 1e9, "y": 1},
    ],
)
def test_position_rejects_nonfinite_coerced_and_unbounded_coordinates(position):
    with pytest.raises(ValidationError):
        validate_workflow_graph(graph([protocol(position=position)]))


@pytest.mark.parametrize(
    "changes",
    [
        {"value": True},
        {"value": "5"},
        {"value": None},
        {"value": [5]},
        {"value": float("nan")},
        {"value": float("inf")},
        {"value_type": "integer", "value": 1.5},
        {"value_type": "string", "operator": "gte", "value": "5", "unit": None},
        {"value_type": "boolean", "operator": "eq", "value": 1, "unit": None},
        {"value_type": "boolean", "operator": "eq", "value": True},
        {"operator": "eval"},
        {"expression": "__import__('os')"},
        {"path": []},
        {"path": ["var", 1]},
        {"path": ["var", ""]},
        {"path": ["var"] * 9},
    ],
)
def test_conditions_do_not_coerce_types_or_accept_expressions(changes):
    with pytest.raises(ValidationError):
        condition(**changes)


@pytest.mark.parametrize(
    "operator,value,expected",
    [
        ("eq", 5, True),
        ("eq", 6, False),
        ("ne", 6, True),
        ("gt", 5, False),
        ("gte", 5, True),
        ("lt", 4, True),
        ("lte", 6, False),
    ],
)
def test_numeric_condition_comparison(operator, value, expected):
    assert (
        evaluate_workflow_condition(
            condition(operator=operator), {"var": {"yield": value}}, catalog()
        )
        is expected
    )


@pytest.mark.parametrize(
    "value_type,value", [("boolean", True), ("string", "confirmed"), ("integer", 3)]
)
def test_supported_scalar_comparisons_keep_strict_types(value_type, value):
    predicate = condition(value_type=value_type, operator="eq", value=value, unit=None)
    assert evaluate_workflow_condition(
        predicate, {"var": {"yield": value}}, catalog(value_type, unit=None)
    )


@pytest.mark.parametrize(
    "output",
    [
        {},
        {"var": {}},
        {"var": None},
        {"var": {"yield": None}},
        {"var": {"yield": "5"}},
        {"var": {"yield": True}},
        {"var": {"yield": float("nan")}},
        {"var": {"yield": float("inf")}},
        {"var": {"yield": [5]}},
    ],
)
def test_missing_null_and_conflicting_output_fail_closed_even_for_not_equal(output):
    with pytest.raises(WorkflowContractError):
        evaluate_workflow_condition(
            condition(operator="ne"), output, catalog(nullable=True)
        )


@pytest.mark.parametrize(
    "wrong_catalog",
    [
        {},
        {("var", "yield"): {"value_type": "number", "unit": "mg"}},
        catalog("integer"),
        catalog(unit="g"),
        catalog(unit=None),
    ],
)
def test_catalog_is_authoritative_for_known_field_type_and_unit(wrong_catalog):
    with pytest.raises(WorkflowContractError):
        evaluate_workflow_condition(condition(), {"var": {"yield": 100}}, wrong_catalog)


def test_literal_field_keys_do_not_become_expressions_wildcards_or_attributes():
    key = "result.mean/with~punctuation"
    predicate = condition(path=["var", key])
    fields = {("var", key): WorkflowFieldSpec(value_type="number", unit="mg")}
    assert evaluate_workflow_condition(predicate, {"var": {key: 9}}, fields)
    with pytest.raises(WorkflowContractError, match="missing"):
        evaluate_workflow_condition(
            predicate, {"var": {"result": {"mean/with~punctuation": 9}}}, fields
        )


def test_path_does_not_traverse_array_indices_or_python_attributes():
    predicate = condition(path=["var", "0"])
    fields = {("var", "0"): WorkflowFieldSpec(value_type="number", unit="mg")}
    with pytest.raises(WorkflowContractError, match="missing"):
        evaluate_workflow_condition(predicate, {"var": [9]}, fields)


def test_graph_condition_validation_uses_source_node_catalog_not_target_catalog():
    value = validate_workflow_graph(
        graph(
            [protocol("source"), protocol("target")],
            [edge("source", "target", condition=condition().model_dump(mode="json"))],
        )
    )
    validate_workflow_conditions(value, {"source": catalog()})
    with pytest.raises(WorkflowContractError, match="unknown field"):
        validate_workflow_conditions(value, {"target": catalog()})


def test_unconditional_graph_does_not_require_spurious_field_catalog():
    value = validate_workflow_graph(
        graph([protocol("a"), protocol("b")], [edge("a", "b")])
    )
    validate_workflow_conditions(value, {})


@pytest.mark.parametrize(
    "outcomes,expected",
    [
        ([], "ready"),
        (["pending"], "waiting"),
        (["active"], "ready"),
        (["inactive"], "branch_not_selected"),
        (["failed"], "blocked"),
        (["cancelled"], "blocked"),
        (["active", "active"], "ready"),
        (["active", "inactive"], "ready"),
        (["inactive", "inactive"], "branch_not_selected"),
        (["active", "pending"], "waiting"),
        (["inactive", "pending"], "waiting"),
        (["failed", "pending"], "waiting"),
        (["active", "failed"], "blocked"),
        (["inactive", "failed"], "blocked"),
        (["active", "cancelled"], "blocked"),
        (["inactive", "cancelled"], "blocked"),
    ],
)
def test_all_active_join_distinguishes_not_selected_from_execution_failure(
    outcomes, expected
):
    decision = evaluate_all_active_join(outcomes)
    assert decision.state == expected
    assert decision.active_count == outcomes.count("active")
    assert decision.inactive_count == outcomes.count("inactive")
    assert decision.pending_count == outcomes.count("pending")
    assert decision.failed_count == outcomes.count("failed")
    assert decision.cancelled_count == outcomes.count("cancelled")


def test_branch_false_does_not_poison_other_successful_branch_at_join():
    assert (
        evaluate_all_active_join([WorkflowEdgeOutcome.INACTIVE]).state
        == "branch_not_selected"
    )
    assert (
        evaluate_all_active_join(
            [WorkflowEdgeOutcome.ACTIVE, WorkflowEdgeOutcome.INACTIVE]
        ).state
        == "ready"
    )
    assert (
        evaluate_all_active_join(
            [WorkflowEdgeOutcome.ACTIVE, WorkflowEdgeOutcome.FAILED]
        ).state
        == "blocked"
    )


@pytest.mark.parametrize(
    "outcomes",
    [
        ["skipped"],
        [False],
        [None],
        ["success"],
        [{}],
        ["active"] * (MAX_WORKFLOW_EDGES + 1),
    ],
)
def test_join_rejects_unclassified_states_or_excessive_input(outcomes):
    with pytest.raises(WorkflowContractError):
        evaluate_all_active_join(outcomes)


def test_graph_json_roundtrip_preserves_pins_conditions_and_digests():
    value = validate_workflow_graph(
        graph(
            [protocol("a"), protocol("b")],
            [edge("a", "b", condition=condition().model_dump(mode="json"))],
        )
    )
    restored = WorkflowGraph.model_validate_json(value.model_dump_json())
    assert restored == value
    assert workflow_revision_digest(restored) == workflow_revision_digest(value)
    assert workflow_execution_digest(restored) == workflow_execution_digest(value)
