"""Fail-closed asset read models without broadening Task membership into data ACL."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.knowledge import KnowledgeItem
from app.models.record import Record
from app.models.research import ResearchAction, ResearchRun, ResearchTask
from app.models.research_asset import ResearchActionOutputSnapshot
from app.services import research_asset_visibility as visibility
from app.services import research_assets
from app.services.research_action_outputs import (
    action_output_digest,
    action_output_payload,
)


def context(*, workflow=True):
    project = SimpleNamespace(id=uuid4(), deleted_at=None)
    task = SimpleNamespace(id=uuid4(), project_id=project.id, archived_at=None)
    run = SimpleNamespace(
        id=uuid4(),
        task_id=task.id,
        environment_snapshot={"manual_workflow": {"execution_contract_version": 3}}
        if workflow
        else {},
    )
    action = ResearchAction(
        id=uuid4(),
        run_id=run.id,
        kind="analysis_run" if workflow else "tool_job",
        revision=1,
        status="completed",
        input_data={},
        output_data={"result": "classified value"},
        requirements={},
    )
    db = SimpleNamespace(
        get=AsyncMock(
            side_effect=lambda model, identity: {
                ResearchTask: task,
                ResearchRun: run,
                ResearchAction: action,
            }.get(model, project)
        ),
        scalar=AsyncMock(return_value=None),
    )
    return db, task, run, action, SimpleNamespace(id=uuid4())


def test_action_output_reuses_per_card_guard_not_whole_run(monkeypatch):
    db, task, run, action, user = context()
    guard = AsyncMock(side_effect=HTTPException(403, "Source revoked"))
    monkeypatch.setattr(
        "app.services.workflow_visibility.require_workflow_action_data_readable", guard
    )
    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            visibility.require_artifact_source_readable(
                db,
                task=task,
                user=user,
                artifact_type="action_output",
                artifact_id=str(action.id),
                artifact_version="",
            )
        )
    assert denied.value.status_code == 403
    assert guard.await_args.kwargs == {
        "run": run,
        "action": action,
        "current_user": user,
        "project": guard.await_args.kwargs["project"],
    }
    db.scalar.assert_not_awaited()


def test_ordinary_action_keeps_existing_snapshot_contract(monkeypatch):
    db, task, _, action, user = context(workflow=False)
    monkeypatch.setattr(
        "app.services.workflow_visibility.require_workflow_action_data_readable",
        AsyncMock(),
    )
    asyncio.run(
        visibility.require_artifact_source_readable(
            db,
            task=task,
            user=user,
            artifact_type="action_output",
            artifact_id=str(action.id),
            artifact_version="",
        )
    )
    db.scalar.assert_not_awaited()


@pytest.mark.parametrize("sealed", [False, True])
def test_ordinary_protocol_uses_sealed_record_when_available(monkeypatch, sealed):
    db, task, run, action, user = context(workflow=False)
    action.kind = "protocol_run"
    action.output_data = {"record": {"original": "exact source"}}
    payload = action_output_payload(action, task_id=task.id)
    snapshot = ResearchActionOutputSnapshot(
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        action_revision=1,
        action_kind=action.kind,
        output_data=action.output_data,
        digest=action_output_digest(payload),
    )
    if sealed:
        db.scalar.return_value = snapshot
        action.output_data = {"record": {"changed": "not the frozen source"}}
    check = AsyncMock()
    monkeypatch.setattr(visibility, "_require_protocol_output_readable", check)
    monkeypatch.setattr(
        "app.services.workflow_visibility.require_workflow_action_data_readable",
        AsyncMock(),
    )
    asyncio.run(
        visibility.require_artifact_source_readable(
            db,
            task=task,
            user=user,
            artifact_type="action_output",
            artifact_id=str(action.id),
            artifact_version=snapshot.digest if sealed else "",
        )
    )
    assert check.await_args.kwargs["output"] == {"record": {"original": "exact source"}}


@pytest.mark.parametrize(
    "mutation",
    [None, "wrong_revision", "hash", "data", "file_revoked", "record_revoked"],
)
def test_ordinary_protocol_record_requires_exact_source_and_current_file_access(
    monkeypatch, mutation
):
    task = SimpleNamespace(id=uuid4(), project_id=uuid4())
    project = SimpleNamespace(id=task.project_id, deleted_at=None)
    user = SimpleNamespace(id=uuid4())
    action = SimpleNamespace(id=uuid4())
    record = SimpleNamespace(
        id=uuid4(),
        version=1,
        protocol_id=uuid4(),
        protocol_version="1.0.0",
        user_id=user.id,
        deleted_at=None,
        data={"var": {"value": 3}},
        hash="exact-record-hash",
    )
    typed = SimpleNamespace(
        protocol_id=record.protocol_id,
        protocol_version=record.protocol_version,
        record_id=record.id,
        record_version=1,
    )
    output = {
        "record": {
            "record_id": str(record.id),
            "record_version": 1,
            "data": record.data.copy(),
            "metadata": {"sha1": record.hash},
        }
    }
    if mutation == "wrong_revision":
        typed.record_version = 2
    elif mutation == "hash":
        output["record"]["metadata"]["sha1"] = "changed"
    elif mutation == "data":
        output["record"]["data"] = {"var": {"value": 99}}
    db = SimpleNamespace(
        get=AsyncMock(
            side_effect=lambda model, key: record if model is Record else project
        ),
        scalar=AsyncMock(return_value=typed),
    )
    scope = AsyncMock(return_value=(None, project, False))
    if mutation == "record_revoked":
        scope.side_effect = HTTPException(403, "Record revoked")
    files = AsyncMock(
        side_effect=HTTPException(403, "File revoked")
        if mutation == "file_revoked"
        else None
    )
    monkeypatch.setattr("app.services.record_analyses.analysis_scope", scope)
    monkeypatch.setattr("app.services.workflow_files.authorize_record_files", files)
    operation = visibility._require_protocol_output_readable(
        db, task=task, action=action, user=user, output=output
    )
    if mutation is not None:
        with pytest.raises(HTTPException) as denied:
            asyncio.run(operation)
        assert denied.value.status_code == (
            403 if mutation.endswith("revoked") else 409
        )
    else:
        asyncio.run(operation)
        files.assert_awaited_once_with(db, record.data, user)


@pytest.mark.parametrize("change", ["output", "task", "run", "digest"])
def test_workflow_snapshot_cannot_borrow_acl_of_changed_action(monkeypatch, change):
    db, task, run, action, user = context()
    payload = action_output_payload(action, task_id=task.id)
    snapshot = ResearchActionOutputSnapshot(
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        action_revision=1,
        action_kind=action.kind,
        output_data=action.output_data.copy(),
        digest=action_output_digest(payload),
    )
    if change == "output":
        action.output_data = {"result": "different now-readable source"}
    elif change == "task":
        snapshot.task_id = uuid4()
    elif change == "run":
        snapshot.run_id = uuid4()
    else:
        snapshot.digest = "0" * 64
    db.scalar.return_value = snapshot
    monkeypatch.setattr(
        "app.services.workflow_visibility.require_workflow_action_data_readable",
        AsyncMock(),
    )
    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            visibility.require_artifact_source_readable(
                db,
                task=task,
                user=user,
                artifact_type="action_output",
                artifact_id=str(action.id),
                artifact_version=snapshot.digest,
            )
        )
    assert denied.value.status_code == 409


def test_visibility_hides_authorization_denial_but_not_server_fault(monkeypatch):
    check = AsyncMock(side_effect=HTTPException(403, "Private source"))
    monkeypatch.setattr(visibility, "require_evidence_source_readable", check)
    assert asyncio.run(visibility.evidence_source_readable(None, None, None)) is False
    check.side_effect = HTTPException(500, "Database error")
    with pytest.raises(HTTPException):
        asyncio.run(visibility.evidence_source_readable(None, None, None))


def test_knowledge_source_links_require_same_original_identity_and_live_read_access(
    monkeypatch,
):
    source = dict(
        id=uuid4(),
        task_id=uuid4(),
        artifact_type="action_output",
        artifact_id=str(uuid4()),
        artifact_version="a" * 64,
    )
    evidence = SimpleNamespace(**source)
    link = SimpleNamespace(
        evidence_id=evidence.id,
        source_snapshot={key: str(value) for key, value in source.items()},
    )
    db = SimpleNamespace(get=AsyncMock(return_value=evidence))
    readable = AsyncMock(return_value=True)
    monkeypatch.setattr(visibility, "evidence_source_readable", readable)
    assert asyncio.run(
        visibility.visible_knowledge_evidence_links(db, [link], object())
    ) == [link]
    readable.return_value = False
    assert (
        asyncio.run(visibility.visible_knowledge_evidence_links(db, [link], object()))
        == []
    )
    readable.return_value = True
    link.source_snapshot["artifact_id"] = str(uuid4())
    assert (
        asyncio.run(visibility.visible_knowledge_evidence_links(db, [link], object()))
        == []
    )


def test_package_checks_only_its_exact_sources_not_later_task_evidence(monkeypatch):
    db, task, _, action, user = context()
    source = dict(
        task_id=str(task.id),
        artifact_type="action_output",
        artifact_id=str(action.id),
        artifact_version="a" * 64,
    )
    check = AsyncMock()
    monkeypatch.setattr(visibility, "require_artifact_source_readable", check)
    asyncio.run(
        visibility.require_asset_snapshot_sources_readable(
            db,
            task_id=task.id,
            payload={
                "evidence": [source],
                "claims": [{"evidence": [{"source_snapshot": source}]}],
            },
            user=user,
        )
    )
    assert check.await_count == 1
    assert db.get.await_count == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"evidence": [None]},
        {"evidence": {}},
        {"data_assets": [{"versions": "latest"}]},
        {"claims": [{"evidence": [None]}]},
    ],
)
def test_malformed_package_sources_fail_closed(payload):
    db, task, _, _, user = context()
    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            visibility.require_asset_snapshot_sources_readable(
                db, task_id=task.id, payload=payload, user=user
            )
        )
    assert denied.value.status_code == 409


def test_snapshot_checks_knowledge_scope_even_without_evidence_links(monkeypatch):
    db, task, _, _, user = context()
    knowledge = KnowledgeItem(id=uuid4(), state="reviewed")
    db.get.side_effect = [task, knowledge]
    check = AsyncMock(side_effect=HTTPException(404, "Restricted Knowledge"))
    monkeypatch.setattr("app.services.knowledge.authorize_knowledge_item", check)
    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            visibility.require_asset_snapshot_sources_readable(
                db,
                task_id=task.id,
                payload={
                    "knowledge_items": [{"id": str(knowledge.id), "evidence": []}]
                },
                user=user,
            )
        )
    assert denied.value.status_code == 404
    check.assert_awaited_once_with(db, user, knowledge)


def test_snapshot_checks_improvement_target_even_with_readable_evidence(monkeypatch):
    db, task, _, _, user = context()
    proposal = SimpleNamespace(id=uuid4(), task_id=task.id, protocol_id=uuid4())
    db.get.side_effect = [task, proposal]
    check = AsyncMock(side_effect=HTTPException(403, "Restricted target Protocol"))
    monkeypatch.setattr(visibility, "require_protocol_improvement_readable", check)
    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            visibility.require_asset_snapshot_sources_readable(
                db,
                task_id=task.id,
                payload={
                    "protocol_improvements": [
                        {
                            "id": str(proposal.id),
                            "protocol_id": str(proposal.protocol_id),
                            "evidence": [],
                        }
                    ]
                },
                user=user,
            )
        )
    assert denied.value.status_code == 403
    check.assert_awaited_once_with(db, proposal, user)


def item(**values):
    return SimpleNamespace(**values, as_dict=lambda: values.copy())


def rows(values):
    return MagicMock(all=lambda: values)


def test_bundle_hides_entire_derived_claim_but_keeps_independent_evidence(monkeypatch):
    hidden = item(id=uuid4(), artifact_type="external", summary="secret value")
    public = item(id=uuid4(), artifact_type="external", summary="public value")
    secret_claim = item(id=uuid4(), statement="copied secret", confidence=None)
    public_claim = item(id=uuid4(), statement="independent conclusion", confidence=None)
    relations = [
        item(claim_id=secret_claim.id, evidence_id=hidden.id),
        item(claim_id=public_claim.id, evidence_id=public.id),
    ]
    db = SimpleNamespace(
        get=AsyncMock(return_value=object()),
        scalars=AsyncMock(
            side_effect=[
                rows([]),
                rows([hidden, public]),
                rows([secret_claim, public_claim]),
                rows(relations),
                rows([]),
                rows([]),
            ]
        ),
    )
    monkeypatch.setattr(
        research_assets,
        "evidence_source_readable",
        AsyncMock(side_effect=lambda db, evidence, user: evidence.id == public.id),
    )
    result = asyncio.run(
        research_assets.research_asset_bundle(
            db, task_id=uuid4(), current_user=object()
        )
    )
    assert result["evidence"] == [{**public.as_dict(), "artifact_snapshot": None}]
    assert [entry["statement"] for entry in result["claims"]] == [
        "independent conclusion"
    ]
