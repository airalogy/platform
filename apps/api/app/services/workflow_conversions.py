"""Explicit legacy structure copies; never reinterpret prose or migrate runs."""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy import select

from app.models.lab import Lab
from app.models.protocol import Protocol, ProtocolKind
from app.models.protocol_version import ProtocolVersion
from app.models.workflow import ProtocolWorkflow
from app.services.research_runtime import canonical_digest
from app.services.workflow_contracts import (
    MAX_WORKFLOW_EDGES,
    MAX_WORKFLOW_NODES,
    WorkflowGraph,
)
from app.services.workflow_definitions import (
    WorkflowDraft,
    preview_draft,
    require_protocol_read,
    scope,
)

PROTOCOL_REFERENCE = re.compile(
    r"^airalogy\.id\.lab\.([A-Za-z0-9_-]+)\.project\.([A-Za-z0-9_-]+)\.protocol\.([A-Za-z0-9_-]+)\.v\.(\d+\.\d+\.\d+)$"
)
EDGE_REFERENCE = re.compile(r"^\s*(\d+)\s*(->|<->)\s*(\d+)\s*$")
OMITTED_FIELDS = [
    "logic",
    "default_initial_protocol_index",
    "default_research_goal",
    "default_research_strategy",
    "path_data",
    "records",
    "conclusions",
    "initial_values",
]


class LegacyProtocolSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_index: int = Field(ge=1, strict=True)
    protocol_id: UUID
    protocol_version_id: UUID


class LegacyControlEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_protocol_index: int = Field(ge=1, strict=True)
    target_protocol_index: int = Field(ge=1, strict=True)


class LegacyConversionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=20000)
    nodes: list[LegacyProtocolSelection] = Field(
        min_length=1, max_length=MAX_WORKFLOW_NODES
    )
    edges: list[LegacyControlEdge] = Field(
        default_factory=list, max_length=MAX_WORKFLOW_EDGES
    )
    acknowledge_versions: StrictBool
    acknowledge_structure_only: StrictBool
    acknowledge_logic_omission: StrictBool

    @model_validator(mode="after")
    def validate_choices(self):
        self.title = self.title.strip()
        self.description = self.description.strip()
        if not self.title:
            raise ValueError("The new Workflow title is required")
        if not all(
            (
                self.acknowledge_versions,
                self.acknowledge_structure_only,
                self.acknowledge_logic_omission,
            )
        ):
            raise ValueError(
                "Confirm the exact versions, Project structure publication and omission of legacy execution logic"
            )
        indexes = [node.protocol_index for node in self.nodes]
        if len(indexes) != len(set(indexes)):
            raise ValueError(
                "Each legacy Protocol occurrence must be selected exactly once"
            )
        return self


class LegacyConversionConfirm(LegacyConversionDraft):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: UUID


def source_digest(workflow):
    # Include the current private execution path only in the digest, never in
    # the new Project asset. Continuing the old run invalidates an unused preview.
    return canonical_digest(
        jsonable_encoder(
            {
                "id": workflow.id,
                "project_id": workflow.project_id,
                "user_id": workflow.user_id,
                "root_protocol_id": workflow.root_protocol_id,
                "title": workflow.title,
                "workflow_info": workflow.workflow_info,
                "path_data": workflow.path_data,
                "updated_at": workflow.updated_at,
                "deleted_at": workflow.deleted_at,
            }
        )
    )


def legacy_nodes(info):
    nodes = info.get("protocols") if isinstance(info, dict) else None
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_WORKFLOW_NODES:
        raise ValueError(
            "Legacy Workflow must have between 1 and 64 Protocol occurrences"
        )
    indexes = []
    for node in nodes:
        if (
            not isinstance(node, dict)
            or type(node.get("protocol_index")) is not int
            or node["protocol_index"] < 1
        ):
            raise ValueError("Legacy Workflow has an invalid Protocol occurrence index")
        if (
            not isinstance(node.get("airalogy_protocol_id"), str)
            or not node["airalogy_protocol_id"].strip()
        ):
            raise ValueError("Legacy Workflow has a missing Protocol reference")
        indexes.append(node["protocol_index"])
    if len(indexes) != len(set(indexes)):
        raise ValueError("Legacy Workflow has duplicate Protocol occurrence indexes")
    return sorted(nodes, key=lambda node: node["protocol_index"])


def legacy_edges(info, indexes):
    edges = info.get("edges", [])
    if not isinstance(edges, list) or len(edges) > MAX_WORKFLOW_EDGES:
        raise ValueError("Legacy Workflow edge list exceeds the supported bound")
    result = []
    for index, raw in enumerate(edges):
        match = EDGE_REFERENCE.fullmatch(raw) if isinstance(raw, str) else None
        source, target = (int(match[1]), int(match[3])) if match else (None, None)
        supported = bool(
            match
            and match[2] == "->"
            and source in indexes
            and target in indexes
            and source != target
        )
        result.append(
            {
                "edge_id": f"legacy_edge_{index + 1}",
                "text": raw if isinstance(raw, str) else str(raw),
                "source_protocol_index": source,
                "target_protocol_index": target,
                "supported": supported,
            }
        )
    return result


def build_conversion_graph(draft, context_nodes):
    expected = {node["protocol_index"]: node for node in context_nodes}
    selected = {node.protocol_index: node for node in draft.nodes}
    if set(expected) != set(selected):
        raise ValueError(
            "Select an exact version for every original Protocol occurrence"
        )
    nodes = []
    for index, original in sorted(expected.items()):
        choice = selected[index]
        if not original["protocol_id"] or str(choice.protocol_id) != str(
            original["protocol_id"]
        ):
            raise ValueError(
                "Conversion cannot substitute a different Protocol for an original occurrence"
            )
        if str(choice.protocol_version_id) not in {
            str(version["id"]) for version in original["versions"]
        }:
            raise ValueError(
                "Select an available exact Protocol version; latest is not implicit"
            )
        nodes.append(
            {
                "node_id": f"legacy_{index}",
                "kind": "protocol",
                "title": original["name"][:255],
                "protocol_id": choice.protocol_id,
                "protocol_version_id": choice.protocol_version_id,
                "position": {
                    "x": float((len(nodes) % 4) * 300),
                    "y": float((len(nodes) // 4) * 180),
                },
            }
        )
    return WorkflowGraph.model_validate(
        {
            "schema_version": 1,
            "nodes": nodes,
            "bindings": [],
            "edges": [
                {
                    "edge_id": f"legacy_{edge.source_protocol_index}_to_{edge.target_protocol_index}",
                    "source_node_id": f"legacy_{edge.source_protocol_index}",
                    "target_node_id": f"legacy_{edge.target_protocol_index}",
                }
                for edge in draft.edges
            ],
        }
    )


async def legacy_source(
    db, user, legacy_id, *, project_id=None, lock=False, write=False
):
    statement = select(ProtocolWorkflow).where(
        ProtocolWorkflow.id == legacy_id,
        ProtocolWorkflow.user_id == user.id,
        ProtocolWorkflow.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    workflow = await db.scalar(statement)
    if workflow is None or (
        project_id is not None and workflow.project_id != project_id
    ):
        raise HTTPException(404, "Legacy Workflow not found")
    project = await scope(
        db, user, workflow.project_id, "research.create" if write else "research.read"
    )
    return workflow, project


async def _protocol_context(db, user, project, node):
    reference = node["airalogy_protocol_id"].strip()
    match = PROTOCOL_REFERENCE.fullmatch(reference)
    protocol = None
    original_version = None
    if match:
        lab_uid, project_uid, protocol_uid, original_version = match.groups()
        lab = await db.get(Lab, project.lab_id)
        if lab is not None and lab.uid == lab_uid and project.uid == project_uid:
            protocol = await db.scalar(
                select(Protocol).where(
                    Protocol.project_id == project.id, Protocol.uid == protocol_uid
                )
            )
    else:
        try:
            protocol_id = UUID(reference)
        except ValueError:
            protocol = await db.scalar(
                select(Protocol).where(
                    Protocol.project_id == project.id, Protocol.uid == reference
                )
            )
        else:
            protocol = await db.get(Protocol, protocol_id)
    result = {
        "protocol_index": node["protocol_index"],
        "node_id": f"legacy_{node['protocol_index']}",
        "name": str(node.get("protocol_name") or f"Protocol {node['protocol_index']}"),
        "protocol_id": None,
        "original_reference": reference,
        "suggested_version_id": None,
        "versions": [],
    }
    if (
        protocol is None
        or protocol.project_id != project.id
        or protocol.deleted_at is not None
        or protocol.kind != ProtocolKind.EXPERIMENT
    ):
        return result
    try:
        await require_protocol_read(db, user, project, protocol)
    except HTTPException as exc:
        if exc.status_code not in {403, 404}:
            raise
        return result
    versions = list(
        (
            await db.scalars(
                select(ProtocolVersion)
                .where(ProtocolVersion.protocol_id == protocol.id)
                .order_by(ProtocolVersion.created_at.desc(), ProtocolVersion.id)
            )
        ).all()
    )
    result.update(
        {
            "protocol_id": protocol.id,
            "name": str(node.get("protocol_name") or protocol.name),
            "versions": [
                {"id": version.id, "version": version.version} for version in versions
            ],
            "suggested_version_id": next(
                (
                    version.id
                    for version in versions
                    if version.version == original_version
                ),
                None,
            ),
        }
    )
    return result


async def conversion_context(db, user, workflow, project):
    try:
        stored_nodes = legacy_nodes(workflow.workflow_info)
        edges = legacy_edges(
            workflow.workflow_info, {node["protocol_index"] for node in stored_nodes}
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    nodes = [await _protocol_context(db, user, project, node) for node in stored_nodes]
    logic = workflow.workflow_info.get("logic") or ""
    logic_text = (
        "\n".join(str(value) for value in logic)
        if isinstance(logic, list)
        else str(logic)
    )
    warnings = [
        {
            "code": "structure_only",
            "message": "Create a new Project-visible structure, without executing it or changing the private legacy Workflow.",
        },
        {
            "code": "legacy_logic_not_executable",
            "message": "Legacy prose, goals and strategy are not converted into executable conditions. Selected edges are unconditional dependencies.",
        },
        {
            "code": "execution_history_not_copied",
            "message": "Existing Records, progress, initial values and conclusions remain in the old Workflow and are not copied or marked complete.",
        },
        {
            "code": "legacy_start_not_preserved",
            "message": "The old initial-Protocol choice is not a scheduling constraint. The new graph starts at every root confirmed in this preview.",
        },
    ]
    if any(not edge["supported"] for edge in edges):
        warnings.append(
            {
                "code": "legacy_edges_need_review",
                "message": "Bidirectional, self-referencing or unrecognized edges require an explicit new direction or omission; no direction is inferred.",
            }
        )
    if any(node["suggested_version_id"] is None for node in nodes):
        warnings.append(
            {
                "code": "exact_version_required",
                "message": "Some original references do not resolve to an exact available version. Select versions explicitly; latest is never substituted.",
            }
        )
    blockers = [
        {
            "code": "protocol_unavailable",
            "protocol_index": node["protocol_index"],
            "message": "The original Protocol is not accessible in this Project or has no available version.",
        }
        for node in nodes
        if not node["protocol_id"] or not node["versions"]
    ]
    return {
        "source": {
            "id": workflow.id,
            "project_id": workflow.project_id,
            "title": workflow.title,
            "digest": source_digest(workflow),
            "path_status": (workflow.path_data or {}).get("path_status"),
        },
        "nodes": nodes,
        "edges": edges,
        "logic_text": logic_text,
        "warnings": warnings,
        "blockers": blockers,
        "omitted_fields": OMITTED_FIELDS,
    }


async def preview_conversion(db, user, legacy_id, draft, *, lock=False):
    workflow, project = await legacy_source(
        db, user, legacy_id, project_id=draft.project_id, lock=lock, write=True
    )
    context = await conversion_context(db, user, workflow, project)
    if context["source"]["digest"] != draft.source_digest:
        raise HTTPException(
            409, "Legacy Workflow changed; reload its context and preview again"
        )
    if context["blockers"]:
        raise HTTPException(
            422,
            {
                "message": "Legacy Workflow contains unavailable Protocols",
                "blockers": context["blockers"],
            },
        )
    try:
        graph = build_conversion_graph(draft, context["nodes"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    preview, _, _ = await preview_draft(
        db,
        user,
        WorkflowDraft(
            project_id=project.id,
            title=draft.title,
            description=draft.description,
            graph=graph,
        ),
    )
    selected = {
        (edge.source_protocol_index, edge.target_protocol_index) for edge in draft.edges
    }
    originals = {
        (edge["source_protocol_index"], edge["target_protocol_index"])
        for edge in context["edges"]
        if edge["supported"]
    }
    warnings = list(context["warnings"])
    if selected != originals:
        warnings.append(
            {
                "code": "dependencies_changed",
                "message": "The selected unconditional dependencies differ from the original directed edges. Confirm this newly designed structure explicitly.",
            }
        )
    content = {
        key: preview[key]
        for key in ("project_id", "title", "description", "graph", "pins")
    }
    request = draft.model_dump(
        mode="json", exclude={"preview_digest", "idempotency_key"}
    )
    return (
        {
            **content,
            "source": context["source"],
            "warnings": warnings,
            "omitted_fields": OMITTED_FIELDS,
            "preview_digest": canonical_digest(
                {
                    "user_id": str(user.id),
                    "legacy_id": str(legacy_id),
                    "request": request,
                    "content": content,
                }
            ),
        },
        workflow,
        project,
    )
