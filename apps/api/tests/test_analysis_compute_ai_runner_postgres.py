"""Synthetic Aira transport -> real approved OCI computation -> grounded report.

Only the model's final transport response is replaced. The test does not claim
model quality: it proves generated source uses the ordinary private execution,
approval, storage and provenance paths against migrated disposable services.
"""

from __future__ import annotations

import asyncio
import copy
import os
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from sqlalchemy import func, select

from app.config import config
from app.models.analysis import AnalysisRun
from app.models.research_execution import ResearchComputeJob
from app.routers import analyses as reports
from app.routers import analysis_compute as compute_api
from app.routers import research_compute_jobs as jobs
from app.services import analysis_compute_ai
from app.services.analysis_compute_contracts import AnalysisComputeDraft
from app.services.analysis_generation import (
    ComputeDraftRequest,
    InterpretationRequest,
    generate_request,
    owned_ai_request,
)
from app.services.record_analyses import AnalysisSelection
from tests.test_analysis_compute_runtime_postgres import (
    SOURCE,
    completion,
    download_and_start,
    execute_container,
    fixture,
    lease,
    read_completed,
    submit_completion,
    upload,
)
from tests.test_record_analysis_compute_postgres import compute_draft, decision_params
from tests.test_record_analysis_postgres import add_record, database

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL")
    or os.environ.get("COMPUTE_ENGINE_TEST") != "1",
    reason="Dedicated migrated services and explicit real OCI execution are required",
)


async def confirm_and_approve(sessions, f, draft):
    async with sessions() as db:
        preview = await compute_api.preview_analysis_compute(
            draft, db, f.scope.analyst, Response()
        )
    async with sessions() as db:
        run = await compute_api.confirm_analysis_compute(
            reports.AnalysisConfirmRequest(
                preview_id=preview["id"],
                preview_digest=preview["preview_digest"],
                client_idempotency_key=f"generated-source-{uuid4().hex}",
            ),
            db,
            f.scope.analyst,
            Response(),
        )
    identity = UUID(str(run["id"]))
    async with sessions() as db:
        approval = await compute_api.get_analysis_compute_approval(
            identity, db, f.scope.owner, Response()
        )
        assert approval["job"]["status"] == "awaiting_approval"
    async with sessions() as db:
        assert (await jobs.lease_compute_job(f.token, db))["job"] is None
    async with sessions() as db:
        approved = await compute_api.decide_analysis_compute(
            identity, decision_params(approval), db, f.scope.owner, Response()
        )
        assert approved["job"]["status"] == "queued"
    return identity


async def execute_and_read(sessions, f, identity, expected):
    delivery = await lease(sessions, f)
    assert delivery.job.analysis_id == str(identity)
    inputs = await download_and_start(sessions, f, delivery)
    result, payload = execute_container(delivery, inputs)
    assert result == expected
    await upload(sessions, f, delivery, payload)
    receipt = completion(delivery, result, payload)
    assert await submit_completion(sessions, f, delivery, receipt) == {
        "status": "completed"
    }
    await read_completed(sessions, f, delivery, result, payload)
    async with sessions() as db:
        return await compute_api.get_analysis_compute(
            identity, db, f.scope.analyst, Response()
        )


def test_generated_editable_source_runs_only_after_approval_and_method_rerun_is_ai_independent(
    monkeypatch,
):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", True)
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "synthetic-not-a-provider-key")
    provider = AsyncMock()
    monkeypatch.setattr(analysis_compute_ai, "aira_structured_proposal", provider)

    async def exercise():
        async with database() as sessions:
            f = await fixture(sessions, real_engine=True)
            raw = compute_draft(f.scope, f.compute).model_dump(mode="json")
            raw["recipe"]["source_code"] = SOURCE
            provider.return_value = {
                "mode": "compute",
                "title": "Synthetic sealed mean",
                "explanation": "Read the selected inputs in the isolated runner.",
                "assumptions": ["The selected field has compatible units."],
                "recipe": raw["recipe"],
                "clarification_questions": [],
            }
            request = ComputeDraftRequest(
                id=uuid4(),
                protocol_id=f.scope.protocol.id,
                selection=AnalysisSelection(),
                question="Compute the mean and valid count with an auditable script.",
                environment_revision_id=f.compute.revision.id,
                language="python",
            )
            async with sessions() as db:
                generated = await generate_request(db, request, f.scope.analyst)
            assert generated.state == "generated", generated.error
            assert provider.await_count == 1
            prompt = provider.call_args.args[0]
            assert "records.json" in prompt
            assert all(str(record.id) not in prompt for record in f.records)
            async with sessions() as db:
                recovered = await generate_request(db, request, f.scope.analyst)
                assert recovered.id == generated.id
                for model in (AnalysisRun, ResearchComputeJob):
                    assert (
                        await db.scalar(
                            select(func.count())
                            .select_from(model)
                            .where(model.created_by_user_id == f.scope.analyst.id)
                        )
                        == 0
                    )
            assert provider.await_count == 1

            # Adoption is editable and not authority. AI may be disabled before
            # the ordinary preview/confirmation and separate approval.
            raw["recipe"] = copy.deepcopy(generated.output["recipe"])
            raw["recipe"]["source_code"] += "\n# Reviewed by the synthetic initiator.\n"
            raw["question"] = request.question
            raw["ai_draft_id"] = str(generated.id)
            monkeypatch.setattr(config, "AI_ENABLED", False)
            identity = await confirm_and_approve(
                sessions, f, AnalysisComputeDraft.model_validate(raw)
            )
            first = await execute_and_read(
                sessions, f, identity, {"mean": 5.0, "count": 4, "uid": 65532}
            )
            assert first["run"]["ai_provenance"]["request_id"] == str(generated.id)
            assert first["run"]["ai_provenance"]["user_edited"] is True
            sealed_first = copy.deepcopy(first["run"])

            # Model prose can select existing result coordinates, never supply
            # authoritative numerical replacements or hidden file contents.
            monkeypatch.setattr(config, "AI_ENABLED", True)
            provider.return_value = {
                "result_kind": "compute",
                "summary": "The script returned descriptive statistics.",
                "observations": [
                    {
                        "text": "Consult the computed mean and sample count.",
                        "metrics": [{"pointer": "/mean"}, {"pointer": "/count"}],
                    }
                ],
                "limitations": ["A descriptive mean does not establish causality."],
                "next_steps": ["Review the study design before inference."],
            }
            async with sessions() as db:
                interpretation = await generate_request(
                    db,
                    InterpretationRequest(id=uuid4()),
                    f.scope.analyst,
                    analysis_id=identity,
                )
            assert interpretation.state == "generated", interpretation.error
            assert interpretation.output["observations"][0]["metrics"] == [
                {"pointer": "/mean", "value": 5.0},
                {"pointer": "/count", "value": 4},
            ]
            assert provider.await_count == 2
            monkeypatch.setattr(config, "AI_ENABLED", False)
            async with sessions() as db:
                history = await owned_ai_request(db, interpretation.id, f.scope.analyst)
                assert history.output_digest == interpretation.output_digest
                method = await reports.create_analysis_pipeline(
                    reports.PipelineCreateRequest(
                        run_id=identity, title="Reviewed method"
                    ),
                    db,
                    f.scope.analyst,
                )
            f.records.append(
                await add_record(
                    sessions,
                    f.scope,
                    10,
                    author=f.scope.analyst,
                    number=5,
                )
            )
            rerun = copy.deepcopy(raw)
            rerun.pop("ai_draft_id")
            rerun["rerun_of_id"] = str(identity)
            rerun["pipeline_revision_id"] = str(method["revisions"][0]["id"])
            rerun_id = await confirm_and_approve(
                sessions, f, AnalysisComputeDraft.model_validate(rerun)
            )
            second = await execute_and_read(
                sessions, f, rerun_id, {"mean": 6.0, "count": 5, "uid": 65532}
            )
            assert second["run"]["ai_provenance"]["inherited"] is True
            assert second["run"]["source_digest"] != sealed_first["source_digest"]
            async with sessions() as db:
                original = await compute_api.get_analysis_compute(
                    identity, db, f.scope.analyst, Response()
                )
                assert original["run"] == sealed_first
            assert provider.await_count == 2

    asyncio.run(exercise())
