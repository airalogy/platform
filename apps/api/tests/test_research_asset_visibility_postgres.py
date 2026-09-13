"""Real Workflow Evidence cannot become a second, less-protected report API."""

import asyncio
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from app.models.analysis import AnalysisRun
from app.models.project import ProjectRole, ProjectUser
from app.models.research import ResearchAction, ResearchRun
from app.models.research_asset import ResearchEvidence
from app.routers import knowledge, research_tasks
from app.routers import research_assets as api
from app.services.research_asset_visibility import (
    require_asset_snapshot_sources_readable,
    require_task_asset_sources_readable,
)
from app.services.workflow_definitions import WorkflowDraft
from tests.test_record_analysis_postgres import execute_job
from tests.test_workflow_analysis_runtime_postgres import (
    queued_analysis,
    setup_analysis_workflow,
)
from tests.test_workflow_binding_postgres import second_protocol
from tests.test_workflow_definitions_postgres import (
    actions_by_node,
    add_record,
    approve_action,
    create_task,
    database,
    node,
    publish,
    seed_analysis,
    start_workflow,
    submit_record,
)
from tests.test_workflow_definitions_postgres import (
    deterministic_no_ai as deterministic_no_ai,
)
from tests.test_workflow_definitions_postgres import pytestmark as pytestmark
from tests.test_workflow_files_postgres import file_record, revoke_source, setup_files


def encoded(value):
    return json.dumps(jsonable_encoder(value), sort_keys=True)


async def register_output(
    sessions, scope, started, action, *, summary="Synthetic evidence"
):
    draft = api.EvidenceDraft(
        task_id=started["task_id"],
        run_id=started["run_id"],
        action_id=action.id,
        artifact_type="action_output",
        artifact_id=str(action.id),
        kind="analysis",
        summary=summary,
    )
    async with sessions() as db:
        preview = await api.preview_evidence(draft, scope.owner, db)
        saved = await api.create_evidence(
            api.EvidenceCreate(
                **draft.model_dump(), preview_digest=preview["preview_digest"]
            ),
            scope.owner,
            db,
        )
        return saved, draft, preview


def test_analysis_evidence_claim_and_knowledge_sources_recheck_revoked_record_access():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            _, started, actions, _, _ = await setup_analysis_workflow(sessions, scope)
            analysis = await queued_analysis(sessions, scope, actions)
            await execute_job(sessions, analysis.as_dict())
            actions = await actions_by_node(sessions, started["run_id"])
            saved, draft, preview = await register_output(
                sessions,
                scope,
                started,
                actions["analysis"],
                summary="Private raw analysis interpretation 993817.25",
            )
            evidence_id = UUID(str(saved["id"]))
            task_id = UUID(str(started["task_id"]))
            async with sessions() as db:
                analysis = await db.get(AnalysisRun, analysis.id)
                await api.review_evidence(
                    evidence_id,
                    api.EvidenceReview(
                        expected_quality_state="pending", quality_state="validated"
                    ),
                    scope.owner,
                    db,
                )
                claim_draft = api.ClaimDraft(
                    task_id=task_id,
                    statement="Private conclusion 993817.25",
                    evidence=[{"evidence_id": evidence_id, "relation": "supports"}],
                )
                claim_preview = await api.preview_claim(claim_draft, scope.analyst, db)
                claim = await api.create_claim(
                    api.ClaimCreate(
                        **claim_draft.model_dump(),
                        preview_digest=claim_preview["preview_digest"],
                    ),
                    scope.analyst,
                    db,
                )
                note_draft = api.KnowledgeSuggestionDraft(
                    task_id=task_id,
                    title="Explicitly published organizational guidance",
                    body="Use a documented review before adopting results.",
                    evidence_ids=[evidence_id],
                )
                note_preview = await api.preview_knowledge_suggestion(
                    note_draft, scope.owner, db
                )
                note = await api.create_knowledge_suggestion(
                    api.KnowledgeSuggestionCreate(
                        **note_draft.model_dump(),
                        preview_digest=note_preview["preview_digest"],
                    ),
                    scope.owner,
                    db,
                )
                await knowledge.review_knowledge_item(
                    UUID(str(note["id"])),
                    knowledge.KnowledgeReviewParams(expected_revision=1),
                    db,
                    scope.owner,
                )
                readable = await api.get_task_research_assets(
                    task_id, scope.analyst, db
                )
                assert "993817.25" in encoded(readable)
                published_evidence = next(
                    item for item in readable["evidence"] if item["id"] == evidence_id
                )
                assert published_evidence["artifact_snapshot"]["output_data"][
                    "analysis_result"
                ]["report"]
                linked = await knowledge.get_knowledge_item(
                    UUID(str(note["id"])), db, scope.analyst
                )
                assert len(linked["evidence_sources"]) == 1
                role = await db.scalar(
                    select(ProjectUser).where(
                        ProjectUser.project_id == scope.project.id,
                        ProjectUser.user_id == scope.analyst.id,
                    )
                )
                role.role = ProjectRole.RECORDER_SELF_ONLY
                await db.commit()
            async with sessions() as db:
                hidden = await api.get_task_research_assets(task_id, scope.analyst, db)
                assert hidden["evidence"] == [] and hidden["claims"] == []
                assert "993817.25" not in encoded(hidden)
                assert analysis.result_digest not in encoded(hidden)
                assert str(analysis.id) not in encoded(hidden)
                published = await knowledge.get_knowledge_item(
                    UUID(str(note["id"])), db, scope.analyst
                )
                assert published["body"] == note_draft.body
                assert published["evidence_sources"] == []
                assert hidden["knowledge_items"][0]["body"] == note_draft.body
                assert hidden["knowledge_items"][0]["evidence"] == []
                for operation in (
                    lambda: api.preview_evidence(draft, scope.analyst, db),
                    lambda: api.create_evidence(
                        api.EvidenceCreate(
                            **draft.model_dump(),
                            preview_digest=preview["preview_digest"],
                        ),
                        scope.analyst,
                        db,
                    ),
                    lambda: api.preview_claim(claim_draft, scope.analyst, db),
                    lambda: api.create_claim(
                        api.ClaimCreate(
                            **claim_draft.model_dump(),
                            preview_digest=claim_preview["preview_digest"],
                        ),
                        scope.analyst,
                        db,
                    ),
                    lambda: api.preview_knowledge_suggestion(
                        note_draft, scope.analyst, db
                    ),
                    lambda: api.preview_claim_revision(
                        UUID(str(claim["id"])),
                        api.ClaimRevisionDraft(
                            expected_revision=1,
                            statement="Drop private source",
                            change_summary="Attempt to remove provenance",
                            evidence=[],
                        ),
                        scope.analyst,
                        db,
                    ),
                    lambda: require_task_asset_sources_readable(
                        db, task_id=task_id, user=scope.analyst
                    ),
                ):
                    with pytest.raises(HTTPException) as denied:
                        await operation()
                    assert denied.value.status_code == 403
                owner = await api.get_task_research_assets(task_id, scope.owner, db)
                assert len(owner["evidence"]) == 3 and len(owner["claims"]) == 1
                role = await db.scalar(
                    select(ProjectUser).where(
                        ProjectUser.project_id == scope.project.id,
                        ProjectUser.user_id == scope.analyst.id,
                    )
                )
                role.role = ProjectRole.COLLABORATOR
                await db.commit()
            async with sessions() as db:
                restored = await api.get_task_research_assets(
                    task_id, scope.analyst, db
                )
                assert len(restored["evidence"]) == 3 and len(restored["claims"]) == 1
                assert (
                    await knowledge.get_knowledge_item(
                        UUID(str(note["id"])), db, scope.analyst
                    )
                )["evidence_sources"]

    asyncio.run(exercise())


def test_evidence_registration_and_list_keep_independent_readable_workflow_branch():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            protocol, version = await second_protocol(
                sessions, scope, assignee=scope.recorder
            )
            workflow, _ = await publish(
                sessions,
                scope,
                WorkflowDraft(
                    project_id=scope.project.id,
                    title="Independent private and readable roots",
                    graph={
                        "schema_version": 2,
                        "nodes": [
                            node(scope, "private"),
                            node(
                                scope,
                                "own",
                                protocol_id=str(protocol.id),
                                protocol_version_id=str(version.id),
                            ),
                        ],
                        "edges": [],
                        "bindings": [],
                    },
                ),
            )
            started, _ = await start_workflow(
                sessions,
                scope,
                workflow,
                await create_task(
                    sessions, scope, protocol_ids=[scope.protocol.id, protocol.id]
                ),
            )
            actions = await actions_by_node(sessions, started["run_id"])
            await submit_record(
                sessions,
                scope,
                actions["private"].id,
                await add_record(sessions, scope, 993817.25),
            )
            await approve_action(sessions, scope, actions["own"].id)
            own_scope = SimpleNamespace(
                **{
                    **vars(scope),
                    "protocol": protocol,
                    "version": version,
                    "owner": scope.recorder,
                }
            )
            await submit_record(
                sessions,
                own_scope,
                actions["own"].id,
                await add_record(sessions, own_scope, 27, author=scope.recorder),
            )
            actions = await actions_by_node(sessions, started["run_id"])
            await register_output(
                sessions,
                scope,
                started,
                actions["private"],
                summary="Restricted 993817.25",
            )
            own, _, _ = await register_output(
                sessions, own_scope, started, actions["own"]
            )
            async with sessions() as db:
                result = await api.get_task_research_assets(
                    UUID(str(started["task_id"])), scope.recorder, db
                )
                own_output = next(
                    item
                    for item in result["evidence"]
                    if str(item["id"]) == str(own["id"])
                )
                assert len(result["evidence"]) == 2
                assert "993817.25" not in encoded(result)
                assert (
                    own_output["artifact_snapshot"]["output_data"]["record"]["data"][
                        "var"
                    ]["value"]
                    == 27
                )
                # An independently sealed subset does not become unreadable merely
                # because this Task also contains an unrelated private branch.
                await require_asset_snapshot_sources_readable(
                    db,
                    task_id=UUID(str(started["task_id"])),
                    payload=result,
                    user=scope.recorder,
                )
                with pytest.raises(HTTPException):
                    await require_task_asset_sources_readable(
                        db,
                        task_id=UUID(str(started["task_id"])),
                        user=scope.recorder,
                    )

    asyncio.run(exercise())


def test_file_bound_record_evidence_rechecks_original_source_on_every_read():
    async def exercise():
        async with database() as sessions:
            scope, started, actions, record, *_ = await setup_files(sessions)
            actions = await actions_by_node(sessions, started["run_id"])
            target = actions["next"]
            alias = target.input_data["initial_values"]["attachment"]
            completed = await file_record(
                sessions, scope, {"attachment": alias}, number=2
            )
            await submit_record(sessions, scope, target.id, completed)
            actions = await actions_by_node(sessions, started["run_id"])
            evidence, _, _ = await register_output(
                sessions, scope, started, actions["next"]
            )
            async with sessions() as db:
                visible = await api.get_task_research_assets(
                    UUID(str(started["task_id"])), scope.owner, db
                )
                assert str(evidence["id"]) in encoded(visible)
            await revoke_source(sessions, record)
            async with sessions() as db:
                hidden = await api.get_task_research_assets(
                    UUID(str(started["task_id"])), scope.owner, db
                )
                assert hidden["evidence"] == [] and alias not in encoded(hidden)
                # A forged direct Record reference cannot bypass its file lineage.
                with pytest.raises(HTTPException):
                    await api.preview_evidence(
                        api.EvidenceDraft(
                            task_id=started["task_id"],
                            artifact_type="record",
                            artifact_id=str(completed.id),
                            artifact_version=str(completed.version),
                            kind="measurement",
                        ),
                        scope.owner,
                        db,
                    )
                assert (
                    await db.get(ResearchEvidence, UUID(str(evidence["id"])))
                    is not None
                )
                assert (await db.get(ResearchAction, target.id)).status == "completed"

    asyncio.run(exercise())


def test_ordinary_protocol_output_evidence_keeps_original_record_acl():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            task = await create_task(sessions, scope)
            task_id = UUID(str(task["id"]))
            async with sessions() as db:
                await research_tasks.start_research_task(
                    task_id,
                    research_tasks.TaskTransitionParams(
                        expected_revision=task["revision"],
                        reason="Synthetic manual study",
                    ),
                    scope.owner,
                    db,
                )
                draft = research_tasks.ManualProtocolActionDraft(
                    protocol_id=scope.protocol.id, idempotency_key=uuid4().hex
                )
                preview = await research_tasks.preview_manual_protocol_action(
                    task_id, draft, scope.owner, db
                )
                created = await research_tasks.create_manual_protocol_action(
                    task_id,
                    research_tasks.ManualProtocolActionCreate(
                        **draft.model_dump(), preview_digest=preview["preview_digest"]
                    ),
                    scope.owner,
                    db,
                )
                action = await db.get(ResearchAction, UUID(str(created["id"])))
                run = await db.get(ResearchRun, action.run_id)
                assert "manual_workflow" not in run.environment_snapshot
                started = {"task_id": task_id, "run_id": run.id}
            record = await add_record(sessions, scope, 281.75)
            await submit_record(sessions, scope, action.id, record)
            async with sessions() as db:
                action = await db.get(ResearchAction, action.id)
            saved, draft, preview = await register_output(
                sessions, scope, started, action
            )
            async with sessions() as db:
                visible = await api.get_task_research_assets(task_id, scope.owner, db)
                assert "281.75" in encoded(visible)
                hidden = await api.get_task_research_assets(task_id, scope.recorder, db)
                assert hidden["evidence"] == []
                with pytest.raises(HTTPException) as denied:
                    await api.preview_evidence(draft, scope.recorder, db)
                assert denied.value.status_code == 403
                # Changing an ordinary Action cannot switch the authority used for
                # its already sealed Evidence to a new, apparently harmless value.
                stored = await db.get(ResearchAction, action.id)
                stored.output_data = {"note": "No sensitive result here"}
                await db.commit()
            async with sessions() as db:
                hidden = await api.get_task_research_assets(task_id, scope.recorder, db)
                assert hidden["evidence"] == []
                original = await api.get_task_research_assets(task_id, scope.owner, db)
                item = next(
                    item
                    for item in original["evidence"]
                    if str(item["id"]) == str(saved["id"])
                )
                assert (
                    item["artifact_snapshot"]["output_data"]["record"]["data"]["var"][
                        "value"
                    ]
                    == 281.75
                )
                with pytest.raises(HTTPException):
                    await api.create_evidence(
                        api.EvidenceCreate(
                            **draft.model_dump(),
                            preview_digest=preview["preview_digest"],
                        ),
                        scope.recorder,
                        db,
                    )

    asyncio.run(exercise())
