"""Pure, AI-independent legacy conversion decisions and bounded graph contracts."""

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.services.workflow_conversions import (
    LegacyConversionDraft,
    build_conversion_graph,
    legacy_edges,
    legacy_nodes,
    source_digest,
)


def selection_context():
    protocol_id, version_id = uuid4(), uuid4()
    return [
        {
            "protocol_index": index,
            "protocol_id": protocol_id,
            "name": f"Repeat {index}",
            "versions": [{"id": version_id, "version": "1.0.0"}],
        }
        for index in (1, 2)
    ]


def draft(context, **changes):
    return LegacyConversionDraft(
        project_id=uuid4(),
        source_digest="1" * 64,
        title="Explicit structure copy",
        nodes=[
            {
                "protocol_index": item["protocol_index"],
                "protocol_id": item["protocol_id"],
                "protocol_version_id": item["versions"][0]["id"],
            }
            for item in context
        ],
        acknowledge_versions=True,
        acknowledge_structure_only=True,
        acknowledge_logic_omission=True,
        **changes,
    )


def test_repeated_protocol_occurrences_remain_distinct_and_versions_are_explicit():
    context = selection_context()
    graph = build_conversion_graph(draft(context), context)
    assert [node.node_id for node in graph.nodes] == ["legacy_1", "legacy_2"]
    assert graph.nodes[0].protocol_id == graph.nodes[1].protocol_id
    assert all(
        node.protocol_version_id == context[0]["versions"][0]["id"]
        for node in graph.nodes
    )
    assert graph.edges == []
    assert graph.bindings == []
    assert all(node.initial_values == {} for node in graph.nodes)


def test_only_user_selected_edges_become_unconditional_dependencies():
    context = selection_context()
    selected = draft(
        context, edges=[{"source_protocol_index": 2, "target_protocol_index": 1}]
    )
    graph = build_conversion_graph(selected, context)
    assert len(graph.edges) == 1
    assert graph.edges[0].source_node_id == "legacy_2"
    assert graph.edges[0].condition is None


@pytest.mark.parametrize(
    "edges",
    [
        [(1, 2), (2, 1)],
        [(1, 1)],
        [(1, 2), (1, 2)],
        [(1, 3)],
    ],
)
def test_cycles_self_edges_duplicate_edges_and_missing_nodes_are_rejected(edges):
    context = selection_context()
    command = draft(
        context,
        edges=[
            {"source_protocol_index": source, "target_protocol_index": target}
            for source, target in edges
        ],
    )
    with pytest.raises(ValueError):
        build_conversion_graph(command, context)


@pytest.mark.parametrize(
    "field,value",
    [
        ("acknowledge_versions", False),
        ("acknowledge_structure_only", False),
        ("acknowledge_logic_omission", False),
        ("acknowledge_versions", 1),
        ("acknowledge_versions", "true"),
    ],
)
def test_all_explicit_acknowledgements_are_strict(field, value):
    context = selection_context()
    data = draft(context).model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        LegacyConversionDraft.model_validate(data)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "substitute", "version"])
def test_no_occurrence_or_exact_version_can_be_silently_replaced(mutation):
    context = selection_context()
    data = draft(context).model_dump()
    if mutation == "missing":
        data["nodes"].pop()
    elif mutation == "duplicate":
        data["nodes"][1] = data["nodes"][0]
    elif mutation == "substitute":
        data["nodes"][0]["protocol_id"] = uuid4()
    else:
        data["nodes"][0]["protocol_version_id"] = uuid4()
    with pytest.raises(ValueError):
        build_conversion_graph(LegacyConversionDraft.model_validate(data), context)


def test_legacy_edges_are_described_not_interpreted_as_code_or_direction_choices():
    raw = {
        "edges": [
            "1 -> 2",
            "2 <-> 3",
            "if x > 3 then 1 -> 2",
            "1 -> 1",
            "1 -> 9",
            "2->3",
        ]
    }
    saved = deepcopy(raw)
    values = legacy_edges(raw, {1, 2, 3})
    assert [entry["supported"] for entry in values] == [
        True,
        False,
        False,
        False,
        False,
        True,
    ]
    assert values[1]["text"] == "2 <-> 3"
    assert values[2]["source_protocol_index"] is None
    assert raw == saved


@pytest.mark.parametrize(
    "protocols",
    [
        [],
        [{"protocol_index": True, "airalogy_protocol_id": "x"}],
        [{"protocol_index": 0, "airalogy_protocol_id": "x"}],
        [{"protocol_index": 1, "airalogy_protocol_id": ""}],
        [{"protocol_index": 1, "airalogy_protocol_id": "x"}] * 2,
    ],
)
def test_invalid_legacy_identity_is_not_repaired_or_guessed(protocols):
    with pytest.raises(ValueError):
        legacy_nodes({"protocols": protocols})


def test_private_source_digest_covers_progress_without_mutating_or_exporting_it():
    source = SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        user_id=uuid4(),
        root_protocol_id=uuid4(),
        title="Private legacy run",
        workflow_info={"logic": "private prose"},
        path_data={"steps": [{"record": "private record"}]},
        updated_at=datetime(2026, 1, 1),
        deleted_at=None,
    )
    original = deepcopy(source.__dict__)
    digest = source_digest(source)
    assert len(digest) == 64
    assert source.__dict__ == original
    source.path_data["steps"].append({"new": "progress"})
    assert source_digest(source) != digest


def test_unknown_legacy_logic_cannot_be_passed_as_executable_conversion_fields():
    context = selection_context()
    data = draft(context).model_dump()
    data["logic"] = "Run arbitrary code and choose the next experiment"
    with pytest.raises(ValidationError):
        LegacyConversionDraft.model_validate(data)
