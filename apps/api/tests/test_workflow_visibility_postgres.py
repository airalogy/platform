"""Real source permissions at Workflow detail, approval and export boundaries."""

import asyncio
import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update

from app.models.project import ProjectRole, ProjectUser
from app.models.research import (
    ResearchAction,
    ResearchApproval,
    ResearchHumanWorkItem,
    ResearchTask,
)
from app.routers import research_result_packages as packages
from app.routers import research_tasks as tasks
from tests.test_workflow_binding_postgres import mapping, second_protocol, setup_bound
from tests.test_workflow_definitions_postgres import (
    actions_by_node,
    add_record,
    create_task,
    database,
    draft,
    edge,
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


def http_json(payload):
    """Direct handler tests must encode values exactly like FastAPI responses."""
    return json.dumps(jsonable_encoder(payload))


async def http_payload(handler, *args, **kwargs):
    return jsonable_encoder(await handler(*args, **kwargs))


async def bound_source(sessions):
    # Public does not grant a RECORDER_SELF_ONLY access to another user's Record.
    scope = await seed_analysis(sessions, public=True)
    _workflow, started, actions = await setup_bound(sessions, scope)
    record = await add_record(sessions, scope, 8173.125)
    await submit_record(sessions, scope, actions["first"].id, record)
    actions = await actions_by_node(sessions, started["run_id"])
    return scope, started, actions


def test_task_list_detail_approval_and_work_item_keep_status_but_hide_private_values():
    async def exercise():
        async with database() as sessions:
            scope, started, actions = await bound_source(sessions)
            task_id = UUID(str(started["task_id"]))
            async with sessions() as db:
                owner_view = await http_payload(
                    tasks.get_research_task, task_id, scope.owner, db
                )
                assert "8173.125" in http_json(owner_view)
                restricted = await http_payload(
                    tasks.get_research_task, task_id, scope.recorder, db
                )
                assert restricted["id"] == str(task_id)
                assert restricted["status"] == "active"
                assert restricted["workflow_data_restricted"] is True
                assert not restricted["permissions"]["can_approve"]
                assert "8173.125" not in http_json(restricted)
                target = next(
                    item
                    for item in restricted["actions"]
                    if item["id"] == str(actions["second"].id)
                )
                assert target["status"] == "proposed"
                assert target["workflow_data_restricted"] is True
                assert target["preview_digest"] == ""
                assert target["protocol_run"]["initial_values"] == {}
                approval = await db.scalar(
                    select(ResearchApproval).where(
                        ResearchApproval.action_id == actions["second"].id,
                        ResearchApproval.status == "pending",
                    )
                )
                preview = await http_payload(
                    tasks.get_research_approval, approval.id, scope.recorder, db
                )
                assert preview["workflow_data_restricted"] is True
                assert preview["action"]["workflow_data_restricted"] is True
                assert preview["preview_digest"] == ""
                assert "8173.125" not in http_json(preview)
                source_item = await db.scalar(
                    select(ResearchHumanWorkItem).where(
                        ResearchHumanWorkItem.action_id == actions["first"].id
                    )
                )
                work_item = await http_payload(
                    tasks.get_research_work_item, source_item.id, scope.recorder, db
                )
                assert work_item["workflow_data_restricted"] is True
                assert not any(work_item["permissions"].values())
                assert "8173.125" not in http_json(work_item)
                listing = await http_payload(
                    tasks.list_research_tasks,
                    scope.recorder,
                    db,
                    project_id=scope.project.id,
                    status=None,
                    page=1,
                    page_size=20,
                )
                assert listing["tasks"][0]["workflow_data_restricted"] is True
                assert "8173.125" not in http_json(listing)

    asyncio.run(exercise())


def test_result_get_and_exports_deny_unreadable_sources_and_restore_after_real_grant():
    async def exercise():
        async with database() as sessions:
            scope, started, actions = await bound_source(sessions)
            task_id = UUID(str(started["task_id"]))
            target_record = await add_record(sessions, scope, 6.0, number=2)
            await submit_record(sessions, scope, actions["second"].id, target_record)
            async with sessions() as db:
                owner_package = await http_payload(
                    packages.get_research_result_package, task_id, scope.owner, db
                )
                assert (
                    owner_package["package"]["manual_workflow"][
                        "execution_contract_version"
                    ]
                    == 2
                )
                with pytest.raises(HTTPException) as denied:
                    await http_payload(
                        packages.get_research_result_package,
                        task_id,
                        scope.recorder,
                        db,
                    )
                assert denied.value.status_code == 403
                for format in ("json", "markdown"):
                    with pytest.raises(HTTPException) as denied_export:
                        await packages.export_research_result_package(
                            task_id, scope.recorder, db, format=format
                        )
                    assert denied_export.value.status_code == 403
                detail = await http_payload(
                    tasks.get_research_task, task_id, scope.recorder, db
                )
                assert detail["status"] == "review_required"
                assert detail["result_package"] == {}
                assert detail["latest_run"]["result_package"] == {}
                assert all(run["result_package"] == {} for run in detail["runs"])
                await db.execute(
                    update(ProjectUser)
                    .where(
                        ProjectUser.project_id == scope.project.id,
                        ProjectUser.user_id == scope.recorder.id,
                    )
                    .values(role=ProjectRole.COLLABORATOR)
                )
                await db.commit()
            async with sessions() as db:
                restored = await http_payload(
                    packages.get_research_result_package, task_id, scope.recorder, db
                )
                assert (
                    restored["snapshot"]["digest"]
                    == owner_package["snapshot"]["digest"]
                )
                assert restored["package"] == owner_package["package"]

    asyncio.run(exercise())


def test_explicit_approver_without_source_access_cannot_confirm_known_digest():
    async def exercise():
        async with database() as sessions:
            scope, started, actions = await bound_source(sessions)
            target_id = actions["second"].id
            async with sessions() as db:
                approval = await db.scalar(
                    select(ResearchApproval).where(
                        ResearchApproval.action_id == target_id,
                        ResearchApproval.status == "pending",
                    )
                )
                # A real explicit assignment grants approval authority, not data access.
                approval.approver_user_id = scope.recorder.id
                await db.commit()
                action = await db.get(ResearchAction, target_id)
                params = tasks.ApprovalDecisionParams(
                    expected_revision=approval.revision,
                    expected_action_revision=action.revision,
                    preview_digest=approval.preview_digest,
                    reason="Cannot approve a bound value the approver cannot read",
                )
                with pytest.raises(HTTPException) as denied:
                    await http_payload(
                        tasks.approve_research_action,
                        approval.id,
                        params,
                        scope.recorder,
                        db,
                    )
                assert denied.value.status_code == 403
                await db.rollback()
            async with sessions() as db:
                action = await db.get(ResearchAction, target_id)
                assert action.status == "proposed"
                assert (
                    await db.scalar(
                        select(ResearchHumanWorkItem.id).where(
                            ResearchHumanWorkItem.action_id == target_id
                        )
                    )
                    is None
                )
                task = await db.get(ResearchTask, UUID(str(started["task_id"])))
                assert task.status == "active"

    asyncio.run(exercise())


def test_unrelated_private_branch_does_not_block_independent_root_approval_start_or_submission():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            independent, independent_version = await second_protocol(
                sessions, scope, assignee=scope.recorder
            )
            root = node(
                scope,
                "independent",
                protocol_id=str(independent.id),
                protocol_version_id=str(independent_version.id),
            )
            workflow, _ = await publish(
                sessions,
                scope,
                draft(
                    scope,
                    nodes=[node(scope), node(scope, "second"), root],
                    edges=[edge("first", "second")],
                    bindings=[mapping()],
                ),
            )
            task = await create_task(
                sessions, scope, protocol_ids=[scope.protocol.id, independent.id]
            )
            started, _ = await start_workflow(sessions, scope, workflow, task)
            actions = await actions_by_node(sessions, started["run_id"])
            await submit_record(
                sessions,
                scope,
                actions["first"].id,
                await add_record(sessions, scope, 8173.125),
            )
            async with sessions() as db:
                approval = await db.scalar(
                    select(ResearchApproval).where(
                        ResearchApproval.action_id == actions["independent"].id,
                        ResearchApproval.status == "pending",
                    )
                )
                approval.approver_user_id = scope.recorder.id
                await db.commit()
                action = await db.get(ResearchAction, actions["independent"].id)
                preview = await http_payload(
                    tasks.get_research_approval, approval.id, scope.recorder, db
                )
                assert not preview.get("workflow_data_restricted", False)
                assert not preview["action"].get("workflow_data_restricted", False)
                assert preview["run"]["workflow_data_restricted"] is True
                assert preview["preview_digest"] == approval.preview_digest
                approved = await http_payload(
                    tasks.approve_research_action,
                    approval.id,
                    tasks.ApprovalDecisionParams(
                        expected_revision=approval.revision,
                        expected_action_revision=action.revision,
                        preview_digest=approval.preview_digest,
                        reason="Approve only the independently assigned Protocol",
                    ),
                    scope.recorder,
                    db,
                )
                item_id = UUID(str(approved["action"]["work_item"]["id"]))
            async with sessions() as db:
                item = await http_payload(
                    tasks.get_research_work_item, item_id, scope.recorder, db
                )
                assert item["permissions"]["can_start"]
                assert not item.get("workflow_data_restricted", False)
                started_item = await http_payload(
                    tasks.start_research_work_item,
                    item_id,
                    tasks.WorkItemRevisionParams(expected_revision=item["revision"]),
                    scope.recorder,
                    db,
                )
                assert started_item["status"] == "in_progress"
                assert "8173.125" not in http_json(started_item)
            independent_scope = SimpleNamespace(
                **{
                    **vars(scope),
                    "protocol": independent,
                    "version": independent_version,
                }
            )
            own_record = await add_record(
                sessions, independent_scope, 409.75, author=scope.recorder
            )
            async with sessions() as db:
                result = await http_payload(
                    tasks.submit_research_work_item,
                    item_id,
                    tasks.WorkItemSubmitParams(
                        expected_revision=started_item["revision"],
                        record_id=own_record.id,
                        record_version=own_record.version,
                        note="Independent valid measurement",
                    ),
                    scope.recorder,
                    db,
                )
                assert result["status"] == "accepted"
                assert (
                    result["action"]["output_data"]["record"]["data"]["var"]["value"]
                    == 409.75
                )
                assert result["run"]["workflow_data_restricted"] is True
                assert "8173.125" not in http_json(result)
                detail = await http_payload(
                    tasks.get_research_task,
                    UUID(str(started["task_id"])),
                    scope.recorder,
                    db,
                )
                by_id = {item["id"]: item for item in detail["actions"]}
                assert not by_id[str(actions["independent"].id)].get(
                    "workflow_data_restricted", False
                )
                assert (
                    by_id[str(actions["first"].id)]["workflow_data_restricted"] is True
                )
                assert (
                    by_id[str(actions["second"].id)]["workflow_data_restricted"] is True
                )
                assert "8173.125" not in http_json(detail)

    asyncio.run(exercise())
