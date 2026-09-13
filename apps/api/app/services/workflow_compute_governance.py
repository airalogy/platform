"""Run-specific Compute choices, separate from reusable method publications."""

from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.models.lab import LabRole, LabUser
from app.models.project import ProjectUser
from app.models.protocol import Protocol
from app.models.user import User
from app.services.analysis_compute import analysis_runner_counts, instant, money
from app.services.analysis_engine import canonical_digest
from app.services.research_budget import research_budget_snapshot
from app.services.research_compute import compute_environment_snapshot
from app.services.research_compute_jobs import (
    compute_estimated_cost,
    pinned_compute_environment,
)
from app.services.research_runtime import (
    has_research_capability,
    require_research_capability,
)
from app.services.workflow_analysis_methods import get_method
from app.services.workflow_definitions import require_protocol_read


async def approver_candidates(db, user, project):
    members = select(ProjectUser.user_id).where(ProjectUser.project_id == project.id)
    managers = select(LabUser.user_id).where(
        LabUser.lab_id == project.lab_id, LabUser.role <= LabRole.MANAGER
    )
    candidates = (
        await db.scalars(
            select(User)
            .where(or_(User.id.in_(members), User.id.in_(managers), User.id == user.id))
            .order_by(User.name, User.id)
        )
    ).all()
    return [
        {"id": candidate.id, "name": candidate.name, "username": candidate.username}
        for candidate in candidates
        if await has_research_capability(
            db, user=candidate, project=project, capability="research.approve"
        )
    ]


async def preview_compute_governance(
    db, *, user, owner, project, task, run, graph, approvers
):
    nodes = [
        node
        for node in graph.nodes
        if node.kind == "analysis" and node.analysis_kind == "compute"
    ]
    if set(approvers) - {node.node_id for node in nodes}:
        raise HTTPException(
            422, "Compute approvers must refer to Compute analysis cards"
        )
    if not nodes:
        return {}
    for actor in (user, owner):
        await require_research_capability(
            db, user=actor, project=project, capability="research.compute.use"
        )
    captured = {
        str(item.get("source_revision_id")): item
        for item in (run.environment_snapshot or {}).get("compute", [])
    }
    budget = await research_budget_snapshot(db, task=task)
    governance = {}
    for node in nodes:
        method = await get_method(db, owner, node.method_publication_id, project)
        exact = method.compute_contract["environment"]
        try:
            pinned, environment, revision = await pinned_compute_environment(
                db, task=task, revision_id=UUID(exact["source_revision_id"])
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if any(
            canonical_digest(value) != canonical_digest(exact)
            for value in (
                pinned.snapshot,
                captured.get(str(revision.id)),
                compute_environment_snapshot(environment, revision),
            )
        ):
            raise HTTPException(
                409,
                "The Task must capture the method's exact Compute Environment revision",
            )
        authorized, _ready = await analysis_runner_counts(db, revision.id)
        if not authorized:
            raise HTTPException(
                409,
                "No Compute Runner is authorized for this method's environment revision",
            )
        estimate = compute_estimated_cost(revision)
        if task.budget_limit is not None:
            if (
                estimate is None
                or not revision.currency
                or revision.currency != task.budget_currency
            ):
                raise HTTPException(
                    409,
                    "A budgeted Workflow requires a known Compute estimate in the Task currency",
                )
            if estimate > Decimal(budget["remaining"]):
                raise HTTPException(
                    409, "Compute estimate exceeds the Task's remaining budget"
                )
        selected = approvers.get(node.node_id, owner.id)
        approver = await db.get(User, selected)
        if approver is None:
            raise HTTPException(422, "Select an available Compute approver")
        await require_research_capability(
            db, user=approver, project=project, capability="research.approve"
        )
        protocol = await db.get(Protocol, method.protocol_id)
        await require_protocol_read(db, approver, project, protocol)
        governance[node.node_id] = {
            "approver_user_id": str(approver.id),
            "max_cost": money(task.budget_limit),
            "budget_currency": task.budget_currency,
            "deadline_at": instant(task.deadline_at),
        }
    return governance
