"""Preview-confirm APIs for Lab Research autonomy policy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.database import DBSession
from app.models.lab import Lab, LabRole, LabUser
from app.models.research_execution import (
    ResearchAutonomyGrant,
    ResearchAutonomyGrantAudit,
    ResearchAutonomyPolicy,
    ResearchAutonomyPolicyAudit,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.research_autonomy_evaluations import (
    AUTONOMY_LEVELS,
    current_autonomy_grant_snapshots,
    evaluate_autonomy_candidates,
    evaluation_for_target,
    grant_snapshot,
)
from app.services.research_autonomy_policy import (
    ResearchAutonomyPolicyConfig,
    autonomy_policy_snapshot,
    current_autonomy_policy_snapshot,
    normalize_policy,
    policy_digest,
)
from app.services.research_runtime import canonical_digest, utcnow

router = APIRouter(
    prefix="/research-autonomy-policies", tags=["research-autonomy-policies"]
)


class ResearchAutonomyPolicyDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_id: UUID
    expected_revision: int = Field(ge=0)
    policy: ResearchAutonomyPolicyConfig
    reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def normalize_reason(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("Research policy change reason cannot be blank")
        return self


class ResearchAutonomyPolicyConfirm(ResearchAutonomyPolicyDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ResearchAutonomyGrantDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_id: UUID
    target_digest: str = Field(min_length=64, max_length=64)
    expected_revision: int = Field(ge=0)
    allowed_levels: list[str] = Field(min_length=1, max_length=2)
    valid_until: datetime
    reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_grant(self):
        self.reason = self.reason.strip()
        levels = list(dict.fromkeys(self.allowed_levels))
        if not self.reason:
            raise ValueError("Autonomy grant reason cannot be blank")
        if any(item not in AUTONOMY_LEVELS for item in levels):
            raise ValueError("Unsupported autonomy level")
        if self.valid_until.tzinfo is None:
            raise ValueError("Autonomy grant expiry must include a timezone")
        self.allowed_levels = levels
        return self


class ResearchAutonomyGrantConfirm(ResearchAutonomyGrantDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ResearchAutonomyGrantRevokeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_id: UUID
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def normalize_reason(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("Autonomy grant revocation reason cannot be blank")
        return self


class ResearchAutonomyGrantRevokeConfirm(ResearchAutonomyGrantRevokeDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


async def _membership(
    db_session: DBSession,
    *,
    user: User,
    lab_id: UUID,
    manage: bool,
) -> tuple[Lab, LabUser]:
    lab = await db_session.get(Lab, lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    membership = await LabUser.find_by(
        db_session, [LabUser.lab_id == lab_id, LabUser.user_id == user.id]
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Research policy access denied")
    if manage and membership.role > LabRole.MANAGER:
        raise HTTPException(
            status_code=403,
            detail="Only Lab Owners and Managers can manage Research policy",
        )
    return lab, membership


def _policy_command(
    *,
    params: ResearchAutonomyPolicyDraft,
    current_revision: int,
) -> dict[str, Any]:
    if params.expected_revision != current_revision:
        raise HTTPException(
            status_code=409,
            detail="The Research policy changed; reload it before previewing again.",
        )
    normalized = normalize_policy(params.policy.model_dump(mode="json", by_alias=True))
    return {
        "operation": "revise_research_autonomy_policy",
        "lab_id": str(params.lab_id),
        "expected_revision": current_revision,
        "next_revision": current_revision + 1,
        "policy": normalized,
        "policy_digest": policy_digest(normalized),
        "reason": params.reason.strip(),
    }


def _response(
    *,
    policy: ResearchAutonomyPolicy | None,
    can_manage: bool,
) -> dict[str, Any]:
    return {
        "policy": autonomy_policy_snapshot(policy),
        "can_manage": can_manage,
    }


def _validate_grant_expiry(valid_until: datetime) -> None:
    now = utcnow()
    normalized = valid_until.astimezone(UTC)
    if normalized <= now:
        raise HTTPException(
            status_code=422, detail="Autonomy grant expiry is in the past"
        )
    if normalized > now + timedelta(days=365):
        raise HTTPException(
            status_code=422,
            detail="Autonomy grants cannot be valid for more than one year",
        )


async def _grant_command(
    db_session: DBSession,
    *,
    params: ResearchAutonomyGrantDraft,
    current: ResearchAutonomyGrant | None,
) -> dict[str, Any]:
    current_revision = current.revision if current is not None else 0
    if params.expected_revision != current_revision:
        raise HTTPException(
            status_code=409,
            detail="The autonomy grant changed; reload it before previewing again.",
        )
    _validate_grant_expiry(params.valid_until)
    evaluation = await evaluation_for_target(
        db_session,
        lab_id=params.lab_id,
        target_digest=params.target_digest,
    )
    if evaluation is None:
        raise HTTPException(
            status_code=404,
            detail="No supervised evaluation history exists for this autonomy target",
        )
    if not evaluation["passed"]:
        raise HTTPException(
            status_code=422,
            detail="This autonomy target has not passed its supervised evaluation",
        )
    return {
        "operation": "grant_evaluated_research_autonomy",
        "lab_id": str(params.lab_id),
        "target": evaluation["target"],
        "expected_revision": current_revision,
        "next_revision": current_revision + 1,
        "allowed_levels": params.allowed_levels,
        "evaluation": evaluation,
        "valid_until": params.valid_until.astimezone(UTC).isoformat(),
        "reason": params.reason,
    }


def _grant_revoke_command(
    *,
    grant: ResearchAutonomyGrant,
    params: ResearchAutonomyGrantRevokeDraft,
) -> dict[str, Any]:
    if grant.lab_id != params.lab_id:
        raise HTTPException(status_code=404, detail="Autonomy grant not found")
    if grant.revision != params.expected_revision:
        raise HTTPException(
            status_code=409,
            detail="The autonomy grant changed; reload it before previewing again.",
        )
    return {
        "operation": "revoke_research_autonomy_grant",
        "lab_id": str(params.lab_id),
        "grant_id": str(grant.id),
        "target_digest": grant.target_digest,
        "expected_revision": grant.revision,
        "next_revision": grant.revision + 1,
        "reason": params.reason,
    }


@router.get("")
async def get_research_autonomy_policy(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    _lab, membership = await _membership(
        db_session, user=current_user, lab_id=lab_id, manage=False
    )
    policy, _snapshot = await current_autonomy_policy_snapshot(
        db_session, lab_id=lab_id
    )
    return _response(
        policy=policy,
        can_manage=membership.role <= LabRole.MANAGER,
    )


@router.get("/audits")
async def list_research_autonomy_policy_audits(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _membership(db_session, user=current_user, lab_id=lab_id, manage=False)
    items = list(
        (
            await db_session.scalars(
                select(ResearchAutonomyPolicyAudit)
                .where(ResearchAutonomyPolicyAudit.lab_id == lab_id)
                .order_by(
                    ResearchAutonomyPolicyAudit.revision.desc(),
                    ResearchAutonomyPolicyAudit.id.desc(),
                )
                .limit(100)
            )
        ).all()
    )
    return {
        "items": [
            {
                "id": str(item.id),
                "revision": item.revision,
                "snapshot": item.snapshot,
                "reason": item.reason,
                "actor_user_id": str(item.actor_user_id),
                "created_at": item.created_at,
            }
            for item in items
        ]
    }


@router.get("/evaluations")
async def list_research_autonomy_evaluations(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _membership(db_session, user=current_user, lab_id=lab_id, manage=True)
    return {"items": await evaluate_autonomy_candidates(db_session, lab_id=lab_id)}


@router.get("/grants")
async def list_research_autonomy_grants(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    _lab, membership = await _membership(
        db_session, user=current_user, lab_id=lab_id, manage=True
    )
    return {
        "items": await current_autonomy_grant_snapshots(
            db_session, lab_id=lab_id, include_inactive=True
        ),
        "can_manage": membership.role <= LabRole.MANAGER,
    }


@router.post("/grants/preview")
async def preview_research_autonomy_grant(
    params: ResearchAutonomyGrantDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab, _membership_row = await _membership(
        db_session, user=current_user, lab_id=params.lab_id, manage=True
    )
    current = await ResearchAutonomyGrant.find_by(
        db_session,
        [
            ResearchAutonomyGrant.lab_id == params.lab_id,
            ResearchAutonomyGrant.target_digest == params.target_digest,
        ],
    )
    command = await _grant_command(db_session, params=params, current=current)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {
            "lab_id": str(lab.id),
            "lab_uid": lab.uid,
            "lab_name": lab.name,
        },
        "current": grant_snapshot(current) if current is not None else None,
        "effects": [
            "Allow only this exact capability version and executor boundary",
            "Require the Lab policy and Executor Binding to allow the same Action",
            "Pin this evaluated grant only into newly captured Research Environments",
            "Return to human confirmation when the grant expires",
        ],
    }


@router.put("/grants")
async def confirm_research_autonomy_grant(
    params: ResearchAutonomyGrantConfirm,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab, _membership_row = await _membership(
        db_session, user=current_user, lab_id=params.lab_id, manage=True
    )
    await db_session.execute(select(Lab.id).where(Lab.id == lab.id).with_for_update())
    current = await db_session.scalar(
        select(ResearchAutonomyGrant)
        .where(
            ResearchAutonomyGrant.lab_id == params.lab_id,
            ResearchAutonomyGrant.target_digest == params.target_digest,
        )
        .with_for_update()
    )
    command = await _grant_command(db_session, params=params, current=current)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(
            status_code=409,
            detail="The autonomy grant preview is stale; preview it again.",
        )
    target = command["target"]
    now = utcnow()
    if current is None:
        current = ResearchAutonomyGrant(
            lab_id=params.lab_id,
            capability_key=target["capability_key"],
            capability_version=target["capability_version"],
            executor_type=target["executor_type"],
            executor_ref=target["executor_ref"],
            executor_digest=target["executor_digest"],
            target_digest=target["target_digest"],
            revision=1,
            enabled=True,
            allowed_levels=command["allowed_levels"],
            evaluation_snapshot=command["evaluation"],
            valid_until=params.valid_until.astimezone(UTC),
            reason=params.reason,
            created_by_user_id=current_user.id,
            updated_by_user_id=current_user.id,
            created_at=now,
            updated_at=now,
        )
        db_session.add(current)
        await db_session.flush()
    else:
        current.revision = command["next_revision"]
        current.enabled = True
        current.allowed_levels = command["allowed_levels"]
        current.evaluation_snapshot = command["evaluation"]
        current.valid_until = params.valid_until.astimezone(UTC)
        current.reason = params.reason
        current.updated_by_user_id = current_user.id
        current.updated_at = now
    snapshot = grant_snapshot(current)
    db_session.add(
        ResearchAutonomyGrantAudit(
            grant_id=current.id,
            lab_id=current.lab_id,
            revision=current.revision,
            action="grant",
            snapshot=snapshot,
            reason=current.reason,
            actor_user_id=current_user.id,
        )
    )
    await db_session.commit()
    return snapshot


@router.post("/grants/{grant_id}/revoke/preview")
async def preview_research_autonomy_grant_revocation(
    grant_id: UUID,
    params: ResearchAutonomyGrantRevokeDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _membership(db_session, user=current_user, lab_id=params.lab_id, manage=True)
    grant = await db_session.get(ResearchAutonomyGrant, grant_id)
    if grant is None:
        raise HTTPException(status_code=404, detail="Autonomy grant not found")
    command = _grant_revoke_command(grant=grant, params=params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "current": grant_snapshot(grant),
        "effects": [
            "Exclude this grant from newly captured Research Environments",
            "Preserve immutable audit history and already captured environments",
            "Keep expiry enforcement active inside already captured environments",
        ],
    }


@router.post("/grants/{grant_id}/revoke")
async def confirm_research_autonomy_grant_revocation(
    grant_id: UUID,
    params: ResearchAutonomyGrantRevokeConfirm,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _membership(db_session, user=current_user, lab_id=params.lab_id, manage=True)
    grant = await db_session.scalar(
        select(ResearchAutonomyGrant)
        .where(ResearchAutonomyGrant.id == grant_id)
        .with_for_update()
    )
    if grant is None:
        raise HTTPException(status_code=404, detail="Autonomy grant not found")
    command = _grant_revoke_command(grant=grant, params=params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(
            status_code=409,
            detail="The autonomy grant revocation preview is stale; preview it again.",
        )
    grant.revision = command["next_revision"]
    grant.enabled = False
    grant.reason = params.reason
    grant.updated_by_user_id = current_user.id
    grant.updated_at = utcnow()
    snapshot = grant_snapshot(grant)
    db_session.add(
        ResearchAutonomyGrantAudit(
            grant_id=grant.id,
            lab_id=grant.lab_id,
            revision=grant.revision,
            action="revoke",
            snapshot=snapshot,
            reason=grant.reason,
            actor_user_id=current_user.id,
        )
    )
    await db_session.commit()
    return snapshot


@router.post("/preview")
async def preview_research_autonomy_policy(
    params: ResearchAutonomyPolicyDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab, _membership_row = await _membership(
        db_session, user=current_user, lab_id=params.lab_id, manage=True
    )
    current, snapshot = await current_autonomy_policy_snapshot(
        db_session, lab_id=params.lab_id
    )
    command = _policy_command(
        params=params,
        current_revision=current.revision if current is not None else 0,
    )
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {
            "lab_id": str(lab.id),
            "lab_uid": lab.uid,
            "lab_name": lab.name,
        },
        "current": snapshot,
        "effects": [
            "Create an immutable Research autonomy policy revision",
            "Apply the revision only to Research Environments captured after confirmation",
            "Keep Assisted Actions approval-gated regardless of this policy",
            "Keep people, instruments, resources, and external services approval-gated",
        ],
    }


@router.put("")
async def confirm_research_autonomy_policy(
    params: ResearchAutonomyPolicyConfirm,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab, _membership_row = await _membership(
        db_session, user=current_user, lab_id=params.lab_id, manage=True
    )
    await db_session.execute(select(Lab.id).where(Lab.id == lab.id).with_for_update())
    current, _snapshot = await current_autonomy_policy_snapshot(
        db_session, lab_id=params.lab_id, lock=True
    )
    command = _policy_command(
        params=params,
        current_revision=current.revision if current is not None else 0,
    )
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(
            status_code=409,
            detail="The Research policy preview is stale; preview it again.",
        )

    now = utcnow()
    if current is None:
        current = ResearchAutonomyPolicy(
            lab_id=params.lab_id,
            revision=1,
            policy=command["policy"],
            reason=command["reason"],
            created_by_user_id=current_user.id,
            updated_by_user_id=current_user.id,
            created_at=now,
            updated_at=now,
        )
        db_session.add(current)
        await db_session.flush()
    else:
        current.revision = command["next_revision"]
        current.policy = command["policy"]
        current.reason = command["reason"]
        current.updated_by_user_id = current_user.id
        current.updated_at = now

    snapshot = autonomy_policy_snapshot(current)
    db_session.add(
        ResearchAutonomyPolicyAudit(
            policy_id=current.id,
            lab_id=current.lab_id,
            revision=current.revision,
            snapshot=snapshot,
            reason=current.reason,
            actor_user_id=current_user.id,
        )
    )
    await db_session.commit()
    return _response(policy=current, can_manage=True)
