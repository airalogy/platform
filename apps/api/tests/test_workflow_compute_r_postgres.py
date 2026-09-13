"""R Workflow transport, with separately opted-in actual R interpreter execution."""

import asyncio
import json
import os
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import Response

from app.models.analysis import AnalysisRun
from app.models.research import ResearchTask
from app.models.research_execution import ResearchComputeEnvironmentRevision
from app.routers import analyses, analysis_compute
from app.services.analysis_compute_contracts import AnalysisComputeDraft
from app.services.workflow_definitions import WorkflowDraft
from tests.test_analysis_compute_runtime_postgres import (
    completion,
    download_and_start,
    execute_container,
    fixture,
    lease,
    submit_completion,
    upload,
)
from tests.test_record_analysis_compute_postgres import compute_draft, decision_params
from tests.test_record_analysis_postgres import add_record, database
from tests.test_workflow_compute_methods_postgres import (
    compute_graph,
    compute_task,
    publish_compute_method,
)
from tests.test_workflow_compute_runtime_postgres import queued
from tests.test_workflow_definitions_postgres import (
    actions_by_node,
    publish,
    start_workflow,
    submit_record,
)
from tests.test_workflow_definitions_postgres import (
    deterministic_no_ai as deterministic_no_ai,
)
from tests.test_workflow_definitions_postgres import pytestmark as pytestmark

R_SOURCE = """snapshot <- jsonlite::fromJSON(file.path(Sys.getenv("AIRALOGY_INPUT_DIR"), "records.json"), simplifyVector=FALSE)
values <- vapply(snapshot$records, function(record) as.numeric(record$data$var$value), numeric(1))
result <- list(mean=mean(values), count=length(values), uid=as.integer(system("id -u", intern=TRUE)))
encoded <- jsonlite::toJSON(result, auto_unbox=TRUE, digits=16)
writeLines(encoded, Sys.getenv("AIRALOGY_RESULT_JSON"))
writeLines(encoded, "/airalogy/output/files/summary.json")
"""


async def r_workflow(*, actual_engine):
    async with database() as sessions:
        f = await fixture(sessions)
        f.scope = SimpleNamespace(**{**vars(f.scope), "analyst": f.scope.owner})
        async with sessions() as db:
            revision = await db.get(
                ResearchComputeEnvironmentRevision, f.compute.revision.id
            )
            revision.allowed_languages = ["r"]
            revision.runtime_version = "synthetic-r-jsonlite"
            if actual_engine:
                revision.image_ref = os.environ["COMPUTE_TEST_R_IMAGE"]
            await db.commit()
        raw = compute_draft(f.scope, f.compute).model_dump(mode="json")
        raw["recipe"].update(language="r", source_code=R_SOURCE)
        async with sessions() as db:
            preview = await analysis_compute.preview_analysis_compute(
                AnalysisComputeDraft.model_validate(raw), db, f.scope.owner, Response()
            )
            private = await analysis_compute.confirm_analysis_compute(
                analyses.AnalysisConfirmRequest(
                    preview_id=preview["id"],
                    preview_digest=preview["preview_digest"],
                    client_idempotency_key=f"r-source-{uuid4()}",
                ),
                db,
                f.scope.owner,
                Response(),
            )
        async with sessions() as db:
            details = await analysis_compute.get_analysis_compute_approval(
                UUID(str(private["id"])), db, f.scope.owner, Response()
            )
            await analysis_compute.decide_analysis_compute(
                UUID(str(private["id"])),
                decision_params(details),
                db,
                f.scope.owner,
                Response(),
            )
        delivered = await lease(sessions, f)
        assert delivered.job.language == "r" and delivered.job.source_code == R_SOURCE
        await download_and_start(sessions, f, delivered)
        # This prerequisite saved-method receipt is explicitly synthetic; the
        # final Workflow below is the optional actual-interpreter assertion.
        original_result = {"mean": 5.0, "count": 4, "uid": 65532}
        payload = json.dumps(original_result).encode()
        await upload(sessions, f, delivered, payload)
        await submit_completion(
            sessions, f, delivered, completion(delivered, original_result, payload)
        )
        async with sessions() as db:
            saved = await analyses.create_analysis_pipeline(
                analyses.PipelineCreateRequest(
                    run_id=UUID(str(private["id"])), title="Private pinned R method"
                ),
                db,
                f.scope.owner,
            )
        method, _ = await publish_compute_method(sessions, f, saved)
        workflow, _ = await publish(
            sessions,
            f.scope,
            WorkflowDraft(
                project_id=f.scope.project.id,
                title="Governed exact R analysis",
                graph=compute_graph(f, method),
            ),
        )
        task = await compute_task(
            sessions,
            f,
            compute_environment_revision_ids=[f.compute.revision.id],
            budget_limit="1",
            budget_currency="USD",
        )
        started, _ = await start_workflow(sessions, f.scope, workflow, task)
        actions = await actions_by_node(sessions, started["run_id"])
        record = await add_record(sessions, f.scope, 9, author=f.scope.owner, number=5)
        await submit_record(sessions, f.scope, actions["source"].id, record)
        f.records = [record]
        job = await queued(
            sessions, f, await actions_by_node(sessions, started["run_id"])
        )
        delivered = await lease(sessions, f)
        assert delivered.job.language == "r" and delivered.job.source_code == R_SOURCE
        inputs = await download_and_start(sessions, f, delivered)
        if actual_engine:
            result, payload = execute_container(delivered, inputs)
            assert result == {"mean": 9.0, "count": 1, "uid": 65532}
        else:
            result = {"mean": 9.0, "count": 1, "uid": 65532}
            payload = json.dumps(result).encode()
        await upload(sessions, f, delivered, payload)
        await submit_completion(
            sessions, f, delivered, completion(delivered, result, payload)
        )
        async with sessions() as db:
            persisted = await db.get(AnalysisRun, job.analysis_run_id)
            assert persisted.result["computed_result"] == result
            assert persisted.recipe["language"] == "r"
            assert (
                await db.get(ResearchTask, UUID(str(started["task_id"])))
            ).status == "review_required"


def test_workflow_r_language_and_source_are_fixed_through_real_receiver_lifecycle():
    asyncio.run(r_workflow(actual_engine=False))


@pytest.mark.skipif(
    os.environ.get("COMPUTE_ENGINE_TEST") != "1"
    or not os.environ.get("COMPUTE_TEST_R_IMAGE"),
    reason="Explicit pinned R/jsonlite OCI image is required; Python receipts are not R interpreter validation",
)
def test_workflow_r_source_executes_in_explicit_pinned_r_environment():
    asyncio.run(r_workflow(actual_engine=True))
