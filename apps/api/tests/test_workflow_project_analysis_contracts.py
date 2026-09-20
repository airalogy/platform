"""Multi-source Workflow ports reuse exact Project Schema and statistic rules."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.services.analysis_engine import canonical_digest
from app.services.project_analysis_engine import (
    ProjectAnalysisError,
    compute_project_analysis,
    validate_project_input_schemas,
    validate_project_recipe,
)
from app.services.workflow_analysis_contracts import (
    project_method_output_catalog,
    project_workflow_outputs,
    validate_project_method_inputs,
)
from app.services.workflow_contracts import (
    WorkflowContractError,
    WorkflowFieldSpec,
    validate_workflow_graph,
    workflow_execution_digest,
    workflow_revision_digest,
)
from tests.test_project_analysis_engine import project_fixture


def method_contract(recipe, snapshot):
    labels = {slot.slot_id: slot.label for slot in recipe.slots}
    slots = []
    for item in snapshot["inputs"]:
        source = item["snapshot"]
        slots.append(
            {
                "slot_id": item["slot_id"],
                "label": labels[item["slot_id"]],
                "protocol_id": source["protocol_id"],
                "versions": [
                    {
                        **deepcopy(version),
                        "schema_digest": canonical_digest(
                            {**version, "protocol_id": source["protocol_id"]}
                        ),
                    }
                    for version in source["schemas"]
                ],
            }
        )
    return {"schema_version": 1, "slots": slots}


def refresh_digest(slot):
    for version in slot["versions"]:
        version["schema_digest"] = canonical_digest(
            {
                **{
                    key: value
                    for key, value in version.items()
                    if key != "schema_digest"
                },
                "protocol_id": slot["protocol_id"],
            }
        )


def actual_versions(contract):
    return {
        slot["slot_id"]: [
            SimpleNamespace(**version, protocol_id=UUID(slot["protocol_id"]))
            for version in slot["versions"]
        ]
        for slot in contract["slots"]
    }


def output(output_id="dose_mean", *, slot="treatment", field="dose", **changes):
    return {
        "output_id": output_id,
        "source": {"kind": "local", "slot_id": slot},
        "field": field,
        "statistic": "mean",
        "group": {},
        **changes,
    }


def graph():
    recipe, snapshot = project_fixture()
    contract = method_contract(recipe, snapshot)
    nodes = []
    sources = []
    for slot in contract["slots"]:
        names = (
            ["treatment_first", "treatment_second"]
            if slot["slot_id"] == "treatment"
            else ["assay"]
        )
        for name in names:
            nodes.append(
                {
                    "node_id": name,
                    "kind": "protocol",
                    "protocol_id": slot["protocol_id"],
                    "protocol_version_id": slot["versions"][0]["id"],
                }
            )
            sources.append(
                {
                    "source_node_id": name,
                    "slot_id": slot["slot_id"],
                    "cardinality": "one",
                }
            )
    nodes.append(
        {
            "node_id": "analysis",
            "kind": "analysis",
            "analysis_kind": "project",
            "method_publication_id": str(UUID(int=50)),
            "record_sources": sources,
            "input_policy": "all_declared",
            "project_outputs": [output()],
        }
    )
    return {
        "schema_version": 6,
        "nodes": nodes,
        "edges": [
            {
                "edge_id": f"{source['source_node_id']}_analysis",
                "source_node_id": source["source_node_id"],
                "target_node_id": "analysis",
            }
            for source in sources
        ],
        "bindings": [],
    }


def test_schema_only_validation_never_requires_or_fabricates_records():
    recipe, snapshot = project_fixture()
    sources = {
        item["slot_id"]: {
            key: deepcopy(item["snapshot"][key]) for key in ("schemas", "fields")
        }
        for item in snapshot["inputs"]
    }
    catalogs, joined = validate_project_input_schemas(recipe, sources)
    assert catalogs["treatment"]["dose"]["unit"] == "mg"
    assert catalogs["assay"]["response"]["unit"] == "%"
    assert joined[0]["semantic_label"] == "Administered dose"
    for item in snapshot["inputs"]:
        del item["snapshot"]["records"]
    with pytest.raises(ProjectAnalysisError):
        validate_project_recipe(recipe, snapshot)


def test_project_output_can_bind_a_direct_downstream_protocol_but_not_an_undeclared_port():
    value = graph()
    value["nodes"].append({**value["nodes"][0], "node_id": "next"})
    value["edges"].append(
        {
            "edge_id": "analysis_next",
            "source_node_id": "analysis",
            "target_node_id": "next",
        }
    )
    value["bindings"].append(
        {
            "binding_id": "dose_input",
            "source_node_id": "analysis",
            "source_path": ["analysis", "dose_mean"],
            "target_node_id": "next",
            "target_path": ["var", "dose"],
            "value_type": "number",
            "unit": "mg",
            "cardinality": "one",
        }
    )
    assert validate_workflow_graph(value).bindings[0].source_path == [
        "analysis",
        "dose_mean",
    ]
    value["bindings"][0]["source_path"][1] = "not_declared"
    with pytest.raises(ValueError, match="undeclared analysis output"):
        validate_workflow_graph(value)


def test_method_contract_pins_per_slot_versions_and_accepts_repeated_occurrences():
    recipe, snapshot = project_fixture()
    contract = method_contract(recipe, snapshot)
    versions = actual_versions(contract)
    versions["treatment"].append(deepcopy(versions["treatment"][0]))
    assert (
        validate_project_method_inputs(recipe, contract, versions)["treatment"][0][
            "key"
        ]
        == "dose"
    )
    versions["treatment"][1].id = str(UUID(int=9999))
    with pytest.raises(WorkflowContractError, match="pinned input version"):
        validate_project_method_inputs(recipe, contract, versions)
    versions = actual_versions(contract)
    versions["treatment"][0].fields = {"edited": True}
    with pytest.raises(WorkflowContractError, match="pinned input version"):
        validate_project_method_inputs(recipe, contract, versions)


@pytest.mark.parametrize("change", ["missing", "type", "unit", "enum", "file"])
def test_every_referenced_field_is_compatible_in_every_published_version(change):
    recipe, snapshot = project_fixture()
    contract = method_contract(recipe, snapshot)
    slot = contract["slots"][0]
    newer = deepcopy(slot["versions"][0])
    newer["id"] = str(UUID(int=900))
    newer["version"] = "2.0.0"
    properties = newer["json_schema"]["properties"]
    if change == "missing":
        del properties["dose"]
    elif change == "type":
        properties["dose"]["type"] = "integer"
    elif change == "unit":
        properties["dose"]["unit"] = "g"
    elif change == "enum":
        properties["sample_id"]["enum"] = ["S1", "S2"]
    else:
        properties["dose"] = {"type": "string", "format": "airalogy.FileId"}
    slot["versions"].append(newer)
    refresh_digest(slot)
    with pytest.raises(WorkflowContractError):
        validate_project_method_inputs(recipe, contract)


def test_unreferenced_schema_changes_remain_allowed_but_full_digest_is_fixed():
    recipe, snapshot = project_fixture()
    contract = method_contract(recipe, snapshot)
    slot = contract["slots"][0]
    newer = deepcopy(slot["versions"][0])
    newer.update(id=str(UUID(int=900)), version="2.0.0")
    newer["json_schema"]["properties"]["unrelated"] = {"type": "object"}
    slot["versions"].append(newer)
    refresh_digest(slot)
    assert validate_project_method_inputs(recipe, contract)
    newer["fields"] = {"changed": True}
    with pytest.raises(WorkflowContractError, match="digest changed"):
        validate_project_method_inputs(recipe, contract)


@pytest.mark.parametrize(
    "change",
    [
        "missing_slot",
        "empty_actual",
        "extra_actual",
        "duplicate_slot",
        "duplicate_version",
        "wrong_label",
        "boolean_version",
        "unknown_property",
    ],
)
def test_project_contract_rejects_ambiguous_or_incomplete_shapes(change):
    recipe, snapshot = project_fixture()
    contract = method_contract(recipe, snapshot)
    versions = actual_versions(contract)
    if change == "missing_slot":
        contract["slots"].pop()
    elif change == "empty_actual":
        versions["assay"] = []
    elif change == "extra_actual":
        versions["unknown"] = versions["assay"]
    elif change == "duplicate_slot":
        contract["slots"].append(deepcopy(contract["slots"][0]))
    elif change == "duplicate_version":
        contract["slots"][0]["versions"].append(
            deepcopy(contract["slots"][0]["versions"][0])
        )
    elif change == "wrong_label":
        contract["slots"][0]["label"] = "Another meaning"
    elif change == "boolean_version":
        contract["schema_version"] = True
    else:
        contract["records"] = []
    with pytest.raises(WorkflowContractError):
        validate_project_method_inputs(recipe, contract, versions)


def test_local_and_join_projection_use_stable_slot_keys_and_exact_units():
    recipe, snapshot = project_fixture()
    contract = method_contract(recipe, snapshot)
    result = compute_project_analysis(recipe, snapshot)
    result["local_results"].reverse()
    outputs = [
        output(),
        output("joined_response", field="response", source={"kind": "join"}),
        output("sample_count", statistic="count"),
    ]
    catalog = project_method_output_catalog(recipe, contract, outputs)
    assert catalog[("analysis", "dose_mean")] == WorkflowFieldSpec(
        value_type="number", nullable=True, unit="mg"
    )
    assert catalog[("analysis", "sample_count")] == WorkflowFieldSpec(
        value_type="integer", nullable=False
    )
    assert project_workflow_outputs(recipe, contract, result, outputs, catalog) == {
        "analysis": {"dose_mean": 4.0, "sample_count": 3, "joined_response": 15.0}
    }
    assert project_workflow_outputs(recipe, contract, result, [], {}) == {
        "analysis": {}
    }


@pytest.mark.parametrize(
    "change",
    [
        "unknown_slot",
        "unknown_field",
        "nested_group",
        "missing_group",
        "duplicate_output",
    ],
)
def test_project_output_declarations_require_exact_supported_selections(change):
    recipe, snapshot = project_fixture()
    contract = method_contract(recipe, snapshot)
    outputs = [output()]
    if change == "unknown_slot":
        outputs[0]["source"]["slot_id"] = "unknown"
    elif change == "unknown_field":
        outputs[0]["field"] = "sample_id"
    elif change == "nested_group":
        outputs[0]["group"] = {"nested": {"value": "S1"}}
    elif change == "missing_group":
        outputs[0]["group"] = {"sample_id": "S1"}
    else:
        outputs.append(deepcopy(outputs[0]))
    with pytest.raises(WorkflowContractError):
        project_method_output_catalog(recipe, contract, outputs)


def test_independent_evidence_never_exposes_implicit_join_output():
    recipe, snapshot = project_fixture("evidence_synthesis")
    contract = method_contract(recipe, snapshot)
    with pytest.raises(WorkflowContractError, match="declared local slot or Join"):
        project_method_output_catalog(
            recipe, contract, [output(source={"kind": "join"})]
        )


@pytest.mark.parametrize(
    "change",
    [
        "duplicate_slot",
        "missing_slot",
        "unknown_slot",
        "wrong_recipe",
        "wrong_engine",
        "wrong_unit",
        "duplicate_group",
        "null_count",
        "wrong_join",
    ],
)
def test_result_projection_rejects_changed_or_ambiguous_reports(change):
    recipe, snapshot = project_fixture()
    contract = method_contract(recipe, snapshot)
    result = compute_project_analysis(recipe, snapshot)
    outputs = [output(statistic="count")]
    catalog = project_method_output_catalog(recipe, contract, outputs)
    first = result["local_results"][0]
    if change == "duplicate_slot":
        result["local_results"][1] = deepcopy(first)
    elif change == "missing_slot":
        result["local_results"].pop()
    elif change == "unknown_slot":
        first["slot_id"] = "unlisted"
    elif change == "wrong_recipe":
        first["recipe_digest"] = "0" * 64
    elif change == "wrong_engine":
        result["engine_version"] = "untrusted"
    elif change == "wrong_unit":
        first["report"]["fields"][0]["unit"] = "g"
    elif change == "duplicate_group":
        first["report"]["groups"].append(deepcopy(first["report"]["groups"][0]))
    elif change == "null_count":
        first["report"]["groups"][0]["fields"]["dose"]["count"] = None
    else:
        result["join"]["fields"][0]["unit"] = "g"
    with pytest.raises(WorkflowContractError):
        project_workflow_outputs(recipe, contract, result, outputs, catalog)


def test_null_measurement_remains_null_not_a_zero_or_successful_condition():
    recipe, snapshot = project_fixture()
    for row in snapshot["inputs"][0]["snapshot"]["records"]:
        row["data"]["var"]["dose"] = None
    contract = method_contract(recipe, snapshot)
    result = compute_project_analysis(recipe, snapshot)
    outputs = [output()]
    catalog = project_method_output_catalog(recipe, contract, outputs)
    assert (
        project_workflow_outputs(recipe, contract, result, outputs, catalog)[
            "analysis"
        ]["dose_mean"]
        is None
    )


def test_v6_graph_accepts_repeated_protocol_occurrences_in_one_distinct_slot():
    value = validate_workflow_graph(graph())
    assert len(value.nodes[-1].record_sources) == 3
    assert value.nodes[-1].project_outputs[0].source.slot_id == "treatment"
    assert workflow_revision_digest(value) != workflow_execution_digest(value)


@pytest.mark.parametrize(
    "change",
    [
        "old_schema",
        "missing_slot",
        "duplicate_node",
        "mixed_protocol",
        "same_protocol_slots",
        "builtin_output",
        "compute_output",
        "no_direct_edge",
        "duplicate_output",
        "project_output_on_builtin",
    ],
)
def test_project_graph_rejects_incomplete_or_ambiguous_bindings(change):
    value = graph()
    node = value["nodes"][-1]
    if change == "old_schema":
        value["schema_version"] = 5
    elif change == "missing_slot":
        del node["record_sources"][0]["slot_id"]
    elif change == "duplicate_node":
        node["record_sources"].append(deepcopy(node["record_sources"][0]))
    elif change == "mixed_protocol":
        node["record_sources"][1]["slot_id"] = "assay"
    elif change == "same_protocol_slots":
        value["nodes"][2]["protocol_id"] = value["nodes"][0]["protocol_id"]
    elif change == "builtin_output":
        node["analysis_outputs"] = [
            {key: val for key, val in output().items() if key != "source"}
        ]
    elif change == "compute_output":
        node["compute_outputs"] = [
            {
                "output_id": "port",
                "path": ["value"],
                "value_type": "number",
                "nullable": False,
            }
        ]
    elif change == "no_direct_edge":
        value["edges"].pop()
    elif change == "duplicate_output":
        node["project_outputs"].append(deepcopy(node["project_outputs"][0]))
    else:
        del node["analysis_kind"]
    with pytest.raises(ValueError):
        validate_workflow_graph(value)


def test_legacy_source_and_project_defaults_do_not_change_sealed_v5_payload():
    from tests.test_workflow_analysis_contracts import graph as builtin_graph

    payload = builtin_graph(schema_version=5)
    value = validate_workflow_graph(payload).model_dump(mode="json")
    assert all("project_outputs" not in node for node in value["nodes"])
    assert all(
        "slot_id" not in item
        for node in value["nodes"]
        for item in node.get("record_sources", [])
    )
    mutated = validate_workflow_graph(payload)
    mutated.nodes[1].record_sources[0].__dict__["slot_id"] = "hidden"
    with pytest.raises(ValueError):
        workflow_revision_digest(mutated)
