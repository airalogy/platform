"""Real computed results become explicit Evidence and reviewed Knowledge copies."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError

from app.config import config
from app.models.analysis_publication import AnalysisEvidencePublication
from app.models.protocol import Protocol
from app.models.research import ResearchAction, ResearchRun, ResearchTask
from app.models.research_asset import DataAsset, ResearchEvidence
from app.routers import (
    analyses,
    analysis_publications,
    knowledge,
    project_analyses,
    research_tasks,
)
from app.routers import research_assets as assets
from app.services.analysis_publications import (
    AnalysisPublicationConfirm,
    AnalysisPublicationDraft,
    sign_preview,
)
from app.services.research_asset_visibility import require_evidence_source_readable
from tests.test_project_analyses_postgres import (
    computed_project,
    human_interpretation,
    project_scope,
)
from tests.test_record_analysis_postgres import database

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Dedicated PostgreSQL is required for analysis publication acceptance",
)


@pytest.fixture(autouse=True)
def manual_flat_permissions(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", False)


async def setup_publication(sessions, *, relational=False):
    from tests.test_project_analyses_postgres import project_recipe

    f = await project_scope(sessions, public=True)
    run = await computed_project(
        sessions, f, recipe=project_recipe(relational=relational)
    )
    async with sessions() as db:
        task = ResearchTask(
            id=uuid4(),
            lab_id=f.scope.lab.id,
            project_id=f.scope.project.id,
            title="Synthetic two-source evidence review",
            goal="Check known values, not scientific validity",
            owner_user_id=f.scope.analyst.id,
            created_by_user_id=f.scope.analyst.id,
        )
        db.add(task)
        await db.commit()
    return f, run, task


def publication_draft(task, **changes):
    return AnalysisPublicationDraft(
        **{
            "task_id": task.id,
            "title": "Selected synthetic observations",
            "summary": "Only a synthetic calculation; causality is not established.",
            "sections": [
                {"section_id": "source:first", "fields": ["value"]},
                {"section_id": "source:second", "fields": ["value"]},
            ],
            **changes,
        }
    )


async def preview(sessions, f, run, draft):
    async with sessions() as db:
        return await analysis_publications.preview_selected_analysis_publication(
            UUID(run["id"]), draft, db, f.scope.analyst, Response()
        )


async def confirm(sessions, f, run, draft, prepared, *, key=None):
    async with sessions() as db:
        return jsonable_encoder(
            await analysis_publications.publish_selected_analysis_evidence(
                UUID(run["id"]),
                AnalysisPublicationConfirm(
                    **draft.model_dump(),
                    preview_digest=prepared["preview_digest"],
                    preview_token=prepared["preview_token"],
                    client_idempotency_key=key or uuid4(),
                ),
                db,
                f.scope.analyst,
                Response(),
            )
        )


async def suggestion(sessions, f, task, evidence, *, expect_pending=False):
    draft = assets.KnowledgeSuggestionDraft(
        task_id=task.id,
        title="Synthetic reusable observation",
        body="The two known synthetic means are 3 and 15; no causal conclusion.",
        evidence_ids=[UUID(evidence["id"])],
        kind="finding",
    )
    async with sessions() as db:
        if expect_pending:
            with pytest.raises(HTTPException) as rejected:
                await assets.preview_knowledge_suggestion(draft, f.scope.analyst, db)
            assert rejected.value.status_code in {409, 422}
            return None
        prepared = await assets.preview_knowledge_suggestion(draft, f.scope.analyst, db)
        return jsonable_encoder(
            await assets.create_knowledge_suggestion(
                assets.KnowledgeSuggestionCreate(
                    **draft.model_dump(), preview_digest=prepared["preview_digest"]
                ),
                f.scope.analyst,
                db,
            )
        )


async def validate_evidence(sessions, f, evidence):
    async with sessions() as db:
        return await assets.review_evidence(
            UUID(evidence["id"]),
            assets.EvidenceReview(
                expected_quality_state="pending",
                quality_state="validated",
                validation_report={"synthetic": True},
            ),
            f.scope.owner,
            db,
        )


def test_analysis_publication_real_worker_to_evidence_and_reviewed_knowledge():
    async def scenario():
        async with database() as sessions:
            f, run, task = await setup_publication(sessions, relational=True)
            async with sessions() as db:
                interpretation = (
                    await project_analyses.append_project_analysis_interpretation(
                        UUID(run["id"]),
                        human_interpretation(run["result_digest"]),
                        db,
                        f.scope.analyst,
                        Response(),
                    )
                )
            draft = publication_draft(
                task, interpretation_revision_id=interpretation["id"]
            )
            prepared = await preview(sessions, f, run, draft)
            snapshot = prepared["publication"]
            assert prepared["effect"]["raw_records_shared"] is False
            assert prepared["effect"]["original_report_remains_private"] is True
            assert [
                item["report"]["groups"][0]["fields"]["value"]["mean"]
                for item in snapshot["sections"]
            ] == [3, 15]
            assert snapshot["join_audit"]["output_rows"] == 2
            assert snapshot["interpretation"]["content"]["judgement"] == "inconclusive"
            assert sum(len(source["records"]) for source in snapshot["sources"]) == 4
            assert run["question"] not in json.dumps(snapshot)
            assert "source_selection" not in json.dumps(snapshot)
            assert all(
                "data" not in record
                for source in snapshot["sources"]
                for record in source["records"]
            )
            published = await confirm(sessions, f, run, draft, prepared)
            evidence = published["evidence"]
            assert evidence["quality_state"] == "pending"
            assert (
                evidence["kind"] == "analysis"
                and evidence["artifact_type"] == "analysis_publication"
            )
            assert evidence["run_id"] is None and evidence["action_id"] is None
            publication_id = UUID(published["publication"]["id"])
            # A different reviewer reads only the explicitly published copy.
            async with sessions() as db:
                copied = jsonable_encoder(
                    await analysis_publications.get_published_analysis_evidence(
                        publication_id, db, f.scope.owner, Response()
                    )
                )
                assert copied["snapshot"] == snapshot
                with pytest.raises(HTTPException) as private:
                    await analyses.get_record_analysis(
                        UUID(run["id"]), db, f.scope.owner, Response()
                    )
                assert private.value.status_code == 404
                with pytest.raises(HTTPException):
                    await analysis_publications.get_published_analysis_evidence(
                        publication_id, db, f.scope.outsider, Response()
                    )
            await suggestion(sessions, f, task, evidence, expect_pending=True)
            await validate_evidence(sessions, f, evidence)
            note = await suggestion(sessions, f, task, evidence)
            assert note["state"] == "suggested"
            async with sessions() as db:
                reviewed = await knowledge.review_knowledge_item(
                    UUID(note["id"]),
                    knowledge.KnowledgeReviewParams(expected_revision=note["revision"]),
                    db,
                    f.scope.owner,
                )
                assert reviewed["state"] == "reviewed"
            async with sessions() as db:
                loaded = await knowledge.get_knowledge_item(
                    UUID(note["id"]), db, f.scope.analyst
                )
                assert loaded["state"] == "reviewed" and loaded["body"] == note["body"]
                detail = await research_tasks.get_research_task(
                    task.id, f.scope.analyst, db
                )
                assert str(detail["id"]) == str(task.id)
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ResearchRun)
                        .where(ResearchRun.task_id == task.id)
                    )
                    == 0
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(DataAsset)
                        .where(DataAsset.project_id == f.scope.project.id)
                    )
                    == 0
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ResearchAction)
                        .join(ResearchRun, ResearchRun.id == ResearchAction.run_id)
                        .where(ResearchRun.task_id == task.id)
                    )
                    == 0
                )

    asyncio.run(scenario())


def test_analysis_publication_exact_preview_concurrent_confirmation_and_database_immutability():
    async def scenario():
        async with database() as sessions:
            f, run, task = await setup_publication(sessions)
            draft = publication_draft(task)
            prepared = await preview(sessions, f, run, draft)
            key = uuid4()
            first, second = await asyncio.gather(
                confirm(sessions, f, run, draft, prepared, key=key),
                confirm(sessions, f, run, draft, prepared, key=key),
            )
            assert first["publication"]["id"] == second["publication"]["id"]
            assert first["evidence"]["id"] == second["evidence"]["id"]
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisEvidencePublication)
                        .where(
                            AnalysisEvidencePublication.analysis_run_id
                            == UUID(run["id"])
                        )
                    )
                    == 1
                )
                with pytest.raises(DBAPIError):
                    await db.execute(
                        update(AnalysisEvidencePublication)
                        .where(
                            AnalysisEvidencePublication.id
                            == UUID(first["publication"]["id"])
                        )
                        .values(title="Mutated result")
                    )
                await db.rollback()
            async with sessions() as db:
                connection = await db.connection()

                def downgrade(connection):
                    with Operations.context(MigrationContext.configure(connection)):
                        import_module(
                            "migrations.versions.0072_analysis_publications"
                        ).downgrade()

                with pytest.raises(RuntimeError, match="Cannot downgrade"):
                    await connection.run_sync(downgrade)
                await db.rollback()
            with pytest.raises(HTTPException) as conflict:
                await confirm(
                    sessions,
                    f,
                    run,
                    publication_draft(task, title="Different selection"),
                    prepared,
                    key=key,
                )
            assert conflict.value.status_code == 409
            async with sessions() as db:
                current = await db.get(ResearchTask, task.id)
                current.title = "Changed target after preview"
                current.revision += 1  # Match the ordinary Task update contract.
                await db.commit()
            with pytest.raises(HTTPException) as changed:
                await confirm(sessions, f, run, draft, prepared)
            assert changed.value.status_code == 409

    asyncio.run(scenario())


def test_analysis_publication_expired_retry_recovers_only_the_saved_authorized_request():
    async def scenario():
        async with database() as sessions:
            f, run, task = await setup_publication(sessions)
            draft = publication_draft(task)
            prepared = await preview(sessions, f, run, draft)
            key = uuid4()
            saved = await confirm(sessions, f, run, draft, prepared, key=key)
            expired_token, expires_at = sign_preview(
                user_id=f.scope.analyst.id,
                analysis_id=UUID(run["id"]),
                digest=prepared["preview_digest"],
                now=datetime.now(UTC) - timedelta(hours=1),
            )
            expired = {
                **prepared,
                "preview_token": expired_token,
                "expires_at": expires_at,
            }
            recovered = await confirm(sessions, f, run, draft, expired, key=key)
            assert recovered == saved
            with pytest.raises(HTTPException) as new_request:
                await confirm(sessions, f, run, draft, expired)
            assert new_request.value.status_code == 409
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisEvidencePublication)
                        .where(AnalysisEvidencePublication.task_id == task.id)
                    )
                    == 1
                )
                second = await db.get(Protocol, f.second.protocol.id)
                second.inherit_permissions = False
                await db.commit()
            with pytest.raises(HTTPException) as revoked_retry:
                await confirm(sessions, f, run, draft, expired, key=key)
            assert revoked_retry.value.status_code in {403, 404}

    asyncio.run(scenario())


def test_analysis_publication_one_revoked_source_hides_pending_knowledge_but_preserves_reviewed_text():
    async def scenario():
        async with database() as sessions:
            f, run, task = await setup_publication(sessions)
            draft = publication_draft(task)
            published = await confirm(
                sessions, f, run, draft, await preview(sessions, f, run, draft)
            )
            await validate_evidence(sessions, f, published["evidence"])
            reviewed = await suggestion(sessions, f, task, published["evidence"])
            pending = await suggestion(sessions, f, task, published["evidence"])
            async with sessions() as db:
                await knowledge.review_knowledge_item(
                    UUID(reviewed["id"]),
                    knowledge.KnowledgeReviewParams(
                        expected_revision=reviewed["revision"]
                    ),
                    db,
                    f.scope.owner,
                )
            async with sessions() as db:
                before_revocation = await knowledge.get_knowledge_item(
                    UUID(reviewed["id"]), db, f.scope.analyst
                )
                assert len(before_revocation["evidence_sources"]) == 1
                source_link = before_revocation["evidence_sources"][0]
                assert str(source_link["evidence_id"]) == published["evidence"]["id"]
                assert (
                    source_link["source_snapshot"]["artifact_type"]
                    == "analysis_publication"
                )
                assert (
                    str(source_link["source_snapshot"]["artifact_id"])
                    == published["publication"]["id"]
                )
                second = await db.get(Protocol, f.second.protocol.id)
                second.inherit_permissions = False
                await db.commit()
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await analysis_publications.get_published_analysis_evidence(
                        UUID(published["publication"]["id"]),
                        db,
                        f.scope.analyst,
                        Response(),
                    )
                evidence = await db.get(
                    ResearchEvidence, UUID(published["evidence"]["id"])
                )
                with pytest.raises(HTTPException):
                    await require_evidence_source_readable(
                        db, evidence, f.scope.analyst
                    )
                with pytest.raises(HTTPException):
                    await knowledge.get_knowledge_item(
                        UUID(pending["id"]), db, f.scope.analyst
                    )
                saved = await knowledge.get_knowledge_item(
                    UUID(reviewed["id"]), db, f.scope.analyst
                )
                assert (
                    saved["body"] == reviewed["body"] and saved["state"] == "reviewed"
                )
                assert saved["evidence_sources"] == []

    asyncio.run(scenario())
