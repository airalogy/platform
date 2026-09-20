"""Real Knowledge scope publication, edit, source revocation and archival lifecycle.

Only synthetic fixtures are created. Writes, source permission changes and
Record soft deletion use shipped routers; no authorization or result is mocked.
Run serially against the dedicated migrated research-integration PostgreSQL.
"""

import asyncio
import os
from uuid import UUID

import pytest
from fastapi import HTTPException, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select

from app.config import config
from app.models.analysis_publication import AnalysisEvidencePublication
from app.models.knowledge import (
    KnowledgeFileLink,
    KnowledgeItem,
    OwnerScope,
    ResearchFile,
)
from app.models.record import Record
from app.models.research_asset import KnowledgeEvidenceLink, ResearchEvidence
from app.routers import access, analyses, analysis_publications, knowledge, records
from app.routers import research_assets as assets
from app.services.research_asset_visibility import (
    require_asset_snapshot_sources_readable,
    require_evidence_source_readable,
)
from tests.test_analysis_publication_postgres import (
    confirm,
    preview,
    publication_draft,
    setup_publication,
    suggestion,
    validate_evidence,
)
from tests.test_record_analysis_postgres import database

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Dedicated PostgreSQL is required for Knowledge publication lifecycle",
)


@pytest.fixture(autouse=True)
def manual_structured_permissions(monkeypatch):
    # Exercise the real inheritance API and its real legacy-role compatibility.
    # This changes deployment configuration, not any authorization implementation.
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "structured")
    monkeypatch.setattr(config, "AI_ENABLED", False)


async def published_analysis(sessions):
    f, run, task = await setup_publication(sessions)
    draft = publication_draft(task)
    published = await confirm(
        sessions, f, run, draft, await preview(sessions, f, run, draft)
    )
    await validate_evidence(sessions, f, published["evidence"])
    return f, run, task, published


async def review_note(sessions, f, note):
    async with sessions() as db:
        return jsonable_encoder(
            await knowledge.review_knowledge_item(
                UUID(note["id"]),
                knowledge.KnowledgeReviewParams(expected_revision=note["revision"]),
                db,
                f.scope.owner,
            )
        )


async def load_note(sessions, identity, user):
    async with sessions() as db:
        return jsonable_encoder(
            await knowledge.get_knowledge_item(
                UUID(str(identity)),
                db,
                user,
            )
        )


async def set_second_protocol_inheritance(sessions, f, inherit):
    async with sessions() as db:
        result = await access.update_protocol_inheritance(
            f.second.protocol.id,
            access.InheritanceParams(inherit_permissions=inherit),
            f.scope.owner,
            db,
        )
        assert result["inherit_permissions"] is inherit


def test_analysis_publication_reviewed_knowledge_publishes_new_lab_scope_and_exact_lineage():
    async def scenario():
        async with database() as sessions:
            f, run, task, published = await published_analysis(sessions)
            source = await review_note(
                sessions, f, await suggestion(sessions, f, task, published["evidence"])
            )
            assert source["state"] == "reviewed"
            assert len(source["evidence_sources"]) == 1
            source_link = source["evidence_sources"][0]
            assert source_link["evidence_id"] == published["evidence"]["id"]
            params = knowledge.KnowledgePublishParams(
                target_scope_type=OwnerScope.LAB,
                target_lab_id=f.scope.lab.id,
            )
            async with sessions() as db:
                prepared = await knowledge.preview_knowledge_publish(
                    UUID(source["id"]),
                    params,
                    db,
                    f.scope.owner,
                )
                assert prepared["impact"]["new_state"] == "draft"
                assert prepared["impact"]["private_files_omitted"] == []
                assert jsonable_encoder(
                    prepared["impact"]["analysis_evidence_sources"]
                ) == [
                    {
                        "evidence_id": source_link["evidence_id"],
                        "source_snapshot": source_link["source_snapshot"],
                    }
                ]
                copied = jsonable_encoder(
                    await knowledge.confirm_knowledge_publish(
                        UUID(source["id"]),
                        knowledge.KnowledgePublishConfirmParams(
                            **params.model_dump(),
                            expected_revision=source["revision"],
                            preview_digest=prepared["preview_digest"],
                        ),
                        db,
                        f.scope.owner,
                    )
                )
            assert copied["id"] != source["id"]
            assert copied["derived_from_id"] == source["id"]
            assert copied["scope_type"] == "lab" and copied["project_id"] is None
            assert copied["lab_id"] == str(f.scope.lab.id)
            assert copied["state"] == "draft" and copied["revision"] == 1
            assert copied["body"] == source["body"]
            assert copied["research_file_ids"] == []
            assert copied["evidence_sources"] == [
                {
                    **source_link,
                    "knowledge_revision": 1,
                }
            ]
            # A Lab member who cannot read the owner-authored source Records
            # must not obtain the unpublished candidate via its wider scope.
            with pytest.raises(HTTPException) as private_draft:
                await load_note(sessions, copied["id"], f.scope.recorder)
            assert private_draft.value.status_code in {403, 404}

            adopted = await review_note(sessions, f, copied)
            readable = await load_note(sessions, adopted["id"], f.scope.recorder)
            assert (
                readable["state"] == "reviewed" and readable["body"] == source["body"]
            )
            assert readable["evidence_sources"] == []
            assert readable["research_file_ids"] == []
            async with sessions() as db:
                with pytest.raises(HTTPException) as private_report:
                    await analyses.get_record_analysis(
                        UUID(run["id"]),
                        db,
                        f.scope.recorder,
                        Response(),
                    )
                assert private_report.value.status_code == 404
                original = await knowledge.get_knowledge_item(
                    UUID(source["id"]),
                    db,
                    f.scope.owner,
                )
                assert original["state"] == "reviewed"
                assert original["scope_type"] == "project"
                assert original["revision"] == source["revision"]
                links = list(
                    (
                        await db.scalars(
                            select(KnowledgeEvidenceLink).where(
                                KnowledgeEvidenceLink.knowledge_item_id
                                == UUID(copied["id"]),
                            )
                        )
                    ).all()
                )
                assert len(links) == 1
                assert links[0].knowledge_revision == 1
                assert (
                    jsonable_encoder(links[0].source_snapshot)
                    == source_link["source_snapshot"]
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(KnowledgeFileLink)
                        .where(
                            KnowledgeFileLink.knowledge_item_id.in_(
                                [UUID(source["id"]), UUID(copied["id"])]
                            ),
                        )
                    )
                    == 0
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ResearchFile)
                        .where(
                            ResearchFile.lab_id == f.scope.lab.id,
                        )
                    )
                    == 0
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(Record)
                        .where(
                            Record.protocol_id.in_(
                                [f.scope.protocol.id, f.second.protocol.id]
                            ),
                        )
                    )
                    == 4
                )

    asyncio.run(scenario())


def test_analysis_publication_reviewed_edit_restores_all_source_checks_for_draft():
    async def scenario():
        async with database() as sessions:
            f, _run, task, published = await published_analysis(sessions)
            source = await review_note(
                sessions, f, await suggestion(sessions, f, task, published["evidence"])
            )
            async with sessions() as db:
                updated = jsonable_encoder(
                    await knowledge.update_knowledge_item(
                        UUID(source["id"]),
                        knowledge.KnowledgeUpdateParams(
                            expected_revision=source["revision"],
                            body=source["body"] + " This revision needs a new review.",
                            change_summary="Reassess the interpretation without changing its sources",
                        ),
                        db,
                        f.scope.owner,
                    )
                )
            assert updated["state"] == "draft"
            assert updated["revision"] == source["revision"] + 1
            assert (
                updated["reviewed_at"] is None
                and updated["reviewed_by_user_id"] is None
            )
            assert updated["evidence_sources"] == source["evidence_sources"]
            assert (await load_note(sessions, updated["id"], f.scope.analyst))[
                "body"
            ] == updated["body"]

            await set_second_protocol_inheritance(sessions, f, False)
            with pytest.raises(HTTPException) as denied:
                await load_note(sessions, updated["id"], f.scope.analyst)
            assert denied.value.status_code in {403, 404}
            async with sessions() as db:
                found = await knowledge.list_knowledge_items(
                    db_session=db,
                    current_user=f.scope.analyst,
                    scope_type=OwnerScope.PROJECT,
                    lab_id=f.scope.lab.id,
                    project_id=f.scope.project.id,
                    q=updated["title"],
                    kind=None,
                    state=None,
                    page=1,
                    page_size=100,
                )
                assert found["items"] == []
                bundle = await assets.get_task_research_assets(
                    task.id, f.scope.analyst, db
                )
                assert bundle["knowledge_items"] == []
                assert bundle["evidence"] == []
            # Restoring the actual source grant makes the same revision usable;
            # neither editing nor revocation erased its historical lineage.
            await set_second_protocol_inheritance(sessions, f, True)
            restored = await load_note(sessions, updated["id"], f.scope.analyst)
            assert restored["body"] == updated["body"]
            assert restored["revision"] == updated["revision"]
            assert restored["evidence_sources"] == source["evidence_sources"]

    asyncio.run(scenario())


def test_analysis_publication_archived_record_blocks_candidates_and_new_promotions():
    async def scenario():
        async with database() as sessions:
            f, run, task, published = await published_analysis(sessions)
            reviewed = await review_note(
                sessions, f, await suggestion(sessions, f, task, published["evidence"])
            )
            pending = await suggestion(sessions, f, task, published["evidence"])
            before = await load_note(sessions, reviewed["id"], f.scope.owner)
            assert len(before["evidence_sources"]) == 1
            assert (
                before["evidence_sources"][0]["evidence_id"]
                == published["evidence"]["id"]
            )
            publication_request = publication_draft(
                task, title="Another explicit selected result"
            )
            publication_preview = await preview(sessions, f, run, publication_request)
            scope_request = knowledge.KnowledgePublishParams(
                target_scope_type=OwnerScope.LAB,
                target_lab_id=f.scope.lab.id,
            )
            async with sessions() as db:
                scope_preview = await knowledge.preview_knowledge_publish(
                    UUID(reviewed["id"]),
                    scope_request,
                    db,
                    f.scope.owner,
                )
                sealed_bundle = jsonable_encoder(
                    await assets.get_task_research_assets(
                        task.id,
                        f.scope.owner,
                        db,
                    )
                )
                # Archive the latest real Record through the normal soft-delete
                # endpoint; no synthetic mutation of permission/result payloads.
                newest = f.records[-1]
                deleted = await records.delete_protocol_record(
                    f.second.protocol.id,
                    newest.id,
                    newest.version,
                    db,
                    f.scope.owner,
                )
                assert deleted["message"] == "success"
            async with sessions() as db:
                archived = await db.get(Record, (newest.id, newest.version))
                assert archived.deleted_at is not None
                with pytest.raises(HTTPException) as unavailable:
                    await analysis_publications.get_published_analysis_evidence(
                        UUID(published["publication"]["id"]),
                        db,
                        f.scope.owner,
                        Response(),
                    )
                assert unavailable.value.status_code in {403, 404, 409}
                evidence = await db.get(
                    ResearchEvidence, UUID(published["evidence"]["id"])
                )
                with pytest.raises(HTTPException):
                    await require_evidence_source_readable(db, evidence, f.scope.owner)
                with pytest.raises(HTTPException):
                    await knowledge.get_knowledge_item(
                        UUID(pending["id"]), db, f.scope.owner
                    )
                with pytest.raises(HTTPException):
                    await knowledge.review_knowledge_item(
                        UUID(pending["id"]),
                        knowledge.KnowledgeReviewParams(
                            expected_revision=pending["revision"]
                        ),
                        db,
                        f.scope.owner,
                    )
                saved = await knowledge.get_knowledge_item(
                    UUID(reviewed["id"]), db, f.scope.owner
                )
                assert (
                    saved["state"] == "reviewed" and saved["body"] == reviewed["body"]
                )
                assert saved["evidence_sources"] == []
                with pytest.raises(HTTPException):
                    await knowledge.preview_knowledge_publish(
                        UUID(reviewed["id"]),
                        scope_request,
                        db,
                        f.scope.owner,
                    )
                with pytest.raises(HTTPException):
                    await knowledge.confirm_knowledge_publish(
                        UUID(reviewed["id"]),
                        knowledge.KnowledgePublishConfirmParams(
                            **scope_request.model_dump(),
                            expected_revision=reviewed["revision"],
                            preview_digest=scope_preview["preview_digest"],
                        ),
                        db,
                        f.scope.owner,
                    )
                bundle = jsonable_encoder(
                    await assets.get_task_research_assets(task.id, f.scope.owner, db)
                )
                assert bundle["evidence"] == []
                assert [item["id"] for item in bundle["knowledge_items"]] == [
                    reviewed["id"]
                ]
                assert bundle["knowledge_items"][0]["evidence"] == []
                with pytest.raises(HTTPException):
                    await require_asset_snapshot_sources_readable(
                        db,
                        task_id=task.id,
                        payload=sealed_bundle,
                        user=f.scope.owner,
                    )
            with pytest.raises(HTTPException):
                await confirm(
                    sessions, f, run, publication_request, publication_preview
                )
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisEvidencePublication)
                        .where(
                            AnalysisEvidencePublication.task_id == task.id,
                        )
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ResearchEvidence)
                        .where(
                            ResearchEvidence.task_id == task.id,
                        )
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(KnowledgeItem)
                        .where(
                            KnowledgeItem.lab_id == f.scope.lab.id,
                        )
                    )
                    == 2
                )
                persisted = await db.get(KnowledgeItem, UUID(pending["id"]))
                assert (
                    persisted.state == "suggested"
                    and persisted.revision == pending["revision"]
                )

    asyncio.run(scenario())
