"""Workflow governance around the existing isolated Analysis Compute lifecycle.

Compute jobs retain their analysis-only foreign key. This adapter neither runs
code nor schedules a second worker; it supplies the Task approval/budget fence.
"""

from copy import deepcopy
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.models.analysis_compute import AnalysisCompute
from app.models.project import Project
from app.models.research import ResearchAction, ResearchActionDependency
from app.models.research_execution import ResearchBudgetEntry, ResearchComputeJob
from app.models.user import User
from app.models.workflow_analysis import ResearchAnalysisAction
from app.services.analysis_compute import (
    authorize_approver,
    authorize_compute_execution,
    confirm_compute,
    emit_analysis_compute_event,
    preview_compute,
    verify_compute_contract,
)
from app.services.analysis_compute_contracts import (
    COMPUTE_ENGINE_VERSION,
    AnalysisComputeDraft,
)
from app.services.record_analyses import utcnow
from app.services.research_budget import (
    ResearchBudgetError,
    project_budget_change,
    protected_compute_reservations,
    research_budget_snapshot,
)
from app.services.research_compute import compute_environment_snapshot
from app.services.research_compute_jobs import (
    _append_compute_budget_entry,
    pinned_compute_environment,
    release_compute_budget,
    settle_compute_budget,
)
from app.services.research_runtime import require_research_capability


def is_compute(method):
    return method.engine_version == COMPUTE_ENGINE_VERSION


def governance(run, action):
    marker = (run.environment_snapshot or {}).get("manual_workflow") or {}
    node_id = (action.input_data.get("action_graph") or {}).get("node_id")
    value = (marker.get("compute_governance") or {}).get(node_id)
    if marker.get("execution_contract_version") not in {4, 5, 6, 7} or not isinstance(
        value, dict
    ):
        raise HTTPException(409, "Compute Workflow governance is not sealed")
    return value


def stable_compute_contract(summary):
    """Runner availability and display names are live, never execution inputs."""
    value = deepcopy(summary["compute"])
    value.pop("authorized_runner_count", None)
    value.pop("ready_runner_count", None)
    value["approver"].pop("name", None)
    return value


async def compute_preview(db, *, task, run, action, method, selection, persist=False):
    policy = governance(run, action)
    _, environment, revision = await pinned_compute_environment(
        db, task=task, revision_id=UUID(method.recipe["environment_revision_id"])
    )
    contract = method.compute_contract or {}
    if compute_environment_snapshot(environment, revision) != contract.get(
        "environment"
    ):
        raise HTTPException(
            409,
            "Published Compute environment is no longer the confirmed Task environment",
        )
    project = await db.get(Project, task.project_id)
    for user_id in {
        task.owner_user_id,
        run.requested_by_user_id,
        action.assignee_user_id,
    }:
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(403, "Compute recipient is unavailable")
        await require_research_capability(
            db, user=user, project=project, capability="research.compute.use"
        )
    user = await db.get(User, action.assignee_user_id)
    preview = await preview_compute(
        db,
        AnalysisComputeDraft(
            protocol_id=method.protocol_id,
            selection=selection,
            question=action.title,
            recipe=method.recipe,
            **policy,
        ),
        user,
        persist=persist,
    )
    return preview


async def approve_compute_card(
    db, *, task, run, action, bridge, method, selection, current_user
):
    policy = governance(run, action)
    if str(current_user.id) != policy["approver_user_id"]:
        raise HTTPException(
            403, "Only the explicitly confirmed Compute approver may decide"
        )
    project = await db.get(Project, task.project_id)
    await authorize_approver(
        db, method.protocol_id, project, bridge.input_snapshot, current_user
    )
    preview = await compute_preview(
        db,
        task=task,
        run=run,
        action=action,
        method=method,
        selection=selection,
        persist=True,
    )
    sealed = action.input_data["analysis_input"]["summary"]
    if preview.source_digest != bridge.source_digest or stable_compute_contract(
        preview.summary
    ) != stable_compute_contract(sealed):
        raise HTTPException(
            409, "Resolved Compute inputs or governance changed; confirm a new Workflow"
        )
    user = await db.get(User, action.assignee_user_id)
    analysis = await confirm_compute(
        db,
        user,
        preview_id=preview.id,
        preview_digest=preview.preview_digest,
        key=f"workflow-analysis:{action.id}",
    )
    bridge.analysis_preview_id = preview.id
    bridge.analysis_run_id = analysis.id
    job = await db.scalar(
        select(ResearchComputeJob).where(
            ResearchComputeJob.analysis_run_id == analysis.id
        )
    )
    details = await db.get(AnalysisCompute, analysis.id)
    await authorize_compute_execution(db, job, require_approved=False)
    try:
        await reserve_budget(
            db, task=task, run=run, action=action, job=job, actor=current_user.id
        )
    except ResearchBudgetError as error:
        raise HTTPException(409, str(error)) from error
    now = utcnow()
    details.approval_state = "approved"
    details.approval_revision += 1
    details.decided_by_user_id = current_user.id
    details.decided_at = now
    details.decision_reason = (
        "Approved the sealed Workflow analysis input and Compute contract"
    )
    job.status = "queued"
    job.approved_at = job.queued_at = now
    job.revision += 1
    await emit_analysis_compute_event(
        db,
        analysis.id,
        "compute.approved",
        actor_user_id=current_user.id,
        payload={
            "workflow_action_id": str(action.id),
            "contract_digest": details.contract_digest,
        },
        key="workflow-approved",
    )
    return analysis


async def budget_entries(db, task, job):
    return list(
        (
            await db.scalars(
                select(ResearchBudgetEntry).where(
                    ResearchBudgetEntry.task_id == task.id,
                    ResearchBudgetEntry.source_type == "compute_job",
                    ResearchBudgetEntry.source_ref == str(job.id),
                )
            )
        ).all()
    )


async def has_prepaid_compute_frontier(db, *, task, run):
    """A full budget may finish approved work, but cannot release new cards."""
    if task.budget_limit is None:
        return False
    snapshot = await research_budget_snapshot(db, task=task)
    if Decimal(snapshot["remaining"]) > 0:
        return False
    if Decimal(snapshot["committed"]) > task.budget_limit or Decimal(
        snapshot["reserved"]
    ) < protected_compute_reservations(snapshot):
        return False
    rows = (
        await db.execute(
            select(ResearchComputeJob, ResearchAction)
            .join(
                ResearchAnalysisAction,
                ResearchAnalysisAction.analysis_run_id
                == ResearchComputeJob.analysis_run_id,
            )
            .join(ResearchAction, ResearchAction.id == ResearchAnalysisAction.action_id)
            .where(
                ResearchAction.run_id == run.id,
                ResearchAction.status.in_(["queued", "running"]),
                ResearchComputeJob.status.in_(["queued", "leased", "running"]),
            )
        )
    ).all()
    for job, action in rows:
        entries = await budget_entries(db, task, job)
        if (
            len(entries) == 1
            and entries[0].kind == "reserve"
            and entries[0].amount == job.estimated_cost
            and entries[0].currency == job.currency == task.budget_currency
            and entries[0].action_id == action.id
            and entries[0].run_id == run.id
        ):
            return True
    return False


async def settlement_only_workflow(db, *, run, actions=None):
    """Prove a fixed graph needs no further executable or approval frontier.

    Only v4 failure descendants extend the all-terminal case. A deliberately
    unselected branch is not a failure: an all-active join may still execute.
    The caller must still verify the immutable graph/ACL before applying skips.
    """
    if actions is None:
        actions = list(
            (
                await db.scalars(
                    select(ResearchAction).where(ResearchAction.run_id == run.id)
                )
            ).all()
        )
    if not actions:
        return False
    terminal = {"completed", "failed", "skipped", "cancelled"}
    pending = {item.id for item in actions if item.status not in terminal}
    if not pending:
        return True
    marker = (run.environment_snapshot or {}).get("manual_workflow") or {}
    if marker.get("execution_contract_version") not in {4, 5, 6, 7} or any(
        item.status != "blocked" for item in actions if item.id in pending
    ):
        return False
    dependencies = list(
        (
            await db.scalars(
                select(ResearchActionDependency).where(
                    ResearchActionDependency.action_id.in_(
                        [item.id for item in actions]
                    )
                )
            )
        ).all()
    )
    return failure_only_frontier(actions, dependencies)


def failure_only_frontier(actions, dependencies):
    terminal = {"completed", "failed", "skipped", "cancelled"}
    pending = {item.id for item in actions if item.status not in terminal}
    if not actions or any(
        item.status != "blocked" for item in actions if item.id in pending
    ):
        return False
    settled = {item.id for item in actions if item.status in terminal}
    failed = {
        item.id
        for item in actions
        if item.status in {"failed", "cancelled"}
        or (
            item.status == "skipped"
            and (item.input_data.get("workflow_resolution") or {}).get("state")
            in {"blocked", "failed"}
        )
    }
    while pending:
        proved = {
            action_id
            for action_id in pending
            if (
                parents := {
                    item.depends_on_action_id
                    for item in dependencies
                    if item.action_id == action_id
                }
            )
            and parents <= settled
            and parents & failed
        }
        if not proved:
            return False
        pending -= proved
        settled |= proved
        failed |= proved
    return True


async def reserve_budget(db, *, task, run, action, job, actor):
    if task.budget_limit is None:
        return
    if job.estimated_cost is None or job.currency != task.budget_currency:
        raise HTTPException(
            409, "Compute estimate must be known in the Task budget currency"
        )
    if await budget_entries(db, task, job):
        raise HTTPException(409, "Compute budget was already reserved")
    amount = Decimal(job.estimated_cost)
    if amount <= 0:
        return
    snapshot = await research_budget_snapshot(db, task=task)
    if Decimal(snapshot["reserved"]) < protected_compute_reservations(snapshot):
        raise HTTPException(409, "Automatic Compute reservations are not fully funded")
    project_budget_change(
        task=task,
        snapshot=snapshot,
        kind="reserve",
        amount=amount,
        currency=job.currency,
    )
    await _append_compute_budget_entry(
        db,
        task=task,
        run=run,
        action=action,
        job=job,
        kind="reserve",
        amount=amount,
        actor_user_id=actor,
        suffix="reserve",
    )
    await db.flush()


async def authorize_workflow_compute(db, job):
    from app.services.workflow_analysis_runtime import (
        verify_analysis_execution,
        workflow_analysis_context,
    )

    context = await workflow_analysis_context(db, job.analysis_run_id)
    if context is None:
        return
    task, run, action, _ = context
    terminal_replay = job.status == "completed" and action.status == "completed"
    if not terminal_replay and (
        task.status != "active"
        or run.status in {"paused", "cancelled", "completed", "failed"}
        or action.status in {"cancelled", "failed", "skipped"}
    ):
        raise HTTPException(409, "Workflow is not accepting Compute execution")
    await verify_analysis_execution(db, task=task, run=run, action=action)
    from app.services.research_runtime import manual_workflow_dispatch_allowed

    if not terminal_replay and task.budget_limit is not None:
        entries = await budget_entries(db, task, job)
        reservations = [item for item in entries if item.kind == "reserve"]
        snapshot = await research_budget_snapshot(db, task=task)
        if (
            job.estimated_cost is None
            or job.currency != task.budget_currency
            or Decimal(snapshot["committed"]) > task.budget_limit
            or Decimal(snapshot["reserved"]) < protected_compute_reservations(snapshot)
            or (
                Decimal(job.estimated_cost) > 0
                and (
                    len(reservations) != 1
                    or reservations[0].amount != job.estimated_cost
                    or reservations[0].action_id != action.id
                    or reservations[0].run_id != run.id
                    or reservations[0].currency != job.currency
                    or any(item.kind != "reserve" for item in entries)
                )
            )
        ):
            raise HTTPException(
                409, "Compute reservation no longer covers this exact job"
            )
    if not terminal_replay and not await manual_workflow_dispatch_allowed(
        db, task=task, run=run, check_budget=False
    ):
        raise HTTPException(409, "Workflow dispatch is no longer authorized")
    _, environment, revision = await pinned_compute_environment(
        db, task=task, revision_id=job.compute_environment_revision_id
    )
    if compute_environment_snapshot(environment, revision) != job.environment_snapshot:
        raise HTTPException(409, "Compute Task environment changed")
    project = await db.get(Project, task.project_id)
    for user_id in {
        task.owner_user_id,
        run.requested_by_user_id,
        action.assignee_user_id,
    }:
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(403, "Compute recipient is unavailable")
        await require_research_capability(
            db, user=user, project=project, capability="research.compute.use"
        )


async def terminal_compute(db, job, analysis, *, usage=None, uncertain=False):
    from app.services.research_runtime import emit_research_event
    from app.services.workflow_analysis_runtime import (
        sync_workflow_analysis,
        workflow_analysis_context,
    )

    context = await workflow_analysis_context(db, analysis.id)
    if context is None:
        return
    task, run, action, _ = context
    entries = await budget_entries(db, task, job)
    reserved = any(item.kind == "reserve" for item in entries)
    settled = any(item.kind == "release" for item in entries)
    if reserved and not settled:
        if usage is not None:
            await settle_compute_budget(
                db,
                task=task,
                run=run,
                action=action,
                job=job,
                wall_seconds=usage["wall_seconds"],
            )
        elif job.started_at is None and not uncertain:
            await release_compute_budget(
                db,
                task=task,
                run=run,
                action=action,
                job=job,
                suffix="workflow-stop-release",
                actor_user_id=None,
            )
        else:
            await emit_research_event(
                db,
                task_id=task.id,
                run_id=run.id,
                action_id=action.id,
                kind="compute.budget_pending_usage",
                actor_user_id=None,
                payload={
                    "compute_job_id": str(job.id),
                    "reserved_cost": str(job.estimated_cost),
                    "currency": job.currency,
                },
                idempotency_key=f"compute-job:{job.id}:budget-pending-usage",
            )
    await db.flush()
    await sync_workflow_analysis(db, analysis)


async def stop_workflow_computes(
    db, *, run, pause=False, reason="Research Task stopped"
):
    from app.services.analysis_compute_runtime import (
        finish_analysis_failure,
        invalidate_analysis_execution,
    )

    rows = list(
        (
            await db.scalars(
                select(ResearchComputeJob)
                .join(
                    ResearchAnalysisAction,
                    ResearchAnalysisAction.analysis_run_id
                    == ResearchComputeJob.analysis_run_id,
                )
                .join(
                    ResearchAction,
                    ResearchAction.id == ResearchAnalysisAction.action_id,
                )
                .where(ResearchAction.run_id == run.id)
            )
        ).all()
    )
    from app.models.analysis import AnalysisRun
    from app.services.workflow_analysis_runtime import workflow_analysis_context

    for candidate in rows:
        await workflow_analysis_context(db, candidate.analysis_run_id)
        await db.get(AnalysisRun, candidate.analysis_run_id, with_for_update=True)
        job = await db.get(
            ResearchComputeJob,
            candidate.id,
            with_for_update=True,
            populate_existing=True,
        )
        if job.status in {"completed", "failed", "cancelled", "cancel_requested"}:
            continue
        if pause and job.status in {"queued", "awaiting_approval"}:
            continue
        if job.status in {"leased", "running"}:
            await invalidate_analysis_execution(db, job, reason=reason)
        else:
            await finish_analysis_failure(db, job, error=reason, cancelled=True)


async def bound_compute(db, analysis_id):
    return await db.scalar(
        select(ResearchAnalysisAction.action_id).where(
            ResearchAnalysisAction.analysis_run_id == analysis_id
        )
    )


async def verify_bound_compute(db, analysis):
    job = await db.scalar(
        select(ResearchComputeJob).where(
            ResearchComputeJob.analysis_run_id == analysis.id
        )
    )
    details = await db.get(AnalysisCompute, analysis.id)
    if job is None or details is None:
        raise HTTPException(409, "Workflow Compute execution is missing")
    await verify_compute_contract(db, analysis, details, job)
    return job, details


async def started_compute(db, job):
    from app.services.workflow_analysis_runtime import workflow_analysis_context

    context = await workflow_analysis_context(db, job.analysis_run_id)
    if context:
        _, _, action, _ = context
        action.status = "running"
        action.started_at = action.started_at or utcnow()
        action.revision += 1


async def validate_workflow_compute_result(db, job, result):
    from app.services.workflow_analysis_methods import get_method
    from app.services.workflow_compute_contracts import project_compute_outputs

    bridge = await db.scalar(
        select(ResearchAnalysisAction).where(
            ResearchAnalysisAction.analysis_run_id == job.analysis_run_id
        )
    )
    if bridge:
        user = await db.get(User, job.created_by_user_id)
        method = await get_method(db, user, bridge.method_publication_id)
        try:
            project_compute_outputs(
                method.compute_contract["result_schema"],
                {"computed_result": result},
                [],
                {},
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
