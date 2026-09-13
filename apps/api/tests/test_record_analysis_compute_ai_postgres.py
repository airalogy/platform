"""Paid advanced draft lifecycle against migrated PostgreSQL, synthetic transport.

Generation intentionally never runs source or grants a job/approval. Separate
Runner integration tests execute the adopted contract through the real container.
"""

from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import delete, select

from app.config import config
from app.models.analysis_ai import AnalysisAIRequest
from app.models.project import ProjectRole, ProjectUser
from app.models.research_execution import (
    ResearchComputeEnvironmentRevision,
    ResearchComputeJob,
    ResearchComputeRunner,
)
from app.routers import analysis_ai as ai_api
from app.routers.analysis_compute import get_analysis_compute_approval
from app.services import analysis_compute_ai
from app.services.analysis_generation import (
    ComputeDraftRequest,
    owned_ai_request,
)
from app.services.record_analyses import AnalysisSelection
from tests.test_record_analysis_ai_postgres import (
    draft_request,
    generate,
)
from tests.test_record_analysis_compute_postgres import (
    compute_draft,
    confirm,
    count_runs_and_jobs,
    preview,
    seed_compute,
)
from tests.test_record_analysis_postgres import add_record, database, seed_analysis

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="RESOURCE_TEST_DATABASE_URL is required for advanced draft guarantees",
)


@pytest.fixture(autouse=True)
def synthetic_policy(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", True)
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "synthetic-not-a-provider-key")


def params(scope, compute, **changes):
    return ComputeDraftRequest(
        **{
            "id": uuid4(),
            "protocol_id": scope.protocol.id,
            "selection": AnalysisSelection(),
            "question": "Compare synthetic groups",
            "environment_revision_id": compute.revision.id,
            "language": "python",
            **changes,
        }
    )


def output(scope, compute, mode="compute"):
    result = {
        "mode": mode,
        "title": "Synthetic advanced method",
        "explanation": "Propose source without executing the source.",
        "assumptions": ["Review the observational study design."],
    }
    if mode == "compute":
        result["recipe"] = compute_draft(scope, compute).recipe.model_dump(mode="json")
    else:
        result["clarification_questions"] = ["Which group is the control?"]
    return result


async def seeded(sessions):
    scope = await seed_analysis(sessions)
    await add_record(sessions, scope, 1234567)
    return scope, await seed_compute(sessions, scope)


@pytest.mark.parametrize("mode", ["compute", "clarification_required"])
def test_compute_generation_is_private_idempotent_without_runner_or_execution(
    monkeypatch, mode
):
    async def exercise():
        async with database() as sessions:
            scope, compute = await seeded(sessions)
            async with sessions() as db:
                runner = await db.get(ResearchComputeRunner, compute.runner.id)
                runner.enabled = False
                await db.commit()
            provider = AsyncMock(return_value=output(scope, compute, mode))
            monkeypatch.setattr(
                analysis_compute_ai, "aira_structured_proposal", provider
            )
            request = params(scope, compute)
            result = await generate(sessions, scope, request)
            assert result.kind == "compute_draft" and result.state == "generated"
            assert result.output["mode"] == mode
            assert result.analysis_run_id is None and result.previous_request_id is None
            assert await count_runs_and_jobs(sessions, scope) == (0, 0)
            assert "1234567" not in provider.call_args.args[0]
            assert (
                provider.call_args.kwargs["usage_context"].feature
                == "analysis.compute_draft"
            )
            assert (
                "scale" in provider.call_args.args[0]
            )  # Required input schema, not a fabricated empty recipe.
            assert (await generate(sessions, scope, request)).output == result.output
            assert provider.await_count == 1
            async with sessions() as db:
                response = Response()
                listed = await ai_api.list_compute_drafts(
                    scope.protocol.id, db, scope.analyst, response, 20, 0
                )
                assert listed["items"][0]["id"] == request.id
                assert "input_context" not in listed["items"][0]
                assert response.headers["Cache-Control"] == "private, no-store"
                with pytest.raises(HTTPException) as denied:
                    await owned_ai_request(db, request.id, scope.owner)
                assert denied.value.status_code == 404

    asyncio.run(exercise())


def test_advanced_concurrent_request_reserves_one_paid_attempt(monkeypatch):
    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        async with database() as sessions:
            scope, compute = await seeded(sessions)

            async def slow(*args, **kwargs):
                entered.set()
                await asyncio.wait_for(release.wait(), 5)
                return output(scope, compute)

            provider = AsyncMock(side_effect=slow)
            monkeypatch.setattr(
                analysis_compute_ai, "aira_structured_proposal", provider
            )
            request = params(scope, compute)
            task = asyncio.create_task(generate(sessions, scope, request))
            try:
                await asyncio.wait_for(entered.wait(), 5)
                duplicate = await asyncio.wait_for(
                    generate(sessions, scope, request), 5
                )
                assert duplicate.state == "generating"
            finally:
                release.set()
            result = await asyncio.wait_for(task, 5)
            assert result.state == "generated" and result.id == duplicate.id
            assert provider.await_count == 1
            assert await count_runs_and_jobs(sessions, scope) == (0, 0)

    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["disabled", "language", "other_lab", "permission"])
def test_new_generation_checks_environment_and_capability_before_paying(
    monkeypatch, change
):
    provider = AsyncMock()
    monkeypatch.setattr(analysis_compute_ai, "aira_structured_proposal", provider)

    async def exercise():
        async with database() as sessions:
            scope, compute = await seeded(sessions)
            request = params(scope, compute)
            async with sessions() as db:
                if change == "disabled":
                    revision = await db.get(
                        ResearchComputeEnvironmentRevision, compute.revision.id
                    )
                    revision.enabled = False
                elif change == "permission":
                    member = await db.scalar(
                        select(ProjectUser).where(
                            ProjectUser.project_id == scope.project.id,
                            ProjectUser.user_id == scope.analyst.id,
                        )
                    )
                    member.role = ProjectRole.EXPLORER
                await db.commit()
            if change == "language":
                request = params(scope, compute, language="r")
            elif change == "other_lab":
                another = await seed_analysis(sessions)
                foreign = await seed_compute(sessions, another)
                request = params(
                    scope, compute, environment_revision_id=foreign.revision.id
                )
            with pytest.raises(HTTPException):
                await generate(sessions, scope, request)
            assert provider.await_count == 0
            async with sessions() as db:
                assert await db.get(AnalysisAIRequest, request.id) is None

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "change", ["sources", "environment", "permission", "revocation", "ai_off"]
)
def test_generation_revalidates_after_paid_call_and_discards_changed_context(
    monkeypatch, change
):
    async def exercise():
        async with database() as sessions:
            scope, compute = await seeded(sessions)

            async def changing(*args, **kwargs):
                if change == "sources":
                    await add_record(sessions, scope, 2, number=2)
                elif change == "ai_off":
                    monkeypatch.setattr(config, "AI_ENABLED", False)
                else:
                    async with sessions() as db:
                        if change == "environment":
                            revision = await db.get(
                                ResearchComputeEnvironmentRevision, compute.revision.id
                            )
                            revision.input_schema = {
                                "type": "object",
                                "required": ["other"],
                            }
                        elif change == "permission":
                            member = await db.scalar(
                                select(ProjectUser).where(
                                    ProjectUser.project_id == scope.project.id,
                                    ProjectUser.user_id == scope.analyst.id,
                                )
                            )
                            member.role = ProjectRole.EXPLORER
                        else:
                            await db.execute(
                                delete(ProjectUser).where(
                                    ProjectUser.project_id == scope.project.id,
                                    ProjectUser.user_id == scope.analyst.id,
                                )
                            )
                        await db.commit()
                return output(scope, compute)

            provider = AsyncMock(side_effect=changing)
            monkeypatch.setattr(
                analysis_compute_ai, "aira_structured_proposal", provider
            )
            request = params(scope, compute)
            if change in {"permission", "revocation"}:
                with pytest.raises(HTTPException) as revoked:
                    await generate(sessions, scope, request)
                assert revoked.value.status_code == 403
            else:
                result = await generate(sessions, scope, request)
                assert result.state == "failed"
            async with sessions() as db:
                saved = await db.get(AnalysisAIRequest, request.id)
                assert saved.state == "failed" and saved.output is None
                assert saved.output_digest is None
            assert provider.await_count == 1
            assert await count_runs_and_jobs(sessions, scope) == (0, 0)

    asyncio.run(exercise())


def test_followups_keep_exact_draft_kind_environment_language_and_fingerprint(
    monkeypatch,
):
    async def exercise():
        async with database() as sessions:
            scope, compute = await seeded(sessions)
            provider = AsyncMock(
                return_value=output(scope, compute, "clarification_required")
            )
            monkeypatch.setattr(
                analysis_compute_ai, "aira_structured_proposal", provider
            )
            request = params(scope, compute)
            initial = await generate(sessions, scope, request)
            followup = params(
                scope,
                compute,
                previous_request_id=initial.id,
                question="Group A is the control",
            )
            assert (await generate(sessions, scope, followup)).state == "generated"
            with pytest.raises(HTTPException) as conflict:
                await generate(
                    sessions,
                    scope,
                    params(scope, compute, id=request.id, question="Another question"),
                )
            assert conflict.value.status_code == 409
            for invalid in (
                params(scope, compute, previous_request_id=initial.id, language="r"),
                params(
                    scope,
                    compute,
                    previous_request_id=initial.id,
                    environment_revision_id=uuid4(),
                ),
                draft_request(scope, previous_request_id=initial.id),
            ):
                with pytest.raises(HTTPException) as mismatch:
                    await generate(sessions, scope, invalid)
                assert mismatch.value.status_code == 409
            assert provider.await_count == 2

    asyncio.run(exercise())


def test_draft_adoption_provenance_edits_ai_off_and_exact_environment(monkeypatch):
    async def exercise():
        async with database() as sessions:
            scope, compute = await seeded(sessions)
            provider = AsyncMock(return_value=output(scope, compute))
            monkeypatch.setattr(
                analysis_compute_ai, "aira_structured_proposal", provider
            )
            generated = await generate(sessions, scope, params(scope, compute))
            monkeypatch.setattr(config, "AI_ENABLED", False)
            proposal = compute_draft(
                scope, compute, ai_draft_id=generated.id, question=generated.question
            )
            original = await preview(sessions, scope, proposal)
            assert original.ai_provenance["user_edited"] is False
            edited = proposal.model_copy(deep=True)
            edited.recipe.source_code += "# reviewed by researcher\n"
            changed = await preview(sessions, scope, edited)
            assert changed.ai_provenance["user_edited"] is True
            run = await confirm(sessions, scope, changed)
            assert run.ai_provenance == changed.ai_provenance
            assert run.recipe["source_code"].endswith("# reviewed by researcher\n")
            async with sessions() as db:
                job = await db.scalar(
                    select(ResearchComputeJob).where(
                        ResearchComputeJob.analysis_run_id == run.id
                    )
                )
                assert job.status == "awaiting_approval"
                approval = await get_analysis_compute_approval(
                    run.id, db, scope.owner, Response()
                )
                assert approval["run"]["ai_provenance"] == {}
                assert (
                    approval["contract"]["source"]["code"] == edited.recipe.source_code
                )
            foreign = await seed_compute(sessions, scope)
            mismatched = proposal.model_copy(deep=True)
            mismatched.recipe.environment_revision_id = foreign.revision.id
            with pytest.raises(HTTPException) as wrong_environment:
                await preview(sessions, scope, mismatched)
            assert wrong_environment.value.status_code == 409
            await add_record(sessions, scope, 2, number=2)
            with pytest.raises(HTTPException) as stale:
                await preview(sessions, scope, proposal)
            assert stale.value.status_code == 409
            async with sessions() as db:
                revision = await db.get(
                    ResearchComputeEnvironmentRevision, compute.revision.id
                )
                revision.enabled = False
                await db.commit()
            async with sessions() as db:
                readable = await owned_ai_request(db, generated.id, scope.analyst)
                assert (
                    readable.output == generated.output
                )  # AI/environment off do not erase history.
            assert provider.await_count == 1

    asyncio.run(exercise())


@pytest.mark.parametrize("failure", ["timeout", "invalid", "provider_failure"])
def test_failed_compute_generation_is_final_and_safe_on_retry(monkeypatch, failure):
    async def exercise():
        async with database() as sessions:
            scope, compute = await seeded(sessions)
            raw = output(scope, compute)
            if failure == "invalid":
                raw["approved"] = True
            provider = AsyncMock(return_value=raw)
            if failure != "invalid":
                provider.side_effect = (
                    TimeoutError("private secret")
                    if failure == "timeout"
                    else RuntimeError("private secret")
                )
            monkeypatch.setattr(
                analysis_compute_ai, "aira_structured_proposal", provider
            )
            request = params(scope, compute)
            result = await generate(sessions, scope, request)
            assert result.state == "failed" and result.output is None
            assert "private secret" not in json.dumps(result.as_dict(), default=str)
            assert (await generate(sessions, scope, request)).state == "failed"
            assert provider.await_count == 1

    asyncio.run(exercise())
