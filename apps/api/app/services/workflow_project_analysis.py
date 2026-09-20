"""Project input-slot adaptation to the existing Workflow analysis lifecycle.

No scheduler, inferred sample selection or private method authority is introduced.
Published Schema contracts and exact upstream occurrences define all inputs.
"""

from uuid import UUID

from fastapi import HTTPException

from app.services.project_analyses import (
    PROJECT_SNAPSHOT_SCHEMA,
    ProjectAnalysisSelection,
    capture_project_sources,
    project_preview_summary,
)
from app.services.project_analysis_engine import ProjectAnalysisRecipe


def analysis_source_snapshots(snapshot):
    """Enumerate only validated source envelopes; never quietly omit a slot."""
    try:
        if not isinstance(snapshot, dict):
            raise TypeError()
        if snapshot.get("schema") == PROJECT_SNAPSHOT_SCHEMA:
            UUID(snapshot["project_id"])
            inputs = snapshot["inputs"]
            if not isinstance(inputs, list) or not 2 <= len(inputs) <= 8:
                raise ValueError()
            if len({item["slot_id"] for item in inputs}) != len(inputs):
                raise ValueError()
            sources = [item["snapshot"] for item in inputs]
            if len({item["protocol_id"] for item in sources}) != len(sources):
                raise ValueError()
        elif "inputs" not in snapshot and "schema" not in snapshot:
            sources = [snapshot]
        else:
            raise ValueError()
        for source in sources:
            UUID(source["protocol_id"])
            if not isinstance(source["records"], list) or not source["records"]:
                raise ValueError()
        return sources
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(409, "Workflow analysis source envelope changed") from exc


def project_selection_from_snapshot(snapshot):
    analysis_source_snapshots(snapshot)
    if snapshot.get("schema") != PROJECT_SNAPSHOT_SCHEMA:
        raise HTTPException(409, "Expected a Project analysis source envelope")
    return ProjectAnalysisSelection.model_validate(
        {
            "inputs": [
                {
                    "slot_id": item["slot_id"],
                    "protocol_id": item["snapshot"]["protocol_id"],
                    "selection": {
                        "mode": "selected",
                        "records": [
                            {"id": row["record_id"], "version": row["record_version"]}
                            for row in item["snapshot"]["records"]
                        ],
                    },
                }
                for item in snapshot["inputs"]
            ]
        }
    )


def validate_project_node_inputs(method, node, versions):
    from app.services.workflow_analysis_contracts import validate_project_method_inputs

    if node.analysis_kind != "project" or not getattr(method, "project_contract", None):
        raise ValueError("A Project method requires an explicit Project analysis card")
    slots = {slot["slot_id"]: [] for slot in method.project_contract["slots"]}
    seen = set()
    for source in node.record_sources:
        if source.slot_id not in slots or source.source_node_id in seen:
            raise ValueError(
                "Project analysis inputs must map each declared source once"
            )
        version = versions.get(source.source_node_id)
        if version is None:
            raise ValueError("Project analysis input version is unavailable")
        seen.add(source.source_node_id)
        slots[source.slot_id].append(version)
    return validate_project_method_inputs(method.recipe, method.project_contract, slots)


async def capture_project_node_inputs(
    db, *, task, method, node, graph, parents_by_node, user
):
    from app.models.protocol_version import ProtocolVersion

    graph_nodes = {item.node_id: item for item in graph.nodes}
    versions = {
        source.source_node_id: await db.get(
            ProtocolVersion,
            graph_nodes[source.source_node_id].protocol_version_id,
            populate_existing=True,
        )
        for source in node.record_sources
    }
    validate_project_node_inputs(method, node, versions)
    by_slot = {slot["slot_id"]: [] for slot in method.project_contract["slots"]}
    receipts, seen = [], set()
    for binding in sorted(
        node.record_sources, key=lambda item: (item.slot_id, item.source_node_id)
    ):
        parent = parents_by_node[binding.source_node_id]
        source = graph_nodes[binding.source_node_id]
        version = versions[binding.source_node_id]
        if parent.kind != "protocol_run" or parent.status != "completed":
            raise ValueError(
                "Every Project analysis source must be a completed Protocol occurrence"
            )
        payload = (parent.output_data or {}).get("record") or {}
        record_id = str(UUID(payload["record_id"]))
        if record_id in seen:
            raise ValueError(
                "The same Record cannot be counted as multiple Workflow samples"
            )
        seen.add(record_id)
        by_slot[binding.slot_id].append(
            {"id": record_id, "version": payload["record_version"]}
        )
        receipts.append(
            {
                "slot_id": binding.slot_id,
                "source_node_id": binding.source_node_id,
                "protocol_id": str(source.protocol_id),
                "protocol_version_id": str(version.id),
                "record_id": record_id,
                "record_version": payload["record_version"],
            }
        )
    selection = ProjectAnalysisSelection.model_validate(
        {
            "inputs": [
                {
                    "slot_id": slot["slot_id"],
                    "protocol_id": slot["protocol_id"],
                    "selection": {
                        "mode": "selected",
                        "records": by_slot[slot["slot_id"]],
                    },
                }
                for slot in method.project_contract["slots"]
            ],
        }
    )
    snapshot, project = await capture_project_sources(
        db, project_id=task.project_id, selection=selection, user=user
    )
    actual = {
        (item["slot_id"], row["record_id"]): row
        for item in snapshot["inputs"]
        for row in item["snapshot"]["records"]
    }
    for receipt in receipts:
        row = actual[(receipt["slot_id"], receipt["record_id"])]
        version = versions[receipt["source_node_id"]]
        if (
            row["record_version"] != receipt["record_version"]
            or row["protocol_version"] != version.version
        ):
            raise HTTPException(
                409, "Workflow source Record does not use its pinned Protocol version"
            )
    summary = project_preview_summary(
        project, ProjectAnalysisRecipe.model_validate(method.recipe), snapshot
    )
    return selection, snapshot, summary, receipts
