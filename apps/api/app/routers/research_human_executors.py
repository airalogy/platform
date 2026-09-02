"""Govern Lab human executor availability, capacity, and verified skills."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

from app.database import DBSession
from app.models.lab import Lab, LabRole, LabUser
from app.models.research_execution import (
    ResearchHumanExecutorProfile,
    ResearchHumanExecutorProfileAudit,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.research_executor_bindings import (
    human_executor_workloads,
    profile_is_available,
)
from app.services.research_runtime import canonical_digest, utcnow

router = APIRouter(
    prefix="/research-human-executors", tags=["research-human-executors"]
)

SKILL_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class HumanExecutorSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    level: int = Field(ge=1, le=5)
    verified: bool = False
    expires_at: datetime | None = None

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        value = value.strip().lower()
        if not SKILL_KEY_RE.fullmatch(value):
            raise ValueError(
                "Skill key must use lowercase letters, numbers, dots, hyphens, or underscores"
            )
        return value

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Skill name cannot be blank")
        return value

    @field_validator("expires_at")
    @classmethod
    def normalize_expiry(cls, value: datetime | None) -> datetime | None:
        return _utc(value)


class HumanExecutorProfileDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_id: UUID
    user_id: UUID
    expected_revision: int = Field(default=0, ge=0)
    availability: Literal["available", "unavailable"] = "available"
    available_from: datetime | None = None
    available_until: datetime | None = None
    max_concurrent_items: int = Field(default=1, ge=1, le=100)
    skills: list[HumanExecutorSkill] = Field(default_factory=list, max_length=100)
    notes: str = Field(default="", max_length=4000)
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def normalize_and_validate(self):
        self.available_from = _utc(self.available_from)
        self.available_until = _utc(self.available_until)
        self.notes = self.notes.strip()
        self.reason = self.reason.strip()
        if (
            self.available_from is not None
            and self.available_until is not None
            and self.available_from >= self.available_until
        ):
            raise ValueError("Availability start must be before its end")
        keys = [skill.key for skill in self.skills]
        if len(set(keys)) != len(keys):
            raise ValueError("Executor skills contain duplicate keys")
        return self


class HumanExecutorProfileUpdate(HumanExecutorProfileDraft):
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
        raise HTTPException(status_code=403, detail="Human Executor access denied")
    if manage and membership.role > LabRole.MANAGER:
        raise HTTPException(
            status_code=403,
            detail="Only Lab Owners and Managers can manage human executors",
        )
    return lab, membership


async def _target_user(
    db_session: DBSession,
    *,
    lab_id: UUID,
    user_id: UUID,
) -> User:
    user = await db_session.get(User, user_id)
    membership = await LabUser.find_by(
        db_session, [LabUser.lab_id == lab_id, LabUser.user_id == user_id]
    )
    if user is None or membership is None:
        raise HTTPException(
            status_code=422, detail="Executor must be a current Lab member"
        )
    return user


def _command(params: HumanExecutorProfileDraft) -> dict:
    return {
        "operation": "upsert_human_executor_profile",
        "lab_id": str(params.lab_id),
        "user_id": str(params.user_id),
        "expected_revision": params.expected_revision,
        "availability": params.availability,
        "available_from": (
            params.available_from.isoformat() if params.available_from else None
        ),
        "available_until": (
            params.available_until.isoformat() if params.available_until else None
        ),
        "max_concurrent_items": params.max_concurrent_items,
        "skills": [skill.model_dump(mode="json") for skill in params.skills],
        "notes": params.notes,
    }


def _snapshot(profile: ResearchHumanExecutorProfile) -> dict:
    return {
        "id": str(profile.id),
        "lab_id": str(profile.lab_id),
        "user_id": str(profile.user_id),
        "revision": profile.revision,
        "availability": profile.availability,
        "available_from": (
            profile.available_from.isoformat() if profile.available_from else None
        ),
        "available_until": (
            profile.available_until.isoformat() if profile.available_until else None
        ),
        "max_concurrent_items": profile.max_concurrent_items,
        "skills": profile.skills or [],
        "notes": profile.notes,
    }


def _profile_data(
    profile: ResearchHumanExecutorProfile,
    user: User,
    *,
    active_workload: int,
) -> dict:
    return {
        **_snapshot(profile),
        "user": {"id": str(user.id), "username": user.username, "name": user.name},
        "active_workload": active_workload,
        "currently_available": profile_is_available(profile),
        "created_by_user_id": str(profile.created_by_user_id),
        "updated_by_user_id": str(profile.updated_by_user_id),
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


async def _existing_profile(
    db_session: DBSession,
    *,
    lab_id: UUID,
    user_id: UUID,
    lock: bool,
) -> ResearchHumanExecutorProfile | None:
    statement = select(ResearchHumanExecutorProfile).where(
        ResearchHumanExecutorProfile.lab_id == lab_id,
        ResearchHumanExecutorProfile.user_id == user_id,
    )
    if lock:
        statement = statement.with_for_update()
    return (await db_session.scalars(statement)).first()


def _ensure_revision(
    profile: ResearchHumanExecutorProfile | None,
    expected_revision: int,
) -> None:
    actual_revision = profile.revision if profile is not None else 0
    if actual_revision != expected_revision:
        raise HTTPException(status_code=409, detail="Human Executor profile changed")


@router.get("")
async def list_human_executor_profiles(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _membership(db_session, user=current_user, lab_id=lab_id, manage=True)
    members = list(
        (
            await db_session.scalars(
                select(User)
                .join(LabUser, LabUser.user_id == User.id)
                .where(LabUser.lab_id == lab_id)
                .order_by(User.name, User.username, User.id)
            )
        ).all()
    )
    rows = list(
        (
            await db_session.execute(
                select(ResearchHumanExecutorProfile, User)
                .join(User, User.id == ResearchHumanExecutorProfile.user_id)
                .where(ResearchHumanExecutorProfile.lab_id == lab_id)
                .order_by(User.name, User.username, User.id)
            )
        ).all()
    )
    workloads = await human_executor_workloads(
        db_session, user_ids=[profile.user_id for profile, _user in rows]
    )
    return {
        "members": [
            {"id": str(user.id), "username": user.username, "name": user.name}
            for user in members
        ],
        "items": [
            _profile_data(
                profile,
                user,
                active_workload=workloads.get(profile.user_id, 0),
            )
            for profile, user in rows
        ],
    }


@router.post("/preview")
async def preview_human_executor_profile(
    params: HumanExecutorProfileDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab, _membership_row = await _membership(
        db_session, user=current_user, lab_id=params.lab_id, manage=True
    )
    user = await _target_user(db_session, lab_id=params.lab_id, user_id=params.user_id)
    profile = await _existing_profile(
        db_session, lab_id=params.lab_id, user_id=params.user_id, lock=False
    )
    _ensure_revision(profile, params.expected_revision)
    command = _command(params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {
            "lab_id": str(lab.id),
            "lab_uid": lab.uid,
            "lab_name": lab.name,
        },
        "executor": {"id": str(user.id), "username": user.username, "name": user.name},
        "effects": [
            "Create a revisioned Lab human Executor profile",
            "Use only verified, unexpired skills for automatic matching",
            "Re-evaluate availability and capacity before future work assignment",
        ],
    }


@router.put("/{user_id}")
async def update_human_executor_profile(
    user_id: UUID,
    params: HumanExecutorProfileUpdate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    if user_id != params.user_id:
        raise HTTPException(
            status_code=422, detail="Executor user does not match route"
        )
    await _membership(db_session, user=current_user, lab_id=params.lab_id, manage=True)
    await db_session.execute(
        select(Lab.id).where(Lab.id == params.lab_id).with_for_update()
    )
    user = await _target_user(db_session, lab_id=params.lab_id, user_id=params.user_id)
    profile = await _existing_profile(
        db_session, lab_id=params.lab_id, user_id=params.user_id, lock=True
    )
    _ensure_revision(profile, params.expected_revision)
    command = _command(params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Human Executor preview changed")
    action = "updated"
    if profile is None:
        action = "created"
        profile = ResearchHumanExecutorProfile(
            lab_id=params.lab_id,
            user_id=params.user_id,
            created_by_user_id=current_user.id,
            updated_by_user_id=current_user.id,
        )
        db_session.add(profile)
    else:
        profile.revision += 1
        profile.updated_by_user_id = current_user.id
        profile.updated_at = utcnow()
    profile.availability = params.availability
    profile.available_from = params.available_from
    profile.available_until = params.available_until
    profile.max_concurrent_items = params.max_concurrent_items
    profile.skills = [skill.model_dump(mode="json") for skill in params.skills]
    profile.notes = params.notes
    await db_session.flush()
    db_session.add(
        ResearchHumanExecutorProfileAudit(
            profile_id=profile.id,
            lab_id=profile.lab_id,
            revision=profile.revision,
            action=action,
            snapshot=_snapshot(profile),
            reason=params.reason,
            actor_user_id=current_user.id,
        )
    )
    await db_session.commit()
    workloads = await human_executor_workloads(db_session, user_ids=[profile.user_id])
    return _profile_data(
        profile,
        user,
        active_workload=workloads.get(profile.user_id, 0),
    )
