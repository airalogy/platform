"""Historical Evidence must not escape through a later, otherwise readable Run."""

import asyncio
import json
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from app.config import config
from app.models.research import (
    ResearchAction,
    ResearchApproval,
    ResearchHumanWorkItem,
    ResearchResultPackageSnapshot,
    ResearchRun,
    ResearchTask,
)
from app.routers import research_result_packages as reports
from app.routers import research_tasks as tasks
from app.services import research_runtime as runtime
from app.services.workflow_visibility import workflow_data_readable
from tests.test_workflow_definitions_postgres import (
    add_record,
    create_task,
    seed_analysis,
    submit_record,
)
from tests.test_workflow_definitions_postgres import (
    deterministic_no_ai as deterministic_no_ai,
)
from tests.test_workflow_definitions_postgres import pytestmark as pytestmark
from tests.test_workflow_files_postgres import database, revoke_source, setup_files


def test_old_run_record_sources_guard_later_task_review_ai_and_sealed_reports(
    monkeypatch,
):
    async def exercise():
        async with database() as sessions:
            scope, started, _, source, _ = await setup_files(sessions)
            task_id = UUID(str(started["task_id"]))
            async with sessions() as db:
                task = await db.get(ResearchTask, task_id)
                # A later ordinary Run retains task-level Evidence from Run 1.
                # This fixture isolates that read boundary; no second execution
                # is dispatched or claimed to have completed.
                later = ResearchRun(
                    task_id=task.id,
                    run_number=2,
                    status="running",
                    requested_by_user_id=scope.owner.id,
                    environment_snapshot={},
                    aira_state={},
                    result_package={},
                )
                db.add(later)
                await db.flush()
                package = await runtime.build_research_result_package(
                    db, task=task, run=later
                )
                assert any(
                    item["artifact_id"] == str(source.id)
                    for item in package["evidence"]
                )
                later.result_package = package
                task.result_package = {}
                task.status = "active"
                sealed = ResearchResultPackageSnapshot(
                    task_id=task.id,
                    run_id=later.id,
                    task_revision=task.revision,
                    schema_version=package["schema"],
                    package=package,
                    digest=runtime.canonical_digest(package),
                    finalized_by_user_id=scope.owner.id,
                )
                db.add(sealed)
                await db.commit()
                later_id = later.id
                revision = task.revision

            async with sessions() as db:
                before = await reports.get_research_result_package(
                    task_id, scope.owner, db, run_id=later_id
                )
                assert before["snapshot"]["sealed"] is True

            await revoke_source(sessions, source)
            model = AsyncMock(
                side_effect=AssertionError("Private sources must never reach a model")
            )
            monkeypatch.setattr(tasks, "generate_research_review", model)
            monkeypatch.setattr(config, "AI_ENABLED", True)
            async with sessions() as db:
                later = await db.get(ResearchRun, later_id)
                # The prior latest-Workflow-only guard would accept this Run.
                assert await workflow_data_readable(
                    db, run=later, current_user=scope.owner
                )
                detail = await tasks.get_research_task(task_id, scope.owner, db)
                assert detail["workflow_data_restricted"] is True
                assert detail["result_package"] == {}
                assert detail["review_recommendations"] == []
                assert detail["latest_run"]["result_package"] == {}

            operations = (
                lambda db: reports.get_research_result_package(
                    task_id, scope.owner, db, run_id=later_id
                ),
                lambda db: reports.export_research_result_package(
                    task_id, scope.owner, db, run_id=later_id
                ),
                lambda db: tasks.generate_review_recommendation(
                    task_id,
                    tasks.ResearchReviewRequest(expected_task_revision=revision),
                    scope.owner,
                    db,
                ),
                lambda db: tasks.complete_research_task(
                    task_id,
                    tasks.TaskCompleteParams(
                        expected_revision=revision,
                        outcome="goal_met",
                        scientific_outcome="supports_hypothesis",
                        conclusion="Review without access must fail",
                    ),
                    scope.owner,
                    db,
                ),
            )
            for operation in operations:
                async with sessions() as db:
                    with pytest.raises(HTTPException) as denied:
                        await operation(db)
                    assert denied.value.status_code in {403, 409}
            model.assert_not_awaited()
            async with sessions() as db:
                task = await db.get(ResearchTask, task_id)
                assert task.status == "active" and task.revision == revision

    asyncio.run(exercise())


def test_ordinary_protocol_record_and_run_cache_do_not_leak_via_cards_workitems_or_approvals():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            created_task = await create_task(sessions, scope)
            task_id = UUID(str(created_task["id"]))
            async with sessions() as db:
                await tasks.start_research_task(
                    task_id,
                    tasks.TaskTransitionParams(
                        expected_revision=created_task["revision"]
                    ),
                    scope.owner,
                    db,
                )
            created = []
            for assignee in (scope.owner, scope.recorder):
                async with sessions() as db:
                    draft = tasks.ManualProtocolActionDraft(
                        protocol_id=scope.protocol.id,
                        assignee_user_id=assignee.id,
                        initial_values={"value": 3.25},
                        idempotency_key=uuid4().hex,
                    )
                    preview = await tasks.preview_manual_protocol_action(
                        task_id, draft, scope.owner, db
                    )
                    created.append(
                        await tasks.create_manual_protocol_action(
                            task_id,
                            tasks.ManualProtocolActionCreate(
                                **draft.model_dump(),
                                preview_digest=preview["preview_digest"],
                            ),
                            scope.owner,
                            db,
                        )
                    )
            private_action_id, own_action_id = [
                UUID(str(item["id"])) for item in created
            ]
            secret = 712839.625
            record = await add_record(sessions, scope, secret)
            await submit_record(sessions, scope, private_action_id, record)
            async with sessions() as db:
                private_action = await db.get(ResearchAction, private_action_id)
                run = await db.get(ResearchRun, private_action.run_id)
                assert "manual_workflow" not in run.environment_snapshot
                assert str(secret) in json.dumps(jsonable_encoder(run.aira_state))
                items = list(
                    (
                        await db.scalars(
                            select(ResearchHumanWorkItem).where(
                                ResearchHumanWorkItem.action_id.in_(
                                    [private_action_id, own_action_id]
                                )
                            )
                        )
                    ).all()
                )
                item_ids = {item.action_id: item.id for item in items}
                # Persist historical approved metadata only; this does not
                # dispatch or approve a new experiment in the test.
                approval = ResearchApproval(
                    action_id=private_action_id,
                    approver_user_id=scope.owner.id,
                    requested_by_user_id=scope.owner.id,
                    decided_by_user_id=scope.owner.id,
                    status="approved",
                    preview_digest=private_action.preview_digest,
                    reason="Synthetic historical approval",
                )
                db.add(approval)
                await db.commit()
                approval_id = approval.id

            async with sessions() as db:
                visible = jsonable_encoder(
                    await tasks.get_research_task(task_id, scope.owner, db)
                )
                assert str(secret) in json.dumps(visible)
                hidden = jsonable_encoder(
                    await tasks.get_research_task(task_id, scope.recorder, db)
                )
                assert str(secret) not in json.dumps(hidden)
                cards = {item["id"]: item for item in hidden["actions"]}
                assert cards[str(private_action_id)]["workflow_data_restricted"] is True
                assert cards[str(private_action_id)]["output_data"] == {}
                assert (
                    cards[str(private_action_id)]["protocol_run"]["record_id"] is None
                )
                assert not cards[str(own_action_id)].get("workflow_data_restricted")
                assert cards[str(own_action_id)]["input_data"]["initial_values"] == {
                    "value": 3.25
                }

            for endpoint, identity in (
                (tasks.get_research_work_item, item_ids[private_action_id]),
                (tasks.get_research_approval, approval_id),
            ):
                async with sessions() as db:
                    result = jsonable_encoder(
                        await endpoint(identity, scope.recorder, db)
                    )
                    assert str(secret) not in json.dumps(result)
                    assert result["workflow_data_restricted"] is True
                    assert result["action"]["output_data"] == {}
                    assert result["run"]["workflow_data_restricted"] is True
                    assert result["run"]["aira_state"] == {}

            async with sessions() as db:
                own = await tasks.get_research_work_item(
                    item_ids[own_action_id], scope.recorder, db
                )
                assert own["permissions"]["can_start"] is True
                assert not own["action"].get("workflow_data_restricted")
                assert own["run"]["workflow_data_restricted"] is True
                assert str(secret) not in json.dumps(jsonable_encoder(own))
                started = await tasks.start_research_work_item(
                    item_ids[own_action_id],
                    tasks.WorkItemRevisionParams(expected_revision=own["revision"]),
                    scope.recorder,
                    db,
                )
                assert started["status"] == "in_progress"
                assert not started["action"].get("workflow_data_restricted")
                assert started["run"]["aira_state"] == {}

    asyncio.run(exercise())
