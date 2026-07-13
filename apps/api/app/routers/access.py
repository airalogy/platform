from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, StringConstraints, field_validator, model_validator
from sqlalchemy import func, or_, select

from app.config import config
from app.database import DBSession
from app.models.access_control import (
    AccessAuditAction,
    AccessGrant,
    AccessGrantAudit,
    AccessScopeType,
    AccessSubjectType,
)
from app.models.group import Group, GroupUser, OrganizationalUnitType
from app.models.lab import Lab, LabRole, LabUser
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.user import User
from app.services.access_control import (
    GRANTABLE_ROLE_KEYS,
    can_delegate,
    manageable_scope_ids,
    resolve_structured_access,
    role_catalog,
    utcnow_naive,
)

from .depends import CurrentUser

router = APIRouter(prefix="/access", tags=["access"])

OrganizationalUnitRole = Literal["manager", "member"]


def ensure_structured_mode() -> None:
    if config.effective_lab_structure_mode != "structured":
        raise HTTPException(status_code=404, detail="Structured access is disabled")


async def get_lab_membership(
    db_session: DBSession, lab_id: UUID, user_id: UUID
) -> LabUser | None:
    return await LabUser.find_by(
        db_session, [LabUser.lab_id == lab_id, LabUser.user_id == user_id]
    )


async def require_lab_manager(
    db_session: DBSession, lab_id: UUID, user_id: UUID
) -> LabUser:
    membership = await get_lab_membership(db_session, lab_id, user_id)
    if membership is None or membership.role > LabRole.MANAGER:
        raise HTTPException(status_code=403, detail="Permission denied")
    return membership


async def require_lab_member(
    db_session: DBSession, lab_id: UUID, user_id: UUID
) -> LabUser:
    membership = await get_lab_membership(db_session, lab_id, user_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="Permission denied")
    return membership


async def require_organizational_unit_manager(
    db_session: DBSession, unit: Group, user_id: UUID
) -> None:
    lab_membership = await get_lab_membership(db_session, unit.lab_id, user_id)
    if lab_membership is not None and lab_membership.role <= LabRole.MANAGER:
        return
    current: Group | None = unit
    visited: set[int] = set()
    while current is not None and current.id not in visited:
        visited.add(current.id)
        unit_membership = await GroupUser.find_by(
            db_session,
            [
                GroupUser.group_id == current.id,
                GroupUser.user_id == user_id,
                GroupUser.membership_role == "manager",
            ],
        )
        if unit_membership is not None:
            return
        current = (
            await Group.find_by(db_session, [Group.id == current.parent_group_id])
            if current.parent_group_id is not None
            else None
        )
    raise HTTPException(status_code=403, detail="Permission denied")


async def organizational_unit_depth(db_session: DBSession, unit: Group | None) -> int:
    depth = 0
    visited: set[int] = set()
    while unit is not None:
        if unit.id in visited:
            raise HTTPException(
                status_code=409,
                detail="Organizational-unit hierarchy contains a cycle",
            )
        visited.add(unit.id)
        depth += 1
        if unit.parent_group_id is None:
            break
        unit = await Group.find_by(db_session, [Group.id == unit.parent_group_id])
    return depth


async def validate_organizational_unit_parent(
    db_session: DBSession,
    lab_id: UUID,
    parent_group_id: int | None,
    moving_group_id: int | None = None,
) -> Group | None:
    if parent_group_id is None:
        return None
    parent = await Group.find_by(
        db_session, [Group.id == parent_group_id, Group.lab_id == lab_id]
    )
    if parent is None:
        raise HTTPException(
            status_code=400,
            detail="Parent organizational unit is not in this Lab",
        )
    if moving_group_id is not None:
        current: Group | None = parent
        visited: set[int] = set()
        while current is not None:
            if current.id == moving_group_id:
                raise HTTPException(
                    status_code=409,
                    detail="Organizational-unit hierarchy cannot contain a cycle",
                )
            if current.id in visited or current.parent_group_id is None:
                break
            visited.add(current.id)
            current = await Group.find_by(
                db_session, [Group.id == current.parent_group_id]
            )
    subtree_height = 1
    if moving_group_id is not None:
        all_units = (
            await db_session.scalars(select(Group).where(Group.lab_id == lab_id))
        ).all()
        children: dict[int, list[int]] = {}
        for item in all_units:
            if item.parent_group_id is not None:
                children.setdefault(item.parent_group_id, []).append(item.id)

        def height(unit_id: int, visited: set[int]) -> int:
            if unit_id in visited:
                raise HTTPException(
                    status_code=409,
                    detail="Organizational-unit hierarchy contains a cycle",
                )
            descendants = children.get(unit_id, [])
            if not descendants:
                return 1
            next_visited = {*visited, unit_id}
            return 1 + max(height(child_id, next_visited) for child_id in descendants)

        subtree_height = height(moving_group_id, set())
    if await organizational_unit_depth(db_session, parent) + subtree_height > 3:
        raise HTTPException(
            status_code=400,
            detail="Organizational-unit hierarchy supports at most 3 levels",
        )
    return parent


def organizational_unit_dict(
    unit: Group, members: list[dict] | None = None
) -> dict:
    state = unit.as_dict(members=members or [])
    state["parent_unit_id"] = unit.parent_group_id
    return state


@router.get("/roles")
async def get_roles(_: CurrentUser):
    ensure_structured_mode()
    return {"roles": role_catalog()}


async def list_organizational_units(
    lab_id: UUID, current_user: CurrentUser, db_session: DBSession
) -> list[dict]:
    ensure_structured_mode()
    await require_lab_member(db_session, lab_id, current_user.id)
    units = (
        await db_session.scalars(
            select(Group).where(Group.lab_id == lab_id).order_by(Group.name.asc())
        )
    ).all()
    memberships = (
        await db_session.execute(
            select(GroupUser, User)
            .join(User, User.id == GroupUser.user_id)
            .join(Group, Group.id == GroupUser.group_id)
            .where(Group.lab_id == lab_id)
            .order_by(User.name.asc())
        )
    ).all()
    by_unit: dict[int, list[dict]] = {}
    for membership, user in memberships:
        by_unit.setdefault(membership.group_id, []).append(
            {
                "id": str(user.id),
                "username": user.username,
                "name": user.name,
                "membership_role": membership.membership_role,
            }
        )
    return [organizational_unit_dict(unit, by_unit.get(unit.id)) for unit in units]


@router.get("/labs/{lab_id}/organizational-units")
async def get_organizational_units(
    lab_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    units = await list_organizational_units(lab_id, current_user, db_session)
    return {"organizational_units": units}


@router.get("/labs/{lab_id}/teams", include_in_schema=False)
async def get_teams_compat(
    lab_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    units = await list_organizational_units(lab_id, current_user, db_session)
    return {"teams": units}


class OrganizationalUnitCreateParams(BaseModel):
    lab_id: UUID
    uid: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{2,31}$")]
    name: Annotated[str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True)]
    description: Annotated[str, StringConstraints(max_length=256, strip_whitespace=True)] = ""
    unit_type: OrganizationalUnitType = OrganizationalUnitType.RESEARCH_GROUP
    parent_unit_id: int | None = None
    parent_group_id: int | None = None

    @model_validator(mode="after")
    def normalize_parent(self):
        if (
            self.parent_unit_id is not None
            and self.parent_group_id is not None
            and self.parent_unit_id != self.parent_group_id
        ):
            raise ValueError("parent_unit_id and parent_group_id must match")
        self.parent_group_id = self.parent_unit_id or self.parent_group_id
        self.parent_unit_id = self.parent_group_id
        return self


@router.post("/organizational-units")
@router.post("/teams", include_in_schema=False)
async def create_organizational_unit(
    params: OrganizationalUnitCreateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    ensure_structured_mode()
    parent = await validate_organizational_unit_parent(
        db_session, params.lab_id, params.parent_group_id
    )
    if parent is None:
        await require_lab_manager(db_session, params.lab_id, current_user.id)
    else:
        await require_organizational_unit_manager(
            db_session, parent, current_user.id
        )
    existing = await Group.find_by(
        db_session, [Group.lab_id == params.lab_id, Group.uid == params.uid]
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Organizational-unit UID already exists",
        )
    unit = Group(
        **params.model_dump(exclude={"parent_unit_id"}),
        create_user_id=current_user.id,
        users_count=0,
        projects_count=0,
    )
    db_session.add(unit)
    await db_session.flush()
    await db_session.commit()
    return organizational_unit_dict(unit)


class OrganizationalUnitUpdateParams(BaseModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True)] | None = None
    description: Annotated[str, StringConstraints(max_length=256, strip_whitespace=True)] | None = None
    unit_type: OrganizationalUnitType | None = None
    parent_unit_id: int | None = None
    parent_group_id: int | None = None
    update_parent: bool = False

    @model_validator(mode="after")
    def normalize_parent(self):
        if (
            self.parent_unit_id is not None
            and self.parent_group_id is not None
            and self.parent_unit_id != self.parent_group_id
        ):
            raise ValueError("parent_unit_id and parent_group_id must match")
        self.parent_group_id = self.parent_unit_id or self.parent_group_id
        self.parent_unit_id = self.parent_group_id
        return self


@router.put("/organizational-units/{unit_id}")
@router.put("/teams/{unit_id}", include_in_schema=False)
async def update_organizational_unit(
    unit_id: int,
    params: OrganizationalUnitUpdateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    ensure_structured_mode()
    unit = await Group.find(db_session, unit_id)
    await require_organizational_unit_manager(db_session, unit, current_user.id)
    values = params.model_dump(
        exclude_none=True,
        exclude={"update_parent", "parent_unit_id", "parent_group_id"},
    )
    if params.update_parent:
        await require_lab_manager(db_session, unit.lab_id, current_user.id)
        await validate_organizational_unit_parent(
            db_session,
            unit.lab_id,
            params.parent_group_id,
            unit.id,
        )
        values["parent_group_id"] = params.parent_group_id
    unit.set_attrs(**values)
    await db_session.commit()
    return organizational_unit_dict(unit)


@router.delete("/organizational-units/{unit_id}")
@router.delete("/teams/{unit_id}", include_in_schema=False)
async def delete_organizational_unit(
    unit_id: int,
    current_user: CurrentUser,
    db_session: DBSession,
):
    ensure_structured_mode()
    unit = await Group.find(db_session, unit_id)
    await require_organizational_unit_manager(db_session, unit, current_user.id)
    has_children = await Group.exists(db_session, [Group.parent_group_id == unit.id])
    has_members = await GroupUser.exists(db_session, [GroupUser.group_id == unit.id])
    has_grants = await AccessGrant.exists(
        db_session,
        [AccessGrant.group_id == unit.id, AccessGrant.revoked_at.is_(None)],
    )
    if has_children or has_members or has_grants:
        raise HTTPException(
            status_code=409,
            detail="Remove child units, members, and active grants before deleting the organizational unit",
        )
    await db_session.delete(unit)
    await db_session.commit()
    return {"success": True}


class OrganizationalUnitMemberParams(BaseModel):
    user_id: UUID
    membership_role: OrganizationalUnitRole = "member"


@router.post("/organizational-units/{unit_id}/members")
@router.post("/teams/{unit_id}/members", include_in_schema=False)
async def add_organizational_unit_member(
    unit_id: int,
    params: OrganizationalUnitMemberParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    ensure_structured_mode()
    unit = await Group.find(db_session, unit_id)
    await require_organizational_unit_manager(db_session, unit, current_user.id)
    await require_lab_member(db_session, unit.lab_id, params.user_id)
    membership = await GroupUser.find_by(
        db_session,
        [GroupUser.group_id == unit.id, GroupUser.user_id == params.user_id],
    )
    if membership is None:
        membership = GroupUser(
            group_id=unit.id,
            user_id=params.user_id,
            membership_role=params.membership_role,
            create_user_id=current_user.id,
        )
        db_session.add(membership)
    else:
        membership.membership_role = params.membership_role
    await db_session.flush()
    unit.users_count = await GroupUser.count(
        db_session, [GroupUser.group_id == unit.id]
    )
    await db_session.commit()
    return {"success": True}


@router.delete("/organizational-units/{unit_id}/members/{user_id}")
@router.delete(
    "/teams/{unit_id}/members/{user_id}", include_in_schema=False
)
async def remove_organizational_unit_member(
    unit_id: int,
    user_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    ensure_structured_mode()
    unit = await Group.find(db_session, unit_id)
    await require_organizational_unit_manager(db_session, unit, current_user.id)
    membership = await GroupUser.find_by(
        db_session, [GroupUser.group_id == unit.id, GroupUser.user_id == user_id]
    )
    if membership is not None:
        await db_session.delete(membership)
        await db_session.flush()
    unit.users_count = await GroupUser.count(
        db_session, [GroupUser.group_id == unit.id]
    )
    await db_session.commit()
    return {"success": True}


class GrantParams(BaseModel):
    lab_id: UUID
    subject_type: AccessSubjectType
    user_id: UUID | None = None
    org_unit_id: int | None = None
    # Compatibility input for clients using the underlying Group identifier.
    group_id: int | None = None
    scope_type: AccessScopeType
    project_id: UUID | None = None
    protocol_id: UUID | None = None
    role_key: str
    inherit_to_children: bool = True
    expires_at: datetime | None = None
    reason: Annotated[str, StringConstraints(max_length=256, strip_whitespace=True)] = ""

    @field_validator("subject_type", mode="before")
    @classmethod
    def normalize_legacy_subject_type(cls, value):
        return AccessSubjectType.ORG_UNIT if value == "team" else value

    @model_validator(mode="after")
    def validate_shape(self):
        if self.role_key not in GRANTABLE_ROLE_KEYS:
            raise ValueError("Role cannot be assigned through a scoped grant")
        if self.subject_type == AccessSubjectType.USER:
            if (
                self.user_id is None
                or self.org_unit_id is not None
                or self.group_id is not None
            ):
                raise ValueError("A user subject requires only user_id")
        else:
            if (
                self.org_unit_id is not None
                and self.group_id is not None
                and self.org_unit_id != self.group_id
            ):
                raise ValueError("org_unit_id and group_id must match")
            unit_id = self.org_unit_id or self.group_id
            if unit_id is None or self.user_id is not None:
                raise ValueError(
                    "An organizational-unit subject requires only org_unit_id"
                )
            self.org_unit_id = unit_id
            self.group_id = unit_id
        if self.scope_type == AccessScopeType.LAB:
            if self.project_id is not None or self.protocol_id is not None:
                raise ValueError("Lab scope cannot include project_id or protocol_id")
        elif self.scope_type == AccessScopeType.PROJECT:
            if self.project_id is None or self.protocol_id is not None:
                raise ValueError("Project scope requires only project_id")
        elif self.protocol_id is None:
            raise ValueError("Protocol scope requires protocol_id")
        if self.expires_at is not None:
            expires = self.expires_at.replace(tzinfo=None)
            if expires <= utcnow_naive():
                raise ValueError("expires_at must be in the future")
            self.expires_at = expires
        return self


async def validate_grant_references(db_session: DBSession, params: GrantParams) -> None:
    await Lab.find(db_session, params.lab_id)
    if params.user_id is not None:
        await require_lab_member(db_session, params.lab_id, params.user_id)
    if params.group_id is not None:
        unit = await Group.find(db_session, params.group_id)
        if unit.lab_id != params.lab_id:
            raise HTTPException(
                status_code=400,
                detail="Organizational unit is not in this Lab",
            )
    if params.project_id is not None:
        project = await Project.find(db_session, params.project_id)
        if project.lab_id != params.lab_id:
            raise HTTPException(status_code=400, detail="Project is not in this Lab")
    if params.protocol_id is not None:
        protocol = await Protocol.find(db_session, params.protocol_id)
        project = await Project.find(db_session, protocol.project_id)
        if project.lab_id != params.lab_id:
            raise HTTPException(status_code=400, detail="Protocol is not in this Lab")
        if params.project_id is not None and params.project_id != project.id:
            raise HTTPException(
                status_code=400,
                detail="Protocol does not belong to the selected Project",
            )


async def grant_scope_resources(
    db_session: DBSession, params: GrantParams
) -> tuple[Project | None, Protocol | None]:
    protocol = (
        await Protocol.find(db_session, params.protocol_id)
        if params.protocol_id is not None
        else None
    )
    project_id = params.project_id or (protocol.project_id if protocol is not None else None)
    project = await Project.find(db_session, project_id) if project_id is not None else None
    return project, protocol


async def require_grant_delegation(
    db_session: DBSession, params: GrantParams, actor_id: UUID
) -> None:
    project, protocol = await grant_scope_resources(db_session, params)
    actor = await resolve_structured_access(
        db_session, actor_id, params.lab_id, project, protocol
    )
    if not can_delegate(actor, params.role_key):
        raise HTTPException(
            status_code=403,
            detail="You cannot delegate capabilities you do not hold at this scope",
        )


def grant_state(grant: AccessGrant) -> dict:
    state = jsonable_encoder(grant.as_dict())
    state["org_unit_id"] = state["group_id"]
    return state


def add_audit(
    db_session: DBSession,
    grant: AccessGrant,
    actor_id: UUID,
    action: AccessAuditAction,
    before: dict | None,
    after: dict | None,
    reason: str,
) -> None:
    db_session.add(
        AccessGrantAudit(
            grant_id=grant.id,
            lab_id=grant.lab_id,
            actor_user_id=actor_id,
            action=action,
            before_state=before,
            after_state=after,
            reason=reason,
        )
    )


@router.get("/labs/{lab_id}/grants")
async def get_grants(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    user_id: UUID | None = None,
    org_unit_id: int | None = None,
    group_id: int | None = None,
    project_id: UUID | None = None,
    protocol_id: UUID | None = None,
    include_revoked: bool = False,
):
    ensure_structured_mode()
    membership = await require_lab_member(db_session, lab_id, current_user.id)
    if (
        org_unit_id is not None
        and group_id is not None
        and org_unit_id != group_id
    ):
        raise HTTPException(
            status_code=400,
            detail="org_unit_id and group_id must match",
        )
    unit_id = org_unit_id or group_id
    conditions = [AccessGrant.lab_id == lab_id]
    if not include_revoked:
        conditions.append(AccessGrant.revoked_at.is_(None))
    for column, value in (
        (AccessGrant.user_id, user_id),
        (AccessGrant.group_id, unit_id),
        (AccessGrant.project_id, project_id),
        (AccessGrant.protocol_id, protocol_id),
    ):
        if value is not None:
            conditions.append(column == value)
    grants = list(
        await db_session.scalars(
            select(AccessGrant).where(*conditions).order_by(AccessGrant.created_at.desc())
        )
    )
    if membership.role > LabRole.MANAGER:
        visible_grants: list[AccessGrant] = []
        for grant in grants:
            protocol = (
                await Protocol.find(db_session, grant.protocol_id)
                if grant.protocol_id is not None
                else None
            )
            grant_project_id = grant.project_id or (
                protocol.project_id if protocol is not None else None
            )
            project = (
                await Project.find(db_session, grant_project_id)
                if grant_project_id is not None
                else None
            )
            decision = await resolve_structured_access(
                db_session, current_user.id, lab_id, project, protocol
            )
            if decision.allows("access.manage"):
                visible_grants.append(grant)
        grants = visible_grants
    return {"grants": [grant_state(grant) for grant in grants]}


@router.get("/labs/{lab_id}/manageable-scopes")
async def get_manageable_scopes(
    lab_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    ensure_structured_mode()
    await require_lab_member(db_session, lab_id, current_user.id)
    lab_access, project_ids, protocol_ids = await manageable_scope_ids(
        db_session, current_user.id, lab_id
    )
    return {
        "lab": lab_access,
        "project_ids": [str(item) for item in project_ids],
        "protocol_ids": [str(item) for item in protocol_ids],
    }


@router.post("/grants")
async def create_grant(
    params: GrantParams, current_user: CurrentUser, db_session: DBSession
):
    ensure_structured_mode()
    await validate_grant_references(db_session, params)
    await require_grant_delegation(db_session, params, current_user.id)
    duplicate_conditions = [
        AccessGrant.lab_id == params.lab_id,
        AccessGrant.subject_type == params.subject_type,
        AccessGrant.scope_type == params.scope_type,
        AccessGrant.role_key == params.role_key,
        AccessGrant.revoked_at.is_(None),
    ]
    for column, value in (
        (AccessGrant.user_id, params.user_id),
        (AccessGrant.group_id, params.group_id),
        (AccessGrant.project_id, params.project_id),
        (AccessGrant.protocol_id, params.protocol_id),
    ):
        duplicate_conditions.append(column == value if value is not None else column.is_(None))
    if await AccessGrant.exists(db_session, duplicate_conditions):
        raise HTTPException(status_code=409, detail="Equivalent active grant already exists")
    grant = AccessGrant(
        **params.model_dump(exclude={"org_unit_id"}),
        created_by_user_id=current_user.id,
    )
    db_session.add(grant)
    await db_session.flush()
    add_audit(
        db_session,
        grant,
        current_user.id,
        AccessAuditAction.CREATED,
        None,
        grant_state(grant),
        params.reason,
    )
    await db_session.commit()
    return grant_state(grant)


class GrantUpdateParams(BaseModel):
    role_key: str | None = None
    inherit_to_children: bool | None = None
    expires_at: datetime | None = None
    clear_expiry: bool = False
    reason: Annotated[str, StringConstraints(max_length=256, strip_whitespace=True)] = ""

    @model_validator(mode="after")
    def validate_update(self):
        if self.role_key is not None and self.role_key not in GRANTABLE_ROLE_KEYS:
            raise ValueError("Role cannot be assigned through a scoped grant")
        if self.clear_expiry and self.expires_at is not None:
            raise ValueError("clear_expiry cannot be combined with expires_at")
        if self.expires_at is not None:
            expires = self.expires_at.replace(tzinfo=None)
            if expires <= utcnow_naive():
                raise ValueError("expires_at must be in the future")
            self.expires_at = expires
        return self


@router.put("/grants/{grant_id}")
async def update_grant(
    grant_id: UUID,
    params: GrantUpdateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    ensure_structured_mode()
    grant = await AccessGrant.find(db_session, grant_id)
    if grant.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Revoked grants cannot be updated")
    role_key = params.role_key or grant.role_key
    grant_params = GrantParams(
        **{
            **grant_state(grant),
            "role_key": role_key,
            "reason": params.reason,
            "expires_at": None,
        }
    )
    await require_grant_delegation(db_session, grant_params, current_user.id)
    before = grant_state(grant)
    grant.role_key = role_key
    if params.inherit_to_children is not None:
        grant.inherit_to_children = params.inherit_to_children
    if params.clear_expiry:
        grant.expires_at = None
    elif params.expires_at is not None:
        grant.expires_at = params.expires_at.replace(tzinfo=None)
    grant.reason = params.reason
    add_audit(
        db_session,
        grant,
        current_user.id,
        AccessAuditAction.UPDATED,
        before,
        grant_state(grant),
        params.reason,
    )
    await db_session.commit()
    return grant_state(grant)


class RevokeParams(BaseModel):
    reason: Annotated[str, StringConstraints(max_length=256, strip_whitespace=True)] = ""


@router.post("/grants/{grant_id}/revoke")
async def revoke_grant(
    grant_id: UUID,
    params: RevokeParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    ensure_structured_mode()
    grant = await AccessGrant.find(db_session, grant_id)
    if grant.revoked_at is not None:
        return grant_state(grant)
    grant_params = GrantParams(**{**grant_state(grant), "expires_at": None})
    await require_grant_delegation(db_session, grant_params, current_user.id)
    before = grant_state(grant)
    grant.revoked_at = utcnow_naive()
    grant.reason = params.reason
    add_audit(
        db_session,
        grant,
        current_user.id,
        AccessAuditAction.REVOKED,
        before,
        grant_state(grant),
        params.reason,
    )
    await db_session.commit()
    return grant_state(grant)


@router.get("/labs/{lab_id}/effective")
async def get_effective_access(
    lab_id: UUID,
    user_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    project_id: UUID | None = None,
    protocol_id: UUID | None = None,
):
    ensure_structured_mode()
    caller = await get_lab_membership(db_session, lab_id, current_user.id)
    if current_user.id != user_id and (caller is None or caller.role > LabRole.MANAGER):
        raise HTTPException(status_code=403, detail="Permission denied")
    await require_lab_member(db_session, lab_id, user_id)
    protocol = await Protocol.find(db_session, protocol_id) if protocol_id else None
    if protocol is not None:
        project_id = protocol.project_id
    project = await Project.find(db_session, project_id) if project_id else None
    if project is not None and project.lab_id != lab_id:
        raise HTTPException(status_code=400, detail="Resource is not in this Lab")
    decision = await resolve_structured_access(
        db_session, user_id, lab_id, project, protocol
    )
    return decision.as_dict()


@router.get("/labs/{lab_id}/audit")
async def get_access_audit(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
):
    ensure_structured_mode()
    decision = await resolve_structured_access(db_session, current_user.id, lab_id)
    if not decision.allows("access.audit.read"):
        raise HTTPException(status_code=403, detail="Permission denied")
    conditions = [AccessGrantAudit.lab_id == lab_id]
    total = await db_session.scalar(
        select(func.count()).select_from(AccessGrantAudit).where(*conditions)
    )
    audits = (
        await db_session.scalars(
            select(AccessGrantAudit)
            .where(*conditions)
            .order_by(AccessGrantAudit.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()
    return {"audits": [jsonable_encoder(audit.as_dict()) for audit in audits], "total_count": total}


class InheritanceParams(BaseModel):
    inherit_permissions: bool


@router.put("/projects/{project_id}/inheritance")
async def update_project_inheritance(
    project_id: UUID,
    params: InheritanceParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    ensure_structured_mode()
    project = await Project.find(db_session, project_id)
    decision = await resolve_structured_access(
        db_session, current_user.id, project.lab_id, project
    )
    if not decision.allows("access.manage"):
        raise HTTPException(status_code=403, detail="Permission denied")
    project.inherit_permissions = params.inherit_permissions
    await db_session.commit()
    return {"inherit_permissions": project.inherit_permissions}


@router.put("/protocols/{protocol_id}/inheritance")
async def update_protocol_inheritance(
    protocol_id: UUID,
    params: InheritanceParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    ensure_structured_mode()
    protocol = await Protocol.find(db_session, protocol_id)
    project = await Project.find(db_session, protocol.project_id)
    decision = await resolve_structured_access(
        db_session, current_user.id, project.lab_id, project, protocol
    )
    if not decision.allows("access.manage"):
        raise HTTPException(status_code=403, detail="Permission denied")
    protocol.inherit_permissions = params.inherit_permissions
    await db_session.commit()
    return {"inherit_permissions": protocol.inherit_permissions}
