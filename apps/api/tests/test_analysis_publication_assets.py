"""A published analysis cannot bypass Evidence or Knowledge source permissions."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.libs.lab_force_delete import _delete_lab_analysis_publications
from app.models.knowledge import KnowledgeItem, KnowledgeRevision, OwnerScope
from app.models.project import Project
from app.models.research import ResearchTask
from app.models.research_asset import KnowledgeEvidenceLink, ResearchEvidence
from app.routers import knowledge, research_log
from app.routers import research_assets as api
from app.services import knowledge as knowledge_service
from app.services import research_asset_visibility as visibility
from app.services import research_assets
from app.services.knowledge import ScopeContext


def rows(values):
    return SimpleNamespace(all=lambda: values)


def evidence_link(*, artifact_type="analysis_publication", revision=1):
    evidence = SimpleNamespace(
        id=uuid4(),
        task_id=uuid4(),
        artifact_type=artifact_type,
        artifact_id=str(uuid4()),
        artifact_version="a" * 64,
        quality_state="validated",
    )
    link = SimpleNamespace(
        id=uuid4(),
        evidence_id=evidence.id,
        knowledge_revision=revision,
        source_snapshot={
            key: str(getattr(evidence, key))
            for key in (
                "id",
                "task_id",
                "artifact_type",
                "artifact_id",
                "artifact_version",
            )
        },
    )
    return evidence, link


def test_analysis_knowledge_promotion_rechecks_all_inherited_sources(monkeypatch):
    analysis, first = evidence_link(revision=1)
    other, second = evidence_link(artifact_type="record", revision=2)
    item = SimpleNamespace(id=uuid4(), revision=3)
    db = SimpleNamespace(
        scalars=AsyncMock(return_value=rows([first, second])),
        get=AsyncMock(side_effect=[analysis, other]),
    )
    check = AsyncMock()
    monkeypatch.setattr(visibility, "require_evidence_source_readable", check)
    user = object()
    assert asyncio.run(
        visibility.require_analysis_knowledge_evidence_readable(
            db,
            item,
            user,
        )
    ) == [first, second]
    assert [call.args for call in check.await_args_list] == [
        (db, analysis, user),
        (db, other, user),
    ]


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "changed_id",
        "changed_type",
        "future_revision",
        "pending",
        "revoked",
    ],
)
def test_analysis_knowledge_promotion_fails_closed(monkeypatch, change):
    analysis, link = evidence_link()
    if change == "changed_id":
        link.source_snapshot["artifact_id"] = str(uuid4())
    elif change == "changed_type":
        link.source_snapshot["artifact_type"] = "record"
    elif change == "future_revision":
        link.knowledge_revision = 2
    elif change == "pending":
        analysis.quality_state = "pending"
    check = AsyncMock(
        side_effect=HTTPException(403, "Revoked") if change == "revoked" else None
    )
    monkeypatch.setattr(visibility, "require_evidence_source_readable", check)
    db = SimpleNamespace(
        scalars=AsyncMock(return_value=rows([link])),
        get=AsyncMock(return_value=None if change == "missing" else analysis),
    )
    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            visibility.require_analysis_knowledge_evidence_readable(
                db,
                SimpleNamespace(id=uuid4(), revision=1),
                object(),
            )
        )
    assert denied.value.status_code == (403 if change == "revoked" else 409)


def test_non_analysis_knowledge_keeps_existing_promotion_contract(monkeypatch):
    evidence, link = evidence_link(artifact_type="record")
    db = SimpleNamespace(
        scalars=AsyncMock(return_value=rows([link])),
        get=AsyncMock(return_value=evidence),
    )
    check = AsyncMock(side_effect=AssertionError("Unrelated behavior changed"))
    monkeypatch.setattr(visibility, "require_evidence_source_readable", check)
    assert (
        asyncio.run(
            visibility.require_analysis_knowledge_evidence_readable(
                db,
                SimpleNamespace(id=uuid4(), revision=1),
                object(),
            )
        )
        == []
    )
    check.assert_not_awaited()


@pytest.mark.parametrize("state", ["suggested", "draft", "reviewed"])
def test_knowledge_scope_then_candidate_source_authorization(monkeypatch, state):
    item = SimpleNamespace(
        id=uuid4(),
        state=state,
        scope_type="project",
        lab_id=uuid4(),
        project_id=uuid4(),
        visibility="project",
    )
    scope = object()
    scoped = AsyncMock(return_value=scope)
    monkeypatch.setattr(knowledge_service, "resolve_scope", scoped)
    check = AsyncMock(side_effect=HTTPException(403, "Source revoked"))
    monkeypatch.setattr(
        visibility, "require_analysis_knowledge_evidence_readable", check
    )
    operation = knowledge_service.authorize_knowledge_item(object(), object(), item)
    if state == "reviewed":
        assert asyncio.run(operation) is scope
        check.assert_not_awaited()
    else:
        with pytest.raises(HTTPException):
            asyncio.run(operation)
        check.assert_awaited_once()
    scoped.assert_awaited_once()
    scoped.side_effect = HTTPException(403, "No Project membership")
    check.reset_mock()
    with pytest.raises(HTTPException):
        asyncio.run(
            knowledge_service.authorize_knowledge_item(object(), object(), item)
        )
    check.assert_not_awaited()


def test_cyclic_candidate_lineage_is_denied_and_guard_resets(monkeypatch):
    evidence, link = evidence_link()
    item = SimpleNamespace(id=uuid4(), revision=1)
    db = SimpleNamespace(
        scalars=AsyncMock(return_value=rows([link])),
        get=AsyncMock(return_value=evidence),
    )

    async def cycle(db, evidence, user):
        await visibility.require_analysis_knowledge_evidence_readable(db, item, user)

    monkeypatch.setattr(visibility, "require_evidence_source_readable", cycle)
    with pytest.raises(HTTPException, match="cyclic") as denied:
        asyncio.run(
            visibility.require_analysis_knowledge_evidence_readable(db, item, object())
        )
    assert denied.value.status_code == 409
    monkeypatch.setattr(visibility, "require_evidence_source_readable", AsyncMock())
    assert asyncio.run(
        visibility.require_analysis_knowledge_evidence_readable(db, item, object())
    ) == [link]


def test_knowledge_keyword_search_omits_denied_candidate_payload(monkeypatch):
    item = SimpleNamespace(id=uuid4(), title="private analysis finding")
    db = SimpleNamespace(scalars=AsyncMock(return_value=rows([item])))
    scope = ScopeContext(OwnerScope.PROJECT, None, uuid4(), uuid4())
    monkeypatch.setattr(knowledge, "resolve_scope", AsyncMock(return_value=scope))
    monkeypatch.setattr(
        knowledge,
        "authorize_knowledge_item",
        AsyncMock(side_effect=HTTPException(403, "Source revoked")),
    )
    payload = AsyncMock(side_effect=AssertionError("Private candidate serialized"))
    monkeypatch.setattr(knowledge, "_knowledge_payload", payload)
    result = asyncio.run(
        knowledge.list_knowledge_items(
            db_session=db,
            current_user=object(),
            scope_type=OwnerScope.PROJECT,
            lab_id=scope.lab_id,
            project_id=scope.project_id,
            q="private",
            kind=None,
            state=None,
            page=1,
            page_size=20,
        )
    )
    assert result["items"] == []
    payload.assert_not_awaited()


def test_log_does_not_disclose_denied_candidate_title(monkeypatch):
    item = SimpleNamespace(id=uuid4(), title="secret analysis result")
    row = SimpleNamespace(
        source_id=str(item.id),
        source_type="knowledge",
        source_version="1",
        event_type="knowledge.created",
        actor_user_id=None,
        lab_id=None,
        project_id=None,
        occurred_at=datetime.now(UTC),
    )
    db = SimpleNamespace(get=AsyncMock(return_value=item))
    check = AsyncMock(side_effect=HTTPException(403, "Source revoked"))
    monkeypatch.setattr(knowledge_service, "authorize_knowledge_item", check)
    assert asyncio.run(research_log._system_event_payload(db, row, object())) is None
    check.assert_awaited_once()


def test_log_filters_candidate_identity_before_counting_or_paging(monkeypatch):
    item = SimpleNamespace(id=uuid4())
    result_rows = MagicMock()
    result_rows.unique.return_value = rows([item])
    db = SimpleNamespace(scalars=AsyncMock(return_value=result_rows))
    scope = research_log.LogScopeContext(
        research_log.ResearchLogScope.PROJECT,
        None,
        SimpleNamespace(id=uuid4()),
        SimpleNamespace(id=uuid4()),
    )
    monkeypatch.setattr(
        knowledge_service,
        "authorize_knowledge_item",
        AsyncMock(side_effect=HTTPException(403, "Source revoked")),
    )
    assert asyncio.run(
        research_log._hidden_analysis_knowledge_ids(db, object(), scope)
    ) == [str(item.id)]
    query = str(db.scalars.await_args.args[0])
    assert "knowledge_items.project_id =" in query
    assert "knowledge_items.state IN" in query
    assert "research_evidence.artifact_type =" in query


def test_log_applies_candidate_exclusions_to_both_count_and_page(monkeypatch):
    hidden_id = str(uuid4())
    scope = research_log.LogScopeContext(
        research_log.ResearchLogScope.PROJECT,
        None,
        SimpleNamespace(id=uuid4()),
        SimpleNamespace(id=uuid4()),
    )
    monkeypatch.setattr(research_log, "_scope_context", AsyncMock(return_value=scope))
    monkeypatch.setattr(
        research_log,
        "_hidden_analysis_knowledge_ids",
        AsyncMock(return_value=[hidden_id]),
    )
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=0), execute=AsyncMock(return_value=rows([]))
    )
    result = asyncio.run(
        research_log.get_research_log_timeline(
            current_user=object(),
            db_session=db,
            scope_type=scope.scope_type,
            lab_id=scope.lab_id,
            project_id=scope.project_id,
            source="all",
            actor_user_id=None,
            date_from=None,
            date_to=None,
            page=1,
            page_size=20,
        )
    )
    assert result["items"] == []
    assert result["total_count"] == 0
    for query in [db.scalar.await_args.args[0], db.execute.await_args.args[0]]:
        compiled = query.compile()
        assert "research_log_events.source_id NOT IN" in str(compiled)
        assert [hidden_id] in compiled.params.values()


def test_bundle_omits_candidate_prose_when_scope_guard_rejects_source(monkeypatch):
    item = KnowledgeItem(id=uuid4(), state="draft", title="Private unpublished result")
    _evidence, link = evidence_link()
    link.knowledge_item_id = item.id
    db = SimpleNamespace(
        get=AsyncMock(return_value=object()),
        scalars=AsyncMock(
            side_effect=[
                rows([]),
                rows([]),
                rows([]),
                rows([link]),
                rows([item]),
                rows([]),
            ]
        ),
    )
    check = AsyncMock(side_effect=HTTPException(403, "Source revoked"))
    monkeypatch.setattr(knowledge_service, "authorize_knowledge_item", check)
    monkeypatch.setattr(
        research_assets, "visible_knowledge_evidence_links", AsyncMock(return_value=[])
    )
    result = asyncio.run(
        research_assets.research_asset_bundle(
            db, task_id=uuid4(), current_user=object()
        )
    )
    assert result["knowledge_items"] == []
    assert result["evidence"] == []
    check.assert_awaited_once()


def test_knowledge_review_refuses_revoked_sources_before_state_change(monkeypatch):
    item = SimpleNamespace(id=uuid4(), revision=2, scope_type="project", state="draft")
    db = SimpleNamespace(
        get=AsyncMock(return_value=item), commit=AsyncMock(), add=MagicMock()
    )
    monkeypatch.setattr(knowledge, "authorize_knowledge_item", AsyncMock())
    check = AsyncMock(side_effect=HTTPException(403, "Source revoked"))
    monkeypatch.setattr(
        visibility, "require_analysis_knowledge_evidence_readable", check
    )
    user = SimpleNamespace(id=uuid4())
    with pytest.raises(HTTPException):
        asyncio.run(
            knowledge.review_knowledge_item(
                item.id,
                knowledge.KnowledgeReviewParams(expected_revision=2),
                db,
                user,
            )
        )
    assert (item.state, item.revision) == ("draft", 2)
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
    check.assert_awaited_once_with(db, item, user)


def test_knowledge_publish_preview_and_confirmation_recheck_sources(monkeypatch):
    item = SimpleNamespace(id=uuid4(), revision=3)
    db = SimpleNamespace(
        get=AsyncMock(return_value=item), commit=AsyncMock(), add=MagicMock()
    )
    monkeypatch.setattr(knowledge, "authorize_knowledge_item", AsyncMock())
    check = AsyncMock(side_effect=HTTPException(403, "Source revoked"))
    monkeypatch.setattr(
        visibility, "require_analysis_knowledge_evidence_readable", check
    )
    for params, operation in [
        (
            knowledge.KnowledgePublishParams(target_scope_type="lab"),
            knowledge.preview_knowledge_publish,
        ),
        (
            knowledge.KnowledgePublishConfirmParams(
                target_scope_type="lab",
                expected_revision=3,
                preview_digest="a" * 64,
            ),
            knowledge.confirm_knowledge_publish,
        ),
    ]:
        with pytest.raises(HTTPException):
            asyncio.run(operation(item.id, params, db, SimpleNamespace(id=uuid4())))
    assert check.await_count == 2
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


def test_knowledge_publication_copies_exact_lineage_without_file_grants(monkeypatch):
    evidence, link = evidence_link()
    lab_id = uuid4()
    item = SimpleNamespace(
        id=uuid4(),
        revision=3,
        lab_id=lab_id,
        scope_type="project",
        kind="finding",
        title="Adopted result",
        body="Bounded conclusion",
        tags=[],
    )
    user = SimpleNamespace(id=uuid4())
    target = ScopeContext(OwnerScope.LAB, None, lab_id, None)
    monkeypatch.setattr(knowledge, "authorize_knowledge_item", AsyncMock())
    monkeypatch.setattr(knowledge, "resolve_scope", AsyncMock(return_value=target))
    check = AsyncMock(return_value=[link])
    monkeypatch.setattr(
        visibility, "require_analysis_knowledge_evidence_readable", check
    )
    db = SimpleNamespace(
        get=AsyncMock(return_value=item),
        scalars=AsyncMock(return_value=rows([])),
        scalar=AsyncMock(return_value=None),
        add=MagicMock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(
        knowledge, "snapshot_knowledge", lambda value: {"title": value.title}
    )
    monkeypatch.setattr(
        knowledge, "_knowledge_payload", AsyncMock(return_value={"saved": True})
    )
    params = knowledge.KnowledgePublishParams(
        target_scope_type="lab", target_lab_id=lab_id
    )

    async def publish():
        preview = await knowledge.preview_knowledge_publish(item.id, params, db, user)
        assert preview["impact"]["analysis_evidence_sources"] == [
            {
                "evidence_id": str(evidence.id),
                "source_snapshot": link.source_snapshot,
            }
        ]
        assert preview["impact"]["private_files_omitted"] == []
        return await knowledge.confirm_knowledge_publish(
            item.id,
            knowledge.KnowledgePublishConfirmParams(
                **params.model_dump(),
                expected_revision=3,
                preview_digest=preview["preview_digest"],
            ),
            db,
            user,
        )

    assert asyncio.run(publish()) == {"saved": True}
    saved = [call.args[0] for call in db.add.call_args_list]
    assert [type(row) for row in saved] == [
        KnowledgeItem,
        KnowledgeRevision,
        KnowledgeEvidenceLink,
    ]
    assert saved[0].derived_from_id == item.id
    assert saved[0].state == "draft"
    assert saved[2].evidence_id == evidence.id
    assert saved[2].source_snapshot == link.source_snapshot
    assert saved[2].knowledge_revision == 1
    assert check.await_count == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "observation"},
        {"run_id": uuid4()},
        {"action_id": uuid4()},
    ],
)
def test_publication_evidence_cannot_invent_execution_context(changes):
    with pytest.raises(ValidationError, match="no execution references"):
        api.EvidenceDraft(
            **{
                "task_id": uuid4(),
                "kind": "analysis",
                "artifact_type": "analysis_publication",
                "artifact_id": str(uuid4()),
                **changes,
            }
        )


def test_evidence_review_refreshes_locked_state_before_source_and_final_checks(
    monkeypatch,
):
    evidence = ResearchEvidence(
        id=uuid4(),
        task_id=uuid4(),
        artifact_type="analysis_publication",
        artifact_id=str(uuid4()),
        artifact_version="a" * 64,
        quality_state="validated",
    )
    operations = []

    async def locked_get(model, identity, **options):
        assert model is ResearchEvidence and identity == evidence.id
        assert options == {"with_for_update": True, "populate_existing": True}
        operations.append("locked_refresh")
        return evidence

    async def scoped(*args):
        operations.append("scope")
        return object()

    async def source(*args):
        operations.append("source")

    db = SimpleNamespace(get=AsyncMock(side_effect=locked_get), commit=AsyncMock())
    monkeypatch.setattr(api, "_task_context", scoped)
    monkeypatch.setattr(api, "require_evidence_source_readable", source)
    event = AsyncMock()
    monkeypatch.setattr(api, "emit_research_event", event)
    with pytest.raises(HTTPException) as conflict:
        asyncio.run(
            api.review_evidence(
                evidence.id,
                api.EvidenceReview(
                    expected_quality_state="pending", quality_state="rejected"
                ),
                SimpleNamespace(id=uuid4()),
                db,
            )
        )
    assert conflict.value.status_code == 409
    assert operations == ["locked_refresh", "scope", "source"]
    assert evidence.quality_state == "validated"
    db.commit.assert_not_awaited()
    event.assert_not_awaited()


@pytest.mark.parametrize("surface", ["artifact", "bundle", "registration"])
@pytest.mark.parametrize(
    "state", ["suggested", "draft", "reviewed", "superseded", "archived", None]
)
def test_knowledge_archive_checks_use_real_model_state(monkeypatch, surface, state):
    project = Project(id=uuid4(), lab_id=uuid4(), deleted_at=None)
    task = ResearchTask(id=uuid4(), project_id=project.id, lab_id=project.lab_id)
    item = (
        KnowledgeItem(
            id=uuid4(),
            state=state,
            scope_type="project",
            visibility="project",
            project_id=project.id,
            lab_id=project.lab_id,
            revision=2,
        )
        if state is not None
        else None
    )
    identity = item.id if item else uuid4()
    db = SimpleNamespace(
        get=AsyncMock(
            side_effect=lambda model, key: {
                KnowledgeItem: item,
                ResearchTask: task,
                Project: project,
            }[model]
        )
    )
    check = AsyncMock()
    monkeypatch.setattr(knowledge_service, "authorize_knowledge_item", check)
    monkeypatch.setattr(api, "authorize_knowledge_item", check)
    user = SimpleNamespace(id=uuid4())
    if surface == "artifact":
        operation = visibility.require_artifact_source_readable(
            db,
            task=task,
            user=user,
            artifact_type="knowledge",
            artifact_id=str(identity),
            artifact_version="2",
        )
    elif surface == "bundle":
        operation = visibility.require_asset_snapshot_sources_readable(
            db,
            task_id=task.id,
            user=user,
            payload={"knowledge_items": [{"id": str(identity), "evidence": []}]},
        )
    else:
        operation = api._validate_evidence_artifact(
            db,
            user,
            api.TaskContext(task, project, SimpleNamespace(id=project.lab_id)),
            artifact_type="knowledge",
            artifact_id=str(identity),
            artifact_version="2",
        )
    if state in {"archived", None}:
        with pytest.raises(HTTPException) as denied:
            asyncio.run(operation)
        assert denied.value.status_code == (404 if surface == "registration" else 403)
        check.assert_not_awaited()
    else:
        result = asyncio.run(operation)
        if surface == "registration":
            assert result == "2"
        check.assert_awaited_once_with(db, user, item)
    # Guard against test doubles silently inventing a nonexistent model field.
    assert "archived_at" not in KnowledgeItem.__table__.c


@pytest.mark.parametrize("version", ["", "b" * 64, "a" * 64])
def test_publication_source_requires_exact_digest_and_live_guard(monkeypatch, version):
    from app.services import analysis_publications

    publication = SimpleNamespace(id=uuid4(), digest="a" * 64)
    task = SimpleNamespace(id=uuid4(), project_id=uuid4())
    db = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(deleted_at=None)))
    user = object()
    check = AsyncMock(return_value=publication)
    monkeypatch.setattr(
        analysis_publications, "require_analysis_publication_readable", check
    )
    operation = visibility.require_artifact_source_readable(
        db,
        task=task,
        user=user,
        artifact_type="analysis_publication",
        artifact_id=str(publication.id),
        artifact_version=version,
    )
    if version == publication.digest:
        asyncio.run(operation)
    else:
        with pytest.raises(HTTPException) as denied:
            asyncio.run(operation)
        assert denied.value.status_code == 409
    check.assert_awaited_once_with(db, publication.id, user, task_id=task.id)


def test_bundle_contains_only_exact_verified_publication_copy(monkeypatch):
    from app.services import analysis_publications

    task_id = uuid4()
    publication = SimpleNamespace(
        id=uuid4(), task_id=task_id, evidence_id=uuid4(), digest="a" * 64
    )
    evidence = ResearchEvidence(
        id=publication.evidence_id,
        task_id=task_id,
        artifact_type="analysis_publication",
        artifact_id=str(publication.id),
        artifact_version=publication.digest,
    )
    expected_snapshot = {
        "schema": "airalogy.analysis-evidence-publication.v1",
        "selected": ["mean"],
    }
    payload = MagicMock(return_value=expected_snapshot)
    monkeypatch.setattr(analysis_publications, "publication_payload", payload)
    db = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                rows([]),
                rows([evidence]),
                rows([publication]),
                rows([]),
                rows([]),
                rows([]),
            ]
        )
    )
    result = asyncio.run(research_assets.research_asset_bundle(db, task_id=task_id))
    assert result["evidence"][0]["artifact_snapshot"] == expected_snapshot
    payload.assert_called_once_with(publication)


def test_lab_publication_cleanup_blocks_foreign_references():
    db = SimpleNamespace(scalar=AsyncMock(return_value=uuid4()), execute=AsyncMock())
    with pytest.raises(ValueError, match="Another Lab"):
        asyncio.run(_delete_lab_analysis_publications(db, uuid4()))
    db.execute.assert_not_awaited()


@pytest.mark.parametrize(
    "change",
    [None, "project", "analysis", "task", "evidence", "digest", "interpretation"],
)
def test_lab_publication_cleanup_only_releases_confirmed_scope(change):
    from app.models.analysis import AnalysisInterpretationRevision, AnalysisRun
    from app.models.project import Project
    from app.models.research import ResearchTask

    lab_id, project_id, analysis_id, task_id = uuid4(), uuid4(), uuid4(), uuid4()
    publication = SimpleNamespace(
        id=uuid4(),
        project_id=project_id,
        analysis_run_id=analysis_id,
        task_id=task_id,
        evidence_id=uuid4(),
        digest="a" * 64,
        interpretation_revision_id=uuid4(),
    )
    sources = {
        Project: SimpleNamespace(id=project_id, lab_id=lab_id),
        AnalysisRun: SimpleNamespace(id=analysis_id, project_id=project_id),
        ResearchTask: SimpleNamespace(id=task_id, lab_id=lab_id, project_id=project_id),
        ResearchEvidence: SimpleNamespace(
            task_id=task_id,
            artifact_type="analysis_publication",
            artifact_id=str(publication.id),
            artifact_version=publication.digest,
        ),
        AnalysisInterpretationRevision: SimpleNamespace(analysis_run_id=analysis_id),
    }
    if change == "project":
        sources[Project].lab_id = uuid4()
    elif change == "analysis":
        sources[AnalysisRun].project_id = uuid4()
    elif change == "task":
        sources[ResearchTask].lab_id = uuid4()
    elif change == "evidence":
        sources[ResearchEvidence].artifact_id = str(uuid4())
    elif change == "digest":
        sources[ResearchEvidence].artifact_version = "b" * 64
    elif change == "interpretation":
        sources[AnalysisInterpretationRevision].analysis_run_id = uuid4()
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=None),
        scalars=AsyncMock(return_value=rows([publication])),
        get=AsyncMock(side_effect=lambda model, identity: sources[model]),
        execute=AsyncMock(),
    )
    operation = _delete_lab_analysis_publications(db, lab_id)
    if change is not None:
        with pytest.raises(ValueError, match="confirmed Lab"):
            asyncio.run(operation)
        db.execute.assert_not_awaited()
    else:
        asyncio.run(operation)
        db.execute.assert_awaited_once()
        query = str(db.execute.await_args.args[0])
        assert "DELETE FROM analysis_evidence_publications" in query
        assert "analysis_evidence_publications.project_id IN" in query
