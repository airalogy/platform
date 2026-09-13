"""Compute publication and exact Run governance with real migrated PostgreSQL."""

import asyncio
import json
from importlib import import_module
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException, Response
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

from app.models.research_execution import ResearchComputeEnvironmentRevision
from app.models.workflow_analysis import WorkflowAnalysisMethod
from app.routers import analyses, research_tasks
from app.routers import workflow_analysis_methods as methods
from app.routers import workflow_definitions as workflows
from app.services.workflow_analysis_methods import (
    MethodPublicationConfirm,
    MethodPublicationDraft,
)
from app.services.workflow_definitions import WorkflowDraft, WorkflowRunDraft
from tests.test_analysis_compute_runtime_postgres import (
    completion,
    confirmed,
    download_and_start,
    fixture,
    lease,
    submit_completion,
    upload,
)
from tests.test_record_analysis_postgres import database
from tests.test_workflow_definitions_postgres import (
    deterministic_no_ai as deterministic_no_ai,
)
from tests.test_workflow_definitions_postgres import edge, node, publish
from tests.test_workflow_definitions_postgres import pytestmark as pytestmark


async def saved_compute_method(sessions, *, real_engine=False):
    f = await fixture(sessions, real_engine=real_engine)
    # Use the actual private routes as the Project owner. Runner receipts below
    # are synthetic transport fixtures, not evidence of source-code execution.
    f.scope = SimpleNamespace(**{**vars(f.scope), "analyst": f.scope.owner})
    analysis_id = await confirmed(sessions, f)
    delivery = await lease(sessions, f)
    await download_and_start(sessions, f, delivery)
    result = {"mean": 5.0, "count": 4, "uid": 65532}
    payload = json.dumps(result).encode()
    await upload(sessions, f, delivery, payload)
    await submit_completion(
        sessions, f, delivery, completion(delivery, result, payload)
    )
    async with sessions() as db:
        saved = await analyses.create_analysis_pipeline(
            analyses.PipelineCreateRequest(
                run_id=analysis_id, title="Private exact Python method"
            ),
            db,
            f.scope.owner,
        )
    return f, saved, analysis_id


def publication_draft(f, saved, **changes):
    return MethodPublicationDraft(
        project_id=f.scope.project.id,
        pipeline_revision_id=saved["revisions"][0]["id"],
        protocol_version_id=f.scope.version.id,
        title="Shared exact Python method",
        **changes,
    )


async def publish_compute_method(sessions, f, saved, **changes):
    params = publication_draft(f, saved, **changes)
    async with sessions() as db:
        preview = await methods.preview_method(params, f.scope.owner, db, Response())
    command = MethodPublicationConfirm(
        **params.model_dump(),
        preview_digest=preview["preview_digest"],
        idempotency_key=uuid4(),
    )
    async with sessions() as db:
        result = await methods.confirm_method(command, f.scope.owner, db)
    return result, command


def compute_graph(f, method):
    return {
        "schema_version": 3,
        "nodes": [
            node(f.scope, "source"),
            {
                "node_id": "analysis",
                "kind": "analysis",
                "analysis_kind": "compute",
                "method_publication_id": method["id"],
                "record_sources": [{"source_node_id": "source", "cardinality": "one"}],
                "input_policy": "all_declared",
                "compute_outputs": [
                    {
                        "output_id": "mean_value",
                        "path": ["mean"],
                        "value_type": "number",
                        "unit": None,
                        "nullable": False,
                    }
                ],
            },
        ],
        "edges": [edge("source", "analysis")],
        "bindings": [],
    }


async def compute_task(sessions, f, **changes):
    params = research_tasks.ResearchTaskDraft(
        project_id=f.scope.project.id,
        title="Synthetic exact Compute Workflow",
        goal="Execute a reviewed method with attributable evidence",
        success_criteria=["A sealed analysis result"],
        protocol_ids=[f.scope.protocol.id],
        **changes,
    )
    async with sessions() as db:
        preview = await research_tasks.preview_research_task(params, f.scope.owner, db)
        return await research_tasks.create_research_task(
            research_tasks.ResearchTaskCreate(
                **params.model_dump(), preview_digest=preview["preview_digest"]
            ),
            f.scope.owner,
            db,
        )


def test_compute_publication_seals_code_schema_environment_but_not_private_history():
    async def exercise():
        async with database() as sessions:
            f, saved, private_run = await saved_compute_method(sessions)
            published, command = await publish_compute_method(sessions, f, saved)
            contract = published["compute_contract"]
            assert contract["environment"]["source_revision_id"] == str(
                f.compute.revision.id
            )
            assert (
                contract["input_schema_contract"]["json_schema"]
                == f.scope.version.json_schema
            )
            assert published["recipe"] == saved["current_recipe"]
            async with sessions() as db:
                listed = await methods.get_methods(
                    f.scope.project.id, f.scope.recorder, db, Response()
                )
                assert listed["items"] == [published]
                serialized = json.dumps(listed, default=str)
                for private_id in (
                    private_run,
                    saved["id"],
                    saved["revisions"][0]["id"],
                    *(r.id for r in f.records),
                ):
                    assert str(private_id) not in serialized
                assert (
                    "approver_user_id" not in serialized
                    and "max_cost" not in serialized
                )
                assert (
                    await methods.confirm_method(command, f.scope.owner, db)
                    == published
                )
                catalog = await methods.output_catalog(
                    UUID(published["id"]), f.scope.recorder, db, Response()
                )
                assert catalog["kind"] == "compute"
                assert ["mean"] in [item["path"] for item in catalog["fields"]]
            async with sessions() as db:
                with pytest.raises(DBAPIError):
                    await db.execute(
                        update(WorkflowAnalysisMethod)
                        .where(WorkflowAnalysisMethod.id == UUID(published["id"]))
                        .values(compute_contract={})
                    )
                await db.rollback()

    asyncio.run(exercise())


def test_compute_publication_explicit_result_schema_is_previewed_and_sealed():
    async def exercise():
        async with database() as sessions:
            f, saved, _ = await saved_compute_method(sessions)
            schema = {
                "type": "object",
                "properties": {
                    "mean": {"type": "number", "minimum": 0, "unit": "mg/L"}
                },
                "required": ["mean"],
            }
            published, command = await publish_compute_method(
                sessions, f, saved, compute_result_schema=schema
            )
            assert published["compute_contract"]["result_schema"] == schema
            async with sessions() as db:
                changed = command.model_copy(
                    update={"compute_result_schema": {"type": "object"}}
                )
                with pytest.raises(HTTPException) as stale:
                    await methods.confirm_method(changed, f.scope.owner, db)
                assert stale.value.status_code == 409
                params = publication_draft(
                    f,
                    saved,
                    compute_result_schema={"$ref": "https://example.test/result.json"},
                )
                with pytest.raises(HTTPException) as unsafe:
                    await methods.preview_method(params, f.scope.owner, db, Response())
                assert unsafe.value.status_code == 422

    asyncio.run(exercise())


def test_compute_workflow_requires_exact_task_revision_and_fresh_run_governance():
    async def exercise():
        async with database() as sessions:
            f, saved, _ = await saved_compute_method(sessions)
            method, _ = await publish_compute_method(sessions, f, saved)
            workflow, _ = await publish(
                sessions,
                f.scope,
                WorkflowDraft(
                    project_id=f.scope.project.id,
                    title="Compute cards",
                    graph=compute_graph(f, method),
                ),
            )
            missing = await compute_task(sessions, f)
            async with sessions() as db:
                with pytest.raises(HTTPException) as unavailable:
                    await workflows.preview_workflow_run(
                        UUID(str(workflow["id"])),
                        WorkflowRunDraft(
                            workflow_revision_id=workflow["current_revision"]["id"],
                            task_id=missing["id"],
                            expected_task_revision=missing["revision"],
                        ),
                        f.scope.owner,
                        db,
                    )
                assert unavailable.value.status_code == 409
            task = await compute_task(
                sessions,
                f,
                compute_environment_revision_ids=[f.compute.revision.id],
                budget_limit="1.00",
                budget_currency="USD",
            )
            params = WorkflowRunDraft(
                workflow_revision_id=workflow["current_revision"]["id"],
                task_id=task["id"],
                expected_task_revision=task["revision"],
            )
            async with sessions() as db:
                preview = await workflows.preview_workflow_run(
                    UUID(str(workflow["id"])), params, f.scope.owner, db
                )
                assert preview["execution_contract_version"] == 4
                assert preview["compute_governance"]["analysis"] == {
                    "approver_user_id": str(f.scope.owner.id),
                    "max_cost": "1",
                    "budget_currency": "USD",
                    "deadline_at": None,
                }
                with pytest.raises(HTTPException) as invalid:
                    await workflows.preview_workflow_run(
                        UUID(str(workflow["id"])),
                        params.model_copy(
                            update={"compute_approvers": {"source": f.scope.owner.id}}
                        ),
                        f.scope.owner,
                        db,
                    )
                assert invalid.value.status_code == 422

    asyncio.run(exercise())


def test_compute_publication_downgrade_refuses_published_contracts():
    async def exercise():
        async with database() as sessions:
            f, saved, _ = await saved_compute_method(sessions)
            await publish_compute_method(sessions, f, saved)
            migration = import_module(
                "migrations.versions.0066_workflow_compute_methods"
            )
            async with sessions() as db:
                connection = await db.connection()

                def downgrade(sync_connection):
                    context = MigrationContext.configure(sync_connection)
                    with Operations.context(context):
                        migration.downgrade()

                with pytest.raises(RuntimeError, match="Cannot downgrade"):
                    await connection.run_sync(downgrade)
                await db.rollback()
                assert await db.scalar(select(WorkflowAnalysisMethod.id).limit(1))

    asyncio.run(exercise())


def test_disabled_compute_revision_is_isolated_without_disclosing_its_shared_code():
    async def exercise():
        async with database() as sessions:
            f, saved, _ = await saved_compute_method(sessions)
            published, _ = await publish_compute_method(sessions, f, saved)
            async with sessions() as db:
                revision = await db.get(
                    ResearchComputeEnvironmentRevision, f.compute.revision.id
                )
                revision.enabled = False
                await db.commit()
            async with sessions() as db:
                listing = await methods.get_methods(
                    f.scope.project.id, f.scope.recorder, db, Response()
                )
                assert listing == {
                    "items": [],
                    "unavailable": [
                        {"id": published["id"], "code": "method_unavailable"}
                    ],
                }

    asyncio.run(exercise())
