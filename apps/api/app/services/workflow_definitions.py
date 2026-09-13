"""Authorization and sealing for Project Workflow assets; no model calls."""

from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text

from app.models.project import Project
from app.models.protocol import Protocol, ProtocolKind
from app.models.protocol_version import ProtocolVersion
from app.models.workflow_definition import WorkflowDefinition, WorkflowRevision
from app.routers.permission import check_user_permission
from app.services.research_runtime import (
    canonical_digest,
    has_research_capability,
    require_research_capability,
)
from app.services.workflow_contracts import WorkflowGraph, validate_workflow_graph
from app.services.workflow_data import (
    protocol_field_catalog,
    validate_protocol_initial_values,
    validate_workflow_data,
)


class WorkflowDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID
    definition_id: UUID | None = None
    expected_revision: int | None = Field(default=None, ge=1, strict=True)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=20000)
    graph: WorkflowGraph

    @model_validator(mode="after")
    def normalize(self):
        self.title = self.title.strip()
        self.description = self.description.strip()
        if not self.title:
            raise ValueError("Workflow title is required")
        if (self.definition_id is None) != (self.expected_revision is None):
            raise ValueError(
                "A revision requires both definition_id and expected_revision"
            )
        return self


class WorkflowConfirm(WorkflowDraft):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: UUID


class WorkflowRunDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_revision_id: UUID
    task_id: UUID
    expected_task_revision: int = Field(ge=1, strict=True)
    compute_approvers: dict[str, UUID] = Field(default_factory=dict, max_length=64)


class WorkflowRunConfirm(WorkflowRunDraft):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: UUID


async def scope(db, user, project_id, capability="research.read"):
    project = await db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(404, "Project not found")
    await require_research_capability(
        db, user=user, project=project, capability=capability
    )
    return project


async def require_protocol_read(db, user, project, protocol):
    try:
        await check_user_permission(
            db, project=project, user=user, action="read_protocol", protocol=protocol
        )
    except HTTPException as exc:
        # The legacy permission adapter uses HTTP 400 for an authorization denial.
        # Normalize only that exact denial, so scoped catalogs can omit it safely.
        if exc.status_code == 400 and exc.detail == "Permission denied":
            raise HTTPException(403, "Protocol access denied") from exc
        raise


async def capabilities(db, user, project):
    return {
        key: await has_research_capability(
            db, user=user, project=project, capability=value
        )
        for key, value in {
            "read": "research.read",
            "write": "research.create",
            "run": "research.run",
        }.items()
    }


async def request_lock(db, user_id, key):
    # Serialize retries before checking idempotency, including the first insert.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"workflow:{user_id}:{key}"},
    )


def validate_initial_values(version, values, *, allow_files=False):
    if not allow_files and values:
        catalog = protocol_field_catalog(version, include_files=True)
        if any(
            (
                catalog.get(("var", key)) is not None
                and catalog[("var", key)].value_type == "file"
            )
            or isinstance(value, str)
            and value.strip().startswith("airalogy.id.file.")
            for key, value in values.items()
        ):
            raise ValueError(
                "Workflow files require an authorized upstream binding, not static initial values"
            )
    validate_protocol_initial_values(version, values)


async def resolve_pins(db, user, project, graph):
    graph = validate_workflow_graph(graph)
    pins = []
    catalogs = {}
    target_catalogs = {}
    versions = {}
    for node in graph.nodes:
        if node.kind != "protocol":
            continue
        protocol = await db.get(Protocol, node.protocol_id)
        version = await db.get(ProtocolVersion, node.protocol_version_id)
        if (
            protocol is None
            or protocol.project_id != project.id
            or protocol.deleted_at is not None
            or protocol.kind != ProtocolKind.EXPERIMENT
            or version is None
            or version.protocol_id != protocol.id
        ):
            raise HTTPException(
                404, "Pinned Protocol version is not available in this Project"
            )
        await require_protocol_read(db, user, project, protocol)
        versions[node.node_id] = version
        catalogs[node.node_id] = protocol_field_catalog(
            version, include_files=graph.schema_version >= 4
        )
        if any(binding.target_node_id == node.node_id for binding in graph.bindings):
            target_catalogs[node.node_id] = protocol_field_catalog(
                version, for_target=True, include_files=graph.schema_version >= 4
            )
        try:
            validate_initial_values(version, node.initial_values)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        pins.append(
            {
                "node_id": node.node_id,
                "protocol_id": str(protocol.id),
                "protocol_version_id": str(version.id),
                "version": version.version,
                "name": protocol.name,
                "content_digest": canonical_digest(
                    {
                        "aimd": version.aimd,
                        "schema": version.json_schema,
                        "fields": version.fields,
                        "assigners": version.assigners,
                        "assigner_graph": version.assigner_graph,
                        "metadata": version.meta_data,
                    }
                ),
            }
        )
    for node in graph.nodes:
        if node.kind != "analysis":
            continue
        if graph.schema_version not in {2, 3, 4} or not node.method_publication_id:
            raise HTTPException(
                422,
                "Analysis cards require an explicitly published Project method and a version 2, 3 or 4 graph",
            )
        from app.services.analysis_engine import AnalysisRecipe, validate_recipe
        from app.services.workflow_analysis_contracts import (
            analysis_output_catalog,
            validate_analysis_method_inputs,
        )
        from app.services.workflow_analysis_methods import get_method

        method = await get_method(db, user, node.method_publication_id, project)
        source_versions = [
            versions[source.source_node_id] for source in node.record_sources
        ]
        if any(
            version.protocol_id != method.protocol_id for version in source_versions
        ):
            raise HTTPException(
                422,
                "This saved method requires explicitly selected Records from its Protocol; cross-Protocol analysis needs a separate mapping",
            )
        try:
            if method.compute_contract:
                from app.services.workflow_compute_contracts import (
                    compute_output_catalog,
                    validate_compute_method_inputs,
                )

                if (
                    graph.schema_version not in {3, 4}
                    or node.analysis_kind != "compute"
                ):
                    raise ValueError(
                        "Compute methods require a version 3 or 4 Compute analysis card"
                    )
                validate_compute_method_inputs(
                    method.compute_contract["input_schema_contract"], source_versions
                )
                catalogs[node.node_id] = compute_output_catalog(
                    method.compute_contract["result_schema"], node.compute_outputs
                )
                if graph.schema_version >= 4:
                    from app.services.workflow_file_contracts import (
                        compute_file_output_catalog,
                    )

                    catalogs[node.node_id].update(
                        compute_file_output_catalog(
                            method.recipe, node.compute_file_outputs
                        )
                    )
            else:
                if node.analysis_kind == "compute":
                    raise ValueError("A Compute card cannot use a builtin method")
                fields = validate_analysis_method_inputs(method.recipe, source_versions)
                # Publication fixes meaning and units, not only field names.
                validate_recipe(
                    AnalysisRecipe.model_validate(method.recipe),
                    [*method.input_fields, *fields],
                )
                catalogs[node.node_id] = analysis_output_catalog(
                    method.recipe, method.input_fields, node.analysis_outputs
                )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        pins.append(
            {
                "node_id": node.node_id,
                "kind": "analysis",
                "method_publication_id": str(method.id),
                "protocol_id": str(method.protocol_id),
                "protocol_version_id": str(method.protocol_version_id),
                "engine_version": method.engine_version,
                "name": method.title,
                "content_digest": method.digest,
            }
        )
    try:
        validate_workflow_data(graph, catalogs)
        if any(
            tuple(binding.target_path)
            not in target_catalogs.get(binding.target_node_id, {})
            for binding in graph.bindings
        ):
            raise ValueError("Workflow binding target Schema is not safely supported")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    by_node = {pin["node_id"]: pin for pin in pins}
    return [by_node[node.node_id] for node in graph.nodes]


async def definition(db, user, definition_id, *, write=False, lock=False):
    statement = select(WorkflowDefinition).where(WorkflowDefinition.id == definition_id)
    if lock:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    item = (await db.scalars(statement)).first()
    if item is None:
        raise HTTPException(404, "Workflow not found")
    project = await scope(
        db, user, item.project_id, "research.create" if write else "research.read"
    )
    return item, project


def revision_content(revision):
    return {
        "title": revision.title,
        "description": revision.description,
        "graph": revision.graph,
        "pins": revision.pins,
    }


def verify_revision(revision):
    if canonical_digest(revision_content(revision)) != revision.digest:
        raise HTTPException(409, "Workflow revision integrity check failed")
    return validate_workflow_graph(revision.graph)


async def revision_payload(db, user, project, revision):
    graph = verify_revision(revision)
    # Version-pinned assets remain permission-checked on every read.
    await resolve_pins(db, user, project, graph)
    return revision.as_dict(excludes=["request_digest", "idempotency_key"])


async def definition_payload(db, user, item, project, *, history=False):
    revisions = list(
        (
            await db.scalars(
                select(WorkflowRevision)
                .where(WorkflowRevision.definition_id == item.id)
                .order_by(WorkflowRevision.revision.desc())
            )
        ).all()
    )
    selected = revisions if history else revisions[:1]
    payloads = [
        await revision_payload(db, user, project, revision) for revision in selected
    ]
    return {
        **item.as_dict(),
        "current_revision": payloads[0] if payloads else None,
        **({"revisions": payloads} if history else {}),
    }


async def preview_draft(db, user, draft, *, lock=False):
    project = await scope(db, user, draft.project_id, "research.create")
    item = None
    if draft.definition_id is not None:
        item, _ = await definition(db, user, draft.definition_id, write=True, lock=lock)
        if item.project_id != project.id:
            raise HTTPException(404, "Workflow not found in this Project")
        if item.revision != draft.expected_revision:
            raise HTTPException(
                409, "Workflow changed; reload before publishing a revision"
            )
    graph = validate_workflow_graph(draft.graph)
    pins = await resolve_pins(db, user, project, graph)
    content = {
        "title": draft.title,
        "description": draft.description,
        "graph": graph.model_dump(mode="json"),
        "pins": pins,
    }
    command = {
        "project_id": str(project.id),
        "definition_id": str(item.id) if item else None,
        "expected_revision": draft.expected_revision,
        **content,
    }
    return (
        {
            **command,
            "preview_digest": canonical_digest({"user_id": str(user.id), **command}),
            "warnings": [],
        },
        item,
        project,
    )
