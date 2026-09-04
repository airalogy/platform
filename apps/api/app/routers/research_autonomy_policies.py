"""Preview-confirm APIs for Lab Research autonomy policy."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.database import DBSession
from app.models.lab import Lab, LabRole, LabUser
from app.models.research_execution import (
    ResearchAutonomyPolicy,
    ResearchAutonomyPolicyAudit,
)
from app.models.user import User
from app.routers.depends import CurrentUser
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
