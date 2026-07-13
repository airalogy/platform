from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_control import AccessGrant, AccessScopeType
from app.models.group import Group, GroupProject, GroupUser
from app.models.lab import LabRole, LabUser
from app.models.project import Project, ProjectRole, ProjectUser
from app.models.project_group import (
    ProjectGroupProtocol,
    ProjectGroupUser,
    ProtocolUser,
)
from app.models.protocol import Protocol

ALL_CAPABILITIES = frozenset(
    {
        "lab.own",
        "access.manage",
        "access.audit.read",
        "team.manage",
        "project.manage",
        "role.assign.manager",
        "role.assign.other",
        "protocol.create",
        "protocol.delete",
        "protocol.update",
        "protocol.read",
        "assigner.execute",
        "record.create",
        "record.delete",
        "record.read",
    }
)

ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "lab_owner": ALL_CAPABILITIES,
    "lab_admin": ALL_CAPABILITIES - {"lab.own"},
    "project_manager": ALL_CAPABILITIES
    - {"lab.own", "team.manage", "access.audit.read", "role.assign.manager"},
    "protocol_editor": frozenset(
        {
            "protocol.create",
            "protocol.delete",
            "protocol.update",
            "protocol.read",
            "assigner.execute",
            "record.create",
            "record.delete",
            "record.read",
            "role.assign.other",
        }
    ),
    "contributor": frozenset(
        {
            "protocol.create",
            "protocol.read",
            "assigner.execute",
            "record.create",
            "record.read",
        }
    ),
    "recorder": frozenset(
        {"protocol.create", "protocol.read", "assigner.execute", "record.create", "record.read"}
    ),
    "viewer": frozenset({"protocol.read", "record.read"}),
}

GRANTABLE_ROLE_KEYS = frozenset(ROLE_CAPABILITIES) - {"lab_owner", "lab_admin"}

ROLE_LABELS = {
    "lab_owner": "Lab owner",
    "lab_admin": "Lab administrator",
    "project_manager": "Project manager",
    "protocol_editor": "Protocol editor",
    "contributor": "Contributor",
    "recorder": "Recorder",
    "viewer": "Viewer",
}

ROLE_LEGACY_PROJECT_ROLE = {
    "lab_owner": ProjectRole.OWNER,
    "lab_admin": ProjectRole.MANAGER,
    "project_manager": ProjectRole.MANAGER,
    "protocol_editor": ProjectRole.PROTOCOL_OWNER,
    "contributor": ProjectRole.COLLABORATOR,
    "recorder": ProjectRole.RECORDER,
    "viewer": ProjectRole.VIEWER,
}

ACCESS_MANAGE_ROLE_KEYS = frozenset(
    key
    for key, capabilities in ROLE_CAPABILITIES.items()
    if "access.manage" in capabilities
)

LEGACY_ROLE_KEY = {
    ProjectRole.OWNER: "project_manager",
    ProjectRole.MANAGER: "project_manager",
    ProjectRole.COLLABORATOR: "contributor",
    ProjectRole.PROTOCOL_OWNER: "protocol_editor",
    ProjectRole.RECORDER: "recorder",
    ProjectRole.RECORDER_SELF_ONLY: "recorder",
    ProjectRole.EXPLORER: "viewer",
    ProjectRole.EXPLORER_SELF_ONLY: "viewer",
    ProjectRole.VIEWER: "viewer",
    ProjectRole.VIEWER_SELF_ONLY: "viewer",
}

ACTION_CAPABILITY = {
    "set_role_manager": "role.assign.manager",
    "set_role_other": "role.assign.other",
    "create_project": "project.manage",
    "update_project": "project.manage",
    "delete_project": "project.manage",
    "create_protocol": "protocol.create",
    "delete_protocol": "protocol.delete",
    "update_protocol": "protocol.update",
    "read_protocol": "protocol.read",
    "read_project": "protocol.read",
    "exec_assigner": "assigner.execute",
    "create_record": "record.create",
    "delete_record": "record.delete",
    "read_record": "record.read",
}


@dataclass(frozen=True)
class AccessSource:
    source_type: str
    role_key: str
    scope_type: str
    scope_id: str
    inherited: bool = False
    grant_id: str | None = None
    subject_type: str | None = None
    subject_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "role_key": self.role_key,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "inherited": self.inherited,
            "grant_id": self.grant_id,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
        }


@dataclass
class AccessDecision:
    capabilities: set[str] = field(default_factory=set)
    role_keys: set[str] = field(default_factory=set)
    sources: list[AccessSource] = field(default_factory=list)

    def add(self, role_key: str, source: AccessSource) -> None:
        capabilities = ROLE_CAPABILITIES.get(role_key)
        if capabilities is None:
            return
        self.capabilities.update(capabilities)
        self.role_keys.add(role_key)
        self.sources.append(source)

    def allows(self, action_or_capability: str) -> bool:
        capability = ACTION_CAPABILITY.get(action_or_capability, action_or_capability)
        return capability in self.capabilities

    @property
    def strongest_project_role(self) -> ProjectRole | None:
        roles = [ROLE_LEGACY_PROJECT_ROLE[key] for key in self.role_keys]
        return min(roles) if roles else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "capabilities": sorted(self.capabilities),
            "role_keys": sorted(self.role_keys),
            "sources": [source.as_dict() for source in self.sources],
        }


def role_catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": ROLE_LABELS[key],
            "capabilities": sorted(capabilities),
            "grantable": key in GRANTABLE_ROLE_KEYS,
        }
        for key, capabilities in ROLE_CAPABILITIES.items()
    ]


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def team_ids_for_user(
    db_session: AsyncSession, user_id: UUID, lab_id: UUID
) -> set[int]:
    direct_ids = set(
        (
            await db_session.scalars(
                select(GroupUser.group_id)
                .join(Group, Group.id == GroupUser.group_id)
                .where(GroupUser.user_id == user_id, Group.lab_id == lab_id)
            )
        ).all()
    )
    if not direct_ids:
        return set()

    parents = dict(
        (
            await db_session.execute(
                select(Group.id, Group.parent_group_id).where(Group.lab_id == lab_id)
            )
        ).all()
    )
    result = set(direct_ids)
    for group_id in direct_ids:
        current = group_id
        visited: set[int] = set()
        while current in parents and parents[current] is not None:
            if current in visited:
                break
            visited.add(current)
            current = parents[current]
            result.add(current)
    return result


async def _project_scope_chain(
    db_session: AsyncSession, project: Project
) -> list[tuple[str, str]]:
    chain: list[tuple[str, str]] = [(AccessScopeType.PROJECT, str(project.id))]
    current = project
    visited = {project.id}
    while current.inherit_permissions and current.parent_project_id is not None:
        parent = await Project.find_by(db_session, [Project.id == current.parent_project_id])
        if parent is None or parent.id in visited or parent.lab_id != project.lab_id:
            break
        chain.append((AccessScopeType.PROJECT, str(parent.id)))
        visited.add(parent.id)
        current = parent
    if current.inherit_permissions:
        chain.append((AccessScopeType.LAB, str(project.lab_id)))
    return chain


async def resource_scope_chain(
    db_session: AsyncSession,
    lab_id: UUID,
    project: Project | None = None,
    protocol: Protocol | None = None,
) -> list[tuple[str, str]]:
    if protocol is not None:
        chain = [(AccessScopeType.PROTOCOL, str(protocol.id))]
        if not protocol.inherit_permissions:
            return chain
        if project is None:
            project = await Project.find(db_session, protocol.project_id)
        return chain + await _project_scope_chain(db_session, project)
    if project is not None:
        return await _project_scope_chain(db_session, project)
    return [(AccessScopeType.LAB, str(lab_id))]


def _grant_scope_id(grant: AccessGrant) -> str:
    if grant.scope_type == AccessScopeType.PROTOCOL:
        return str(grant.protocol_id)
    if grant.scope_type == AccessScopeType.PROJECT:
        return str(grant.project_id)
    return str(grant.lab_id)


async def resolve_structured_access(
    db_session: AsyncSession,
    user_id: UUID,
    lab_id: UUID,
    project: Project | None = None,
    protocol: Protocol | None = None,
    *,
    include_legacy: bool = True,
) -> AccessDecision:
    decision = AccessDecision()
    chain = await resource_scope_chain(db_session, lab_id, project, protocol)
    chain_positions = {scope: index for index, scope in enumerate(chain)}

    lab_user = await LabUser.find_by(
        db_session, [LabUser.lab_id == lab_id, LabUser.user_id == user_id]
    )
    if lab_user is None:
        return decision
    if lab_user is not None and lab_user.role <= LabRole.MANAGER:
        role_key = "lab_owner" if lab_user.role == LabRole.OWNER else "lab_admin"
        decision.add(
            role_key,
            AccessSource(
                source_type="lab_membership",
                role_key=role_key,
                scope_type=AccessScopeType.LAB,
                scope_id=str(lab_id),
                inherited=chain[0][0] != AccessScopeType.LAB,
                subject_type="user",
                subject_id=str(user_id),
            ),
        )

    team_ids = await team_ids_for_user(db_session, user_id, lab_id)
    subject_condition = AccessGrant.user_id == user_id
    if team_ids:
        subject_condition = or_(subject_condition, AccessGrant.group_id.in_(team_ids))
    grants = (
        await db_session.scalars(
            select(AccessGrant).where(
                AccessGrant.lab_id == lab_id,
                AccessGrant.revoked_at.is_(None),
                or_(AccessGrant.expires_at.is_(None), AccessGrant.expires_at > utcnow_naive()),
                subject_condition,
            )
        )
    ).all()
    for grant in grants:
        scope = (grant.scope_type, _grant_scope_id(grant))
        position = chain_positions.get(scope)
        if position is None or (position > 0 and not grant.inherit_to_children):
            continue
        subject_id = grant.user_id if grant.user_id is not None else grant.group_id
        decision.add(
            grant.role_key,
            AccessSource(
                source_type="grant",
                role_key=grant.role_key,
                scope_type=grant.scope_type,
                scope_id=scope[1],
                inherited=position > 0,
                grant_id=str(grant.id),
                subject_type=grant.subject_type,
                subject_id=str(subject_id),
            ),
        )

    if include_legacy and project is not None:
        await _add_legacy_project_sources(db_session, decision, user_id, project, team_ids)
        if protocol is not None:
            await _add_legacy_protocol_sources(db_session, decision, user_id, protocol)
    return decision


async def structured_project_ids_for_action(
    db_session: AsyncSession,
    user_id: UUID,
    projects: list[Project],
    action: str,
) -> set[UUID]:
    """Resolve structured grants in bulk for Project discovery queries."""
    result: set[UUID] = set()
    projects_by_lab: dict[UUID, list[Project]] = {}
    for project in projects:
        projects_by_lab.setdefault(project.lab_id, []).append(project)

    for lab_id, candidates in projects_by_lab.items():
        membership = await LabUser.find_by(
            db_session, [LabUser.lab_id == lab_id, LabUser.user_id == user_id]
        )
        if membership is None:
            continue
        if membership.role <= LabRole.MANAGER:
            role_key = (
                "lab_owner" if membership.role == LabRole.OWNER else "lab_admin"
            )
            if ACTION_CAPABILITY.get(action, action) in ROLE_CAPABILITIES[role_key]:
                result.update(project.id for project in candidates)
                continue

        team_ids = await team_ids_for_user(db_session, user_id, lab_id)
        subject_condition = AccessGrant.user_id == user_id
        if team_ids:
            subject_condition = or_(
                subject_condition, AccessGrant.group_id.in_(team_ids)
            )
        grants = (
            await db_session.scalars(
                select(AccessGrant).where(
                    AccessGrant.lab_id == lab_id,
                    AccessGrant.revoked_at.is_(None),
                    or_(
                        AccessGrant.expires_at.is_(None),
                        AccessGrant.expires_at > utcnow_naive(),
                    ),
                    subject_condition,
                )
            )
        ).all()
        capability = ACTION_CAPABILITY.get(action, action)
        grants = [
            grant
            for grant in grants
            if capability in ROLE_CAPABILITIES.get(grant.role_key, frozenset())
        ]
        if not grants:
            continue

        all_projects = (
            await db_session.scalars(select(Project).where(Project.lab_id == lab_id))
        ).all()
        project_map = {project.id: project for project in all_projects}
        protocol_project_ids: dict[UUID, UUID] = {}
        protocol_ids = [
            grant.protocol_id for grant in grants if grant.protocol_id is not None
        ]
        if protocol_ids and capability == "protocol.read":
            protocol_project_ids = dict(
                (
                    await db_session.execute(
                        select(Protocol.id, Protocol.project_id).where(
                            Protocol.id.in_(protocol_ids)
                        )
                    )
                ).all()
            )

        for project in candidates:
            chain: list[tuple[str, str]] = [
                (AccessScopeType.PROJECT, str(project.id))
            ]
            current = project
            visited = {project.id}
            while current.inherit_permissions and current.parent_project_id is not None:
                parent = project_map.get(current.parent_project_id)
                if parent is None or parent.id in visited:
                    break
                chain.append((AccessScopeType.PROJECT, str(parent.id)))
                visited.add(parent.id)
                current = parent
            if current.inherit_permissions:
                chain.append((AccessScopeType.LAB, str(lab_id)))
            positions = {scope: index for index, scope in enumerate(chain)}
            for grant in grants:
                if (
                    grant.protocol_id is not None
                    and protocol_project_ids.get(grant.protocol_id) == project.id
                ):
                    result.add(project.id)
                    break
                scope = (grant.scope_type, _grant_scope_id(grant))
                position = positions.get(scope)
                if position is not None and (
                    position == 0 or grant.inherit_to_children
                ):
                    result.add(project.id)
                    break
    return result


async def structured_protocol_ids_for_action(
    db_session: AsyncSession,
    user_id: UUID,
    project: Project,
    protocols: list[Protocol],
    action: str,
) -> set[UUID]:
    if not protocols:
        return set()

    membership = await LabUser.find_by(
        db_session,
        [LabUser.lab_id == project.lab_id, LabUser.user_id == user_id],
    )
    if membership is None:
        return set()

    capability = ACTION_CAPABILITY.get(action, action)
    if membership.role <= LabRole.MANAGER:
        role_key = "lab_owner" if membership.role == LabRole.OWNER else "lab_admin"
        if capability in ROLE_CAPABILITIES[role_key]:
            return {protocol.id for protocol in protocols}

    team_ids = await team_ids_for_user(db_session, user_id, project.lab_id)
    subject_condition = AccessGrant.user_id == user_id
    if team_ids:
        subject_condition = or_(subject_condition, AccessGrant.group_id.in_(team_ids))
    grants = list(
        (
            await db_session.scalars(
                select(AccessGrant).where(
                    AccessGrant.lab_id == project.lab_id,
                    AccessGrant.revoked_at.is_(None),
                    or_(
                        AccessGrant.expires_at.is_(None),
                        AccessGrant.expires_at > utcnow_naive(),
                    ),
                    subject_condition,
                )
            )
        ).all()
    )
    grants = [
        grant
        for grant in grants
        if capability in ROLE_CAPABILITIES.get(grant.role_key, frozenset())
    ]
    if not grants:
        return set()

    project_chain = await _project_scope_chain(db_session, project)
    result: set[UUID] = set()
    for protocol in protocols:
        chain = [(AccessScopeType.PROTOCOL, str(protocol.id))]
        if protocol.inherit_permissions:
            chain.extend(project_chain)
        positions = {scope: index for index, scope in enumerate(chain)}
        for grant in grants:
            position = positions.get((grant.scope_type, _grant_scope_id(grant)))
            if position is not None and (position == 0 or grant.inherit_to_children):
                result.add(protocol.id)
                break
    return result


async def manageable_scope_ids(
    db_session: AsyncSession, user_id: UUID, lab_id: UUID
) -> tuple[bool, set[UUID], set[UUID]]:
    membership = await LabUser.find_by(
        db_session, [LabUser.lab_id == lab_id, LabUser.user_id == user_id]
    )
    if membership is None:
        return False, set(), set()

    projects = list(
        (
            await db_session.scalars(
                select(Project).where(
                    Project.lab_id == lab_id,
                    Project.deleted_at.is_(None),
                )
            )
        ).all()
    )
    project_id_set = {project.id for project in projects}
    protocols = list(
        (
            await db_session.scalars(
                select(Protocol).where(
                    Protocol.project_id.in_(project_id_set),
                    Protocol.deleted_at.is_(None),
                )
            )
        ).all()
    ) if project_id_set else []

    if membership.role <= LabRole.MANAGER:
        return True, project_id_set, {protocol.id for protocol in protocols}

    lab_decision = await resolve_structured_access(
        db_session, user_id, lab_id, include_legacy=False
    )
    lab_access = lab_decision.allows("access.manage")
    structured_project_ids = await structured_project_ids_for_action(
        db_session, user_id, projects, "access.manage"
    )
    team_ids = await team_ids_for_user(db_session, user_id, lab_id)

    legacy_project_ids = set(
        (
            await db_session.scalars(
                select(ProjectUser.project_id).where(
                    ProjectUser.user_id == user_id,
                    ProjectUser.project_id.in_(project_id_set),
                    ProjectUser.role <= ProjectRole.MANAGER,
                )
            )
        ).all()
    ) if project_id_set else set()
    if team_ids and project_id_set:
        legacy_project_ids.update(
            (
                await db_session.scalars(
                    select(GroupProject.project_id).where(
                        GroupProject.group_id.in_(team_ids),
                        GroupProject.project_id.in_(project_id_set),
                        GroupProject.role <= ProjectRole.MANAGER,
                    )
                )
            ).all()
        )
    project_ids = structured_project_ids | legacy_project_ids

    protocol_ids = {
        protocol.id
        for protocol in protocols
        if protocol.project_id in legacy_project_ids
        or (
            protocol.inherit_permissions
            and protocol.project_id in structured_project_ids
        )
    }
    protocol_id_set = {protocol.id for protocol in protocols}
    if protocol_id_set:
        subject_condition = AccessGrant.user_id == user_id
        if team_ids:
            subject_condition = or_(
                subject_condition, AccessGrant.group_id.in_(team_ids)
            )
        exact_protocol_ids = (
            await db_session.scalars(
                select(AccessGrant.protocol_id).where(
                    AccessGrant.lab_id == lab_id,
                    AccessGrant.scope_type == AccessScopeType.PROTOCOL,
                    AccessGrant.protocol_id.in_(protocol_id_set),
                    AccessGrant.role_key.in_(ACCESS_MANAGE_ROLE_KEYS),
                    AccessGrant.revoked_at.is_(None),
                    or_(
                        AccessGrant.expires_at.is_(None),
                        AccessGrant.expires_at > utcnow_naive(),
                    ),
                    subject_condition,
                )
            )
        ).all()
        protocol_ids.update(item for item in exact_protocol_ids if item is not None)
        protocol_ids.update(
            (
                await db_session.scalars(
                    select(ProtocolUser.protocol_id).where(
                        ProtocolUser.user_id == user_id,
                        ProtocolUser.protocol_id.in_(protocol_id_set),
                        ProtocolUser.role <= ProjectRole.MANAGER,
                    )
                )
            ).all()
        )
        protocol_ids.update(
            (
                await db_session.scalars(
                    select(ProjectGroupProtocol.protocol_id)
                    .join(
                        ProjectGroupUser,
                        ProjectGroupProtocol.project_group_id
                        == ProjectGroupUser.project_group_id,
                    )
                    .where(
                        ProjectGroupUser.user_id == user_id,
                        ProjectGroupProtocol.protocol_id.in_(protocol_id_set),
                        ProjectGroupProtocol.role <= ProjectRole.MANAGER,
                    )
                )
            ).all()
        )
    return lab_access, project_ids, protocol_ids


async def _add_legacy_project_sources(
    db_session: AsyncSession,
    decision: AccessDecision,
    user_id: UUID,
    project: Project,
    team_ids: set[int],
) -> None:
    direct_roles = (
        await db_session.scalars(
            select(ProjectUser.role).where(
                ProjectUser.user_id == user_id, ProjectUser.project_id == project.id
            )
        )
    ).all()
    team_roles: list[int] = []
    if team_ids:
        team_roles = list(
            (
                await db_session.scalars(
                    select(GroupProject.role).where(
                        GroupProject.group_id.in_(team_ids),
                        GroupProject.project_id == project.id,
                    )
                )
            ).all()
        )
    for role_value in [*direct_roles, *team_roles]:
        role = ProjectRole(role_value)
        role_key = LEGACY_ROLE_KEY[role]
        decision.add(
            role_key,
            AccessSource(
                source_type="legacy_project_role",
                role_key=role_key,
                scope_type=AccessScopeType.PROJECT,
                scope_id=str(project.id),
                subject_type="user",
                subject_id=str(user_id),
            ),
        )


async def _add_legacy_protocol_sources(
    db_session: AsyncSession,
    decision: AccessDecision,
    user_id: UUID,
    protocol: Protocol,
) -> None:
    direct_roles = (
        await db_session.scalars(
            select(ProtocolUser.role).where(
                ProtocolUser.user_id == user_id, ProtocolUser.protocol_id == protocol.id
            )
        )
    ).all()
    project_group_roles = (
        await db_session.scalars(
            select(ProjectGroupProtocol.role)
            .join(
                ProjectGroupUser,
                ProjectGroupProtocol.project_group_id == ProjectGroupUser.project_group_id,
            )
            .where(
                ProjectGroupProtocol.protocol_id == protocol.id,
                ProjectGroupUser.user_id == user_id,
            )
        )
    ).all()
    for role_value in [*direct_roles, *project_group_roles]:
        role = ProjectRole(role_value)
        role_key = LEGACY_ROLE_KEY[role]
        decision.add(
            role_key,
            AccessSource(
                source_type="legacy_protocol_role",
                role_key=role_key,
                scope_type=AccessScopeType.PROTOCOL,
                scope_id=str(protocol.id),
                subject_type="user",
                subject_id=str(user_id),
            ),
        )


def can_delegate(actor: AccessDecision, role_key: str) -> bool:
    requested = ROLE_CAPABILITIES.get(role_key)
    return (
        role_key in GRANTABLE_ROLE_KEYS
        and requested is not None
        and "access.manage" in actor.capabilities
        and requested.issubset(actor.capabilities)
    )
