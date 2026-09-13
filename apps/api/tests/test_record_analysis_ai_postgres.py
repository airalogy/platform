"""Real PostgreSQL Aira analysis lifecycle; only the model response is replaced.

Run with the dedicated e2e database. Authorization, SQL, snapshots, confirmation,
and numerical computation use production code and synthetic research data.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from masterbrain.usage import UsageContext
from sqlalchemy import delete, func, select, update

from app.config import config
from app.models.analysis import AnalysisRun
from app.models.analysis_ai import AnalysisAIRequest
from app.models.project import ProjectRole, ProjectUser
from app.models.record import Record
from app.models.resource import PersistentJob
from app.routers import analyses as api
from app.routers import analysis_ai as ai_api
from app.services import analysis_ai
from app.services.analysis_engine import (
    AnalysisRecipe,
    canonical_digest,
    compute_analysis,
)
from app.services.analysis_generation import (
    DraftRequest,
    InterpretationRequest,
    generate_request,
    owned_ai_request,
    request_payload,
    settle_interrupted_request,
)
from app.services.record_analyses import AnalysisSelection
from tests.test_record_analysis_postgres import (
    add_record,
    confirm,
    database,
    execute_job,
    get_run,
    group_stats,
    preview,
    recipe,
    seed_analysis,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="RESOURCE_TEST_DATABASE_URL is required for real AI analysis guarantees",
)


@pytest.fixture(autouse=True)
def synthetic_ai_policy(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", True)
    # No real credential is needed: only the last model adapter is replaced.
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "synthetic-not-a-provider-key")


def builtin_output():
    return {
        "mode": "builtin",
        "title": "Compare experimental groups",
        "explanation": "Calculate descriptive means using the selected Records.",
        "assumptions": ["Group labels describe the intended experimental groups."],
        "recipe": recipe().model_dump(mode="json"),
    }


def interpretation_output():
    return {
        "summary": "The selected group has a descriptive mean.",
        "observations": [
            {
                "text": "The metric card reports the computed group mean.",
                "metrics": [{"field": "value", "group_index": 0, "statistic": "mean"}],
            }
        ],
        "limitations": ["Descriptive measurements do not establish causality."],
        "next_steps": ["Review the experimental design."],
    }


def draft_request(scope, **changes):
    return DraftRequest.model_validate(
        {
            "id": uuid4(),
            "protocol_id": scope.protocol.id,
            "selection": AnalysisSelection(),
            "question": "Compare synthetic groups",
            **changes,
        }
    )


async def generate(sessions, scope, params, *, user=None, analysis_id=None):
    async with sessions() as db:
        return await generate_request(
            db, params, user or scope.analyst, analysis_id=analysis_id
        )


async def read_request(sessions, scope, identity, *, user=None):
    async with sessions() as db:
        return await owned_ai_request(db, identity, user or scope.analyst)


async def assert_no_execution(sessions, scope):
    async with sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AnalysisRun)
                .where(AnalysisRun.project_id == scope.project.id)
            )
            == 0
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(PersistentJob)
                .where(PersistentJob.lab_id == scope.lab.id)
            )
            == 0
        )


@pytest.mark.parametrize(
    "mode", ["builtin", "clarification_required", "compute_required"]
)
def test_draft_modes_are_private_persisted_suggestions_with_trusted_usage(
    monkeypatch, mode
):
    raw = builtin_output()
    if mode != "builtin":
        raw.pop("recipe")
        raw["mode"] = mode
        if mode == "clarification_required":
            raw["clarification_questions"] = [
                "Which group is the experimental control?"
            ]
        else:
            raw["compute_requirements"] = [
                "A separately reviewed regression method is required."
            ]
    provider = AsyncMock(return_value=raw)
    monkeypatch.setattr(analysis_ai, "aira_structured_proposal", provider)

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 1234567)
            params = draft_request(scope)
            generated = await generate(sessions, scope, params)
            assert generated.state == "generated"
            assert generated.kind == "draft" and generated.analysis_run_id is None
            assert generated.output["mode"] == mode
            assert generated.output_digest == canonical_digest(generated.output)
            await assert_no_execution(sessions, scope)
            usage = provider.call_args.kwargs["usage_context"]
            assert isinstance(usage, UsageContext)
            assert usage.feature == "analysis.draft"
            assert usage.user_id == str(scope.analyst.id)
            assert usage.tenant_id == str(scope.lab.id)
            assert usage.project_id == str(scope.project.id)
            assert usage.operation_id == generated.operation_id
            assert usage.attributes["analysis_ai_request_id"] == str(params.id)
            assert usage.attributes["protocol_id"] == str(scope.protocol.id)
            # Drafting sees schema/selection metadata, never raw measurements.
            assert "1234567" not in provider.call_args.args[0]
            retried = await generate(sessions, scope, params)
            assert retried.id == generated.id and retried.output == generated.output
            assert provider.await_count == 1
            payload = request_payload(retried)
            assert "input_context" not in payload and "source_manifest" not in payload

    asyncio.run(exercise())


def test_concurrent_paid_request_identity_calls_model_once(monkeypatch):
    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow_provider(*_args, **_kwargs):
            entered.set()
            await asyncio.wait_for(release.wait(), timeout=5)
            return builtin_output()

        provider = AsyncMock(side_effect=slow_provider)
        monkeypatch.setattr(analysis_ai, "aira_structured_proposal", provider)
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            params = draft_request(scope)
            first = asyncio.create_task(generate(sessions, scope, params))
            try:
                await asyncio.wait_for(entered.wait(), timeout=5)
                duplicate = await asyncio.wait_for(
                    generate(sessions, scope, params), timeout=5
                )
                assert duplicate.state == "generating"
            finally:
                release.set()
            completed = await asyncio.wait_for(first, timeout=5)
            assert completed.id == duplicate.id and completed.state == "generated"
            assert provider.await_count == 1
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisAIRequest)
                        .where(AnalysisAIRequest.project_id == scope.project.id)
                    )
                    == 1
                )
            await assert_no_execution(sessions, scope)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "invalid", ["extra", "unknown_field", "provider_failure", "timeout"]
)
def test_invalid_or_failed_generation_has_no_output_and_never_leaks_provider_text(
    monkeypatch, invalid, caplog
):
    raw = builtin_output()
    if invalid == "extra":
        raw["execute_sql"] = "private-provider-payload"
    elif invalid == "unknown_field":
        raw["recipe"]["numeric_fields"] = ["private-provider-payload"]
    provider = AsyncMock(return_value=raw)
    if invalid == "provider_failure":
        provider.side_effect = RuntimeError(
            "private-provider-payload credential=SECRET"
        )
    elif invalid == "timeout":
        provider.side_effect = TimeoutError(
            "private-provider-payload credential=SECRET"
        )
    monkeypatch.setattr(analysis_ai, "aira_structured_proposal", provider)

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            params = draft_request(scope)
            failed = await generate(sessions, scope, params)
            assert failed.state == "failed"
            assert failed.output is None and failed.output_digest is None
            assert (
                failed.error
                == {
                    "extra": "invalid_proposal",
                    "unknown_field": "invalid_proposal",
                    "provider_failure": "model_unavailable",
                    "timeout": "model_timeout",
                }[invalid]
            )
            assert "private-provider-payload" not in json.dumps(
                request_payload(failed), default=str
            )
            await generate(sessions, scope, params)
            assert provider.await_count == 1
            await assert_no_execution(sessions, scope)

    asyncio.run(exercise())
    assert "private-provider-payload" not in caplog.text


def test_ai_disabled_rejects_generation_but_manual_analysis_remains_complete(
    monkeypatch,
):
    monkeypatch.setattr(config, "AI_ENABLED", False)
    provider = AsyncMock(return_value=builtin_output())
    monkeypatch.setattr(analysis_ai, "aira_structured_proposal", provider)

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            await add_record(sessions, scope, 4, number=2)
            with pytest.raises(HTTPException) as disabled:
                await generate(sessions, scope, draft_request(scope))
            assert disabled.value.status_code == 503
            assert provider.await_count == 0
            run = await confirm(sessions, scope, await preview(sessions, scope))
            await execute_job(sessions, run)
            report = await get_run(sessions, scope, run["id"])
            assert report["status"] == "succeeded"
            assert group_stats(report["result"])["A"]["mean"] == 3
            assert report["ai_provenance"] == {}

    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["new_record", "revoke"])
def test_context_or_permission_change_during_generation_cannot_be_adopted(
    monkeypatch, change
):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)

            async def changing_provider(*_args, **_kwargs):
                if change == "new_record":
                    await add_record(sessions, scope, 100, number=2)
                else:
                    async with sessions() as db:
                        await db.execute(
                            delete(ProjectUser).where(
                                ProjectUser.project_id == scope.project.id,
                                ProjectUser.user_id == scope.analyst.id,
                            )
                        )
                        await db.commit()
                return builtin_output()

            provider = AsyncMock(side_effect=changing_provider)
            monkeypatch.setattr(analysis_ai, "aira_structured_proposal", provider)
            params = draft_request(scope)
            if change == "revoke":
                with pytest.raises(HTTPException) as revoked:
                    await generate(sessions, scope, params)
                assert revoked.value.status_code == 403
            else:
                assert (await generate(sessions, scope, params)).state == "failed"
            async with sessions() as db:
                persisted = await db.get(AnalysisAIRequest, params.id)
                assert persisted.state == "failed"
                assert persisted.output is None and persisted.output_digest is None
                assert persisted.error == (
                    "context_changed"
                    if change == "new_record"
                    else "source_access_changed"
                )
            assert provider.await_count == 1
            await assert_no_execution(sessions, scope)

    asyncio.run(exercise())


def test_saved_generation_is_owner_private_and_rechecks_original_source_access(
    monkeypatch,
):
    provider = AsyncMock(return_value=builtin_output())
    monkeypatch.setattr(analysis_ai, "aira_structured_proposal", provider)

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            original = await add_record(sessions, scope, 2)
            params = draft_request(scope)
            row = await generate(sessions, scope, params)
            for user in (scope.owner, scope.outsider):
                with pytest.raises(HTTPException) as private:
                    await read_request(sessions, scope, row.id, user=user)
                assert private.value.status_code == 404
                with pytest.raises(HTTPException) as collision:
                    await generate(sessions, scope, params, user=user)
                assert collision.value.status_code == 404
            changed_request = params.model_copy(
                update={"question": "A different question"}
            )
            with pytest.raises(HTTPException) as reused_identity:
                await generate(sessions, scope, changed_request)
            assert reused_identity.value.status_code == 409
            async with sessions() as db:
                await db.execute(
                    update(Record)
                    .where(Record.id == original.id)
                    .values(deleted_at=datetime.now(UTC).replace(tzinfo=None))
                )
                await db.commit()
            with pytest.raises(HTTPException) as lost_source:
                await read_request(sessions, scope, row.id)
            assert lost_source.value.status_code == 403
            assert provider.await_count == 1

    asyncio.run(exercise())


def test_generated_draft_can_be_edited_confirmed_and_computed_with_persistent_provenance(
    monkeypatch,
):
    provider = AsyncMock(return_value=builtin_output())
    monkeypatch.setattr(analysis_ai, "aira_structured_proposal", provider)

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            await add_record(sessions, scope, 4, number=2)
            generated = await generate(sessions, scope, draft_request(scope))
            edited = AnalysisRecipe.model_validate(
                {**generated.output["recipe"], "chart": "line"}
            )
            draft = await preview(
                sessions, scope, selected_recipe=edited, ai_draft_id=generated.id
            )
            assert draft["ai_provenance"]["user_edited"] is True
            run = await confirm(sessions, scope, draft)
            await execute_job(sessions, run)
            report = await get_run(sessions, scope, run["id"])
            assert report["status"] == "succeeded"
            assert group_stats(report["result"])["A"]["mean"] == 3
            assert report["recipe"]["chart"] == "line"
            assert report["ai_provenance"] == draft["ai_provenance"]
            provenance = report["ai_provenance"]
            assert provenance["request_id"] == str(generated.id)
            assert provenance["input_digest"] == generated.input_digest
            assert provenance["output_digest"] == generated.output_digest
            assert provenance["generation"]["recipe"]["chart"] == "bar"
            assert provenance["digest"] == canonical_digest(
                {key: value for key, value in provenance.items() if key != "digest"}
            )
            stored = await read_request(sessions, scope, generated.id)
            assert stored.output["recipe"]["chart"] == "bar"
            assert provider.await_count == 1

    asyncio.run(exercise())


def test_interpretation_grounds_true_metric_and_does_not_rewrite_report_or_records(
    monkeypatch,
):
    provider = AsyncMock(return_value=interpretation_output())
    monkeypatch.setattr(analysis_ai, "aira_structured_proposal", provider)

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            originals = [
                await add_record(sessions, scope, 2),
                await add_record(sessions, scope, 4, number=2),
            ]
            run = await confirm(sessions, scope, await preview(sessions, scope))
            await execute_job(sessions, run)
            before = copy.deepcopy(await get_run(sessions, scope, run["id"]))
            params = InterpretationRequest(
                id=uuid4(), question="Explain the actual descriptive result"
            )
            explanation = await generate(sessions, scope, params, analysis_id=run["id"])
            assert (
                explanation.kind == "interpretation"
                and explanation.state == "generated"
            )
            metric = explanation.output["observations"][0]["metrics"][0]
            assert metric["value"] == 3 and metric["unit"] == "mg/L"
            assert metric["n"] == 2 and metric["row_count"] == 2
            assert explanation.output["numeric_values_origin"] == "computed_result"
            assert (
                provider.call_args.kwargs["usage_context"].feature
                == "analysis.interpretation"
            )
            assert await get_run(sessions, scope, run["id"]) == before
            async with sessions() as db:
                for original in originals:
                    current = await db.get(Record, (original.id, original.version))
                    assert (
                        current.data == original.data and current.hash == original.hash
                    )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisRun)
                        .where(AnalysisRun.project_id == scope.project.id)
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(PersistentJob)
                        .where(PersistentJob.lab_id == scope.lab.id)
                    )
                    == 1
                )

    asyncio.run(exercise())


def test_interrupted_expired_attempt_is_settled_without_repeating_model_call(
    monkeypatch,
):
    async def exercise():
        entered = asyncio.Event()

        async def interrupted_provider(*_args, **_kwargs):
            entered.set()
            await asyncio.wait_for(asyncio.Event().wait(), timeout=5)
            return builtin_output()

        provider = AsyncMock(side_effect=interrupted_provider)
        monkeypatch.setattr(analysis_ai, "aira_structured_proposal", provider)
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            params = draft_request(scope)
            task = asyncio.create_task(generate(sessions, scope, params))
            await asyncio.wait_for(entered.wait(), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            async with sessions() as db:
                persisted = await db.get(AnalysisAIRequest, params.id)
                assert persisted.state == "generating"
                persisted.deadline = datetime.now(UTC) - timedelta(seconds=1)
                await db.commit()
            async with sessions() as db:
                persisted = await owned_ai_request(db, params.id, scope.analyst)
                await settle_interrupted_request(db, persisted)
                await db.commit()
                assert (
                    persisted.state == "failed"
                    and persisted.error == "generation_interrupted"
                )
                assert persisted.output is None and persisted.output_digest is None
            retried = await generate(sessions, scope, params)
            assert (
                retried.state == "failed" and retried.error == "generation_interrupted"
            )
            assert provider.await_count == 1
            await assert_no_execution(sessions, scope)

    asyncio.run(exercise())


def test_followup_preserves_prior_draft_and_cannot_switch_protocol(monkeypatch):
    provider = AsyncMock(return_value=builtin_output())
    monkeypatch.setattr(analysis_ai, "aira_structured_proposal", provider)

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            first = await generate(sessions, scope, draft_request(scope))
            followup = await generate(
                sessions,
                scope,
                draft_request(
                    scope,
                    question="Keep the method and clarify its limitations",
                    previous_request_id=first.id,
                ),
            )
            assert followup.previous_request_id == first.id
            assert followup.input_context["previous_draft"] == first.output
            assert followup.input_context["followup_depth"] == 1
            assert (
                await read_request(sessions, scope, first.id)
            ).output == first.output
            other_scope = await seed_analysis(sessions)
            await add_record(sessions, other_scope, 8)
            async with sessions() as db:
                db.add(
                    ProjectUser(
                        project_id=other_scope.project.id,
                        user_id=scope.analyst.id,
                        role=ProjectRole.COLLABORATOR,
                        create_user_id=other_scope.owner.id,
                    )
                )
                await db.commit()
            with pytest.raises(HTTPException) as wrong_protocol:
                await generate(
                    sessions,
                    scope,
                    draft_request(other_scope, previous_request_id=first.id),
                )
            assert wrong_protocol.value.status_code == 409
            assert provider.await_count == 2

    asyncio.run(exercise())


async def replace_result_with_matching_digest(sessions, run_id):
    """Simulate a separate transaction rewriting a report and its valid checksum.

    The replacement uses the real engine and a temporary copy of synthetic rows;
    it changes neither persisted Records nor the original source snapshot.
    """
    async with sessions() as db:
        run = await db.get(AnalysisRun, run_id)
        copied_rows = copy.deepcopy(run.source_snapshot["records"])
        for row in copied_rows:
            row["data"]["var"]["value"] += 100
        replacement = compute_analysis(
            AnalysisRecipe.model_validate(run.recipe),
            copied_rows,
            run.source_snapshot["fields"],
        )
        run.result = replacement
        run.result_digest = canonical_digest(replacement)
        await db.commit()
        return run.result_digest


def test_interpretation_discards_old_result_after_concurrent_valid_checksum_rewrite(
    monkeypatch,
):
    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow_provider(*_args, **_kwargs):
            entered.set()
            await asyncio.wait_for(release.wait(), timeout=5)
            return interpretation_output()

        provider = AsyncMock(side_effect=slow_provider)
        monkeypatch.setattr(analysis_ai, "aira_structured_proposal", provider)
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            await add_record(sessions, scope, 4, number=2)
            run = await confirm(sessions, scope, await preview(sessions, scope))
            await execute_job(sessions, run)
            before = await get_run(sessions, scope, run["id"])
            params = InterpretationRequest(id=uuid4(), question="Explain the mean")
            generating = asyncio.create_task(
                generate(sessions, scope, params, analysis_id=run["id"])
            )
            try:
                await asyncio.wait_for(entered.wait(), timeout=5)
                new_digest = await replace_result_with_matching_digest(
                    sessions, run["id"]
                )
                current = await get_run(sessions, scope, run["id"])
                # The report passes its own checksum and source authorization;
                # the stale interpretation must fail its separate result binding.
                assert new_digest != before["result_digest"]
                assert current["result_digest"] == canonical_digest(current["result"])
                assert group_stats(current["result"])["A"]["mean"] == 103
            finally:
                release.set()
            with pytest.raises(HTTPException) as changed:
                await asyncio.wait_for(generating, timeout=5)
            assert changed.value.status_code == 409
            async with sessions() as db:
                saved = await db.get(AnalysisAIRequest, params.id)
                assert saved.state == "failed"
                assert saved.output is None and saved.output_digest is None
                assert saved.input_context["result_digest"] == before["result_digest"]
                assert group_stats(saved.input_context["result"])["A"]["mean"] == 3
            assert provider.await_count == 1

    asyncio.run(exercise())


def test_saved_interpretation_get_rejects_changed_bound_result_digest(monkeypatch):
    provider = AsyncMock(return_value=interpretation_output())
    monkeypatch.setattr(analysis_ai, "aira_structured_proposal", provider)

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            await add_record(sessions, scope, 4, number=2)
            run = await confirm(sessions, scope, await preview(sessions, scope))
            await execute_job(sessions, run)
            params = InterpretationRequest(id=uuid4(), question="Explain the mean")
            explanation = await generate(sessions, scope, params, analysis_id=run["id"])
            original_output = copy.deepcopy(explanation.output)
            async with sessions() as db:
                response = Response()
                readable = await ai_api.get_generation(
                    explanation.id, db, scope.analyst, response
                )
                assert response.headers["Cache-Control"] == "private, no-store"
                assert readable["output"] == original_output
            new_digest = await replace_result_with_matching_digest(sessions, run["id"])
            assert (await get_run(sessions, scope, run["id"]))[
                "result_digest"
            ] == new_digest
            async with sessions() as db:
                with pytest.raises(HTTPException) as stale:
                    await ai_api.get_generation(
                        explanation.id, db, scope.analyst, Response()
                    )
                assert stale.value.status_code == 409
            with pytest.raises(HTTPException) as stale_retry:
                await generate(sessions, scope, params, analysis_id=run["id"])
            assert stale_retry.value.status_code == 409
            async with sessions() as db:
                persisted = await db.get(AnalysisAIRequest, explanation.id)
                assert persisted.output == original_output
                assert persisted.output_digest == explanation.output_digest
                assert persisted.input_context["result_digest"] != new_digest
            assert provider.await_count == 1

    asyncio.run(exercise())


def test_saved_ai_method_revisions_preserve_inheritance_and_sticky_user_edits(
    monkeypatch,
):
    provider = AsyncMock(return_value=builtin_output())
    monkeypatch.setattr(analysis_ai, "aira_structured_proposal", provider)

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            await add_record(sessions, scope, 4, number=2)
            generated = await generate(sessions, scope, draft_request(scope))
            initial = await confirm(
                sessions,
                scope,
                await preview(sessions, scope, ai_draft_id=generated.id),
            )
            await execute_job(sessions, initial)
            old_report = copy.deepcopy(await get_run(sessions, scope, initial["id"]))
            assert old_report["ai_provenance"]["user_edited"] is False
            async with sessions() as db:
                saved = await api.create_analysis_pipeline(
                    api.PipelineCreateRequest(
                        run_id=initial["id"], title="Synthetic Aira reusable method"
                    ),
                    db,
                    scope.analyst,
                )
            original = copy.deepcopy(saved["revisions"][0])
            assert (
                original["provenance"]["ai_provenance"] == old_report["ai_provenance"]
            )
            reused = await preview(sessions, scope, pipeline_revision_id=original["id"])
            assert reused["ai_provenance"]["inherited"] is True
            assert reused["ai_provenance"]["user_edited"] is False
            async with sessions() as db:
                revision = await api.revise_analysis_pipeline(
                    saved["id"],
                    api.PipelineReviseRequest(
                        expected_revision=1, recipe=recipe(chart="line")
                    ),
                    db,
                    scope.analyst,
                )
            provenance = revision["provenance"]["ai_provenance"]
            assert provenance["inherited"] is True and provenance["user_edited"] is True
            assert provenance["request_id"] == str(generated.id)
            assert provenance["generation"]["recipe"]["chart"] == "bar"
            assert provenance["digest"] == canonical_digest(
                {key: value for key, value in provenance.items() if key != "digest"}
            )
            edited_preview = await preview(
                sessions,
                scope,
                selected_recipe=recipe(chart="line"),
                pipeline_revision_id=revision["id"],
            )
            rerun = await confirm(sessions, scope, edited_preview)
            await execute_job(sessions, rerun)
            edited_report = await get_run(sessions, scope, rerun["id"])
            assert edited_report["ai_provenance"] == provenance
            assert edited_report["recipe"]["chart"] == "line"
            assert group_stats(edited_report["result"])["A"]["mean"] == 3
            async with sessions() as db:
                restored = await api.revise_analysis_pipeline(
                    saved["id"],
                    api.PipelineReviseRequest(expected_revision=2, recipe=recipe()),
                    db,
                    scope.analyst,
                )
                latest = await api.get_analysis_pipeline(
                    saved["id"], db, scope.analyst, Response()
                )
            # Returning to the generated recipe does not erase intervening edits.
            assert restored["provenance"]["ai_provenance"]["user_edited"] is True
            assert restored["provenance"]["ai_provenance"]["inherited"] is True
            assert latest["revisions"][-1] == original
            assert await get_run(sessions, scope, initial["id"]) == old_report
            assert (
                await read_request(sessions, scope, generated.id)
            ).output == generated.output
            assert provider.await_count == 1

    asyncio.run(exercise())


@pytest.mark.parametrize("question", ["", " \t\n "])
def test_blank_interpretation_question_uses_default_without_invalid_proposal(
    monkeypatch, question
):
    provider = AsyncMock(return_value=interpretation_output())
    monkeypatch.setattr(analysis_ai, "aira_structured_proposal", provider)

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            run = await confirm(sessions, scope, await preview(sessions, scope))
            await execute_job(sessions, run)
            explanation = await generate(
                sessions,
                scope,
                InterpretationRequest(id=uuid4(), question=question),
                analysis_id=run["id"],
            )
            assert explanation.state == "generated" and explanation.error is None
            assert (
                explanation.input_context["analysis_question"]
                == "Compare synthetic groups"
            )
            assert "Compare synthetic groups" in provider.call_args.args[0]
            assert explanation.output["observations"][0]["metrics"][0]["value"] == 2
            assert provider.await_count == 1

    asyncio.run(exercise())
