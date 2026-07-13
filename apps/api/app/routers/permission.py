"""
AIRA平台的基于角色的控制
"""

from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, union_all

from app.database import DBSession
from app.config import config
from app.models.group import GroupProject, GroupUser
from app.models.project import (
    PermissionType,
    Project,
    ProjectRole,
    ProjectType,
    ProjectUser,
)
from app.models.project_group import (
    ProjectGroupProtocol,
    ProjectGroupUser,
    ProtocolUser,
)
from app.models.protocol import Protocol
from app.models.record import Record
from app.models.user import User
from app.services.access_control import resolve_structured_access

# 私有项目权限
private_project_permissions = {
    "set_role_manager": {ProjectRole.OWNER},
    "set_role_other": {ProjectRole.OWNER, ProjectRole.MANAGER},
    "create_protocol": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
        ProjectRole.COLLABORATOR,
        ProjectRole.RECORDER,
    },
    "delete_protocol": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
    },
    "update_protocol": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
    },
    "read_protocol": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
        ProjectRole.COLLABORATOR,
        ProjectRole.RECORDER,
    },
    "exec_assigner": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
        ProjectRole.COLLABORATOR,
        ProjectRole.RECORDER,
    },
    "create_record": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
        ProjectRole.COLLABORATOR,
        ProjectRole.RECORDER,
    },
    "delete_record": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
    },
    "read_record": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
        ProjectRole.COLLABORATOR,
        ProjectRole.RECORDER,
    },
}

# 公共项目权限
public_project_permissions = {
    "set_role_manager": {ProjectRole.OWNER},
    "set_role_other": {ProjectRole.OWNER, ProjectRole.MANAGER},
    "create_protocol": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
        ProjectRole.COLLABORATOR,
    },
    "delete_protocol": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
    },
    "update_protocol": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
    },
    "read_protocol": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
        ProjectRole.COLLABORATOR,
        ProjectRole.RECORDER,
        ProjectRole.RECORDER_SELF_ONLY,
        ProjectRole.EXPLORER,
        ProjectRole.EXPLORER_SELF_ONLY,
        ProjectRole.VIEWER,
        ProjectRole.VIEWER_SELF_ONLY,
    },
    "exec_assigner": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
        ProjectRole.COLLABORATOR,
        ProjectRole.RECORDER,
        ProjectRole.RECORDER_SELF_ONLY,
        ProjectRole.EXPLORER,
        ProjectRole.EXPLORER_SELF_ONLY,
    },
    "create_record": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
        ProjectRole.COLLABORATOR,
        ProjectRole.RECORDER,
        ProjectRole.RECORDER_SELF_ONLY,
    },
    "delete_record": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
    },
    "read_record": {
        ProjectRole.OWNER,
        ProjectRole.MANAGER,
        ProjectRole.PROTOCOL_OWNER,
        ProjectRole.COLLABORATOR,
        ProjectRole.RECORDER,
        ProjectRole.RECORDER_SELF_ONLY,
        ProjectRole.EXPLORER,
        ProjectRole.EXPLORER_SELF_ONLY,
        ProjectRole.VIEWER,
    },
}

anonymous_read_actions = {"read_project", "read_protocol", "read_record"}
self_only_roles = {
    ProjectRole.RECORDER_SELF_ONLY,
    ProjectRole.EXPLORER_SELF_ONLY,
    ProjectRole.VIEWER_SELF_ONLY,
}


async def get_user_project_role(
    db_session: DBSession, user_id: UUID, project_id: UUID
) -> ProjectRole | None:
    """
    获取用户在项目中的角色，考虑直接角色和通过群组的角色
    返回最小的角色值（权限最高）
    """

    # 查询用户直接在项目中的角色
    direct_role_query = select(ProjectUser.role).where(
        ProjectUser.user_id == user_id, ProjectUser.project_id == project_id
    )

    # 查询用户通过群组在项目中的角色
    group_role_query = (
        select(GroupProject.role)
        .select_from(GroupProject)
        .join(GroupUser, GroupProject.group_id == GroupUser.group_id)
        .where(
            GroupProject.project_id == project_id,
            GroupUser.user_id == user_id,
        )
    )

    # 合并两个查询并获取最小值
    combined_query = select(
        func.min(union_all(direct_role_query, group_role_query).alias("roles").c.role)
    )

    result = await db_session.execute(combined_query)
    role = result.scalar()
    if role is None:
        return None
    return ProjectRole(role)


async def get_user_protocol_role(
    db_session: DBSession, user_id: UUID, protocol_id: UUID
) -> ProjectRole | None:
    """
    获取用户对特定协议的角色（用于 permission_type=2 的项目）
    检查直接分配和通过项目组的分配
    返回最小的角色值（权限最高）
    """

    # 查询用户直接对协议的角色
    direct_role_query = select(ProtocolUser.role).where(
        ProtocolUser.user_id == user_id, ProtocolUser.protocol_id == protocol_id
    )

    # 查询用户通过项目组对协议的角色
    group_role_query = (
        select(ProjectGroupProtocol.role)
        .select_from(ProjectGroupProtocol)
        .join(
            ProjectGroupUser,
            ProjectGroupProtocol.project_group_id == ProjectGroupUser.project_group_id,
        )
        .where(
            ProjectGroupProtocol.protocol_id == protocol_id,
            ProjectGroupUser.user_id == user_id,
        )
    )

    # 合并两个查询并获取最小值
    combined_query = select(
        func.min(union_all(direct_role_query, group_role_query).alias("roles").c.role)
    )

    result = await db_session.execute(combined_query)
    role = result.scalar()
    if role is None:
        return None
    return ProjectRole(role)


async def check_user_permission(
    db_session: DBSession,
    project: Project,
    user: User | None,
    action: str,
    protocol: Optional[Protocol] = None,
    record: Optional[Record] = None,
) -> ProjectRole:
    if user is None and action not in anonymous_read_actions:
        raise HTTPException(status_code=400, detail="Permission denied")

    if user is not None and config.effective_lab_structure_mode == "structured":
        structured_access = await resolve_structured_access(
            db_session,
            user.id,
            project.lab_id,
            project,
            protocol,
            include_legacy=False,
        )
        if structured_access.allows(action):
            return structured_access.strongest_project_role or ProjectRole.MANAGER

    # First, get user's project role
    role = None
    if user is not None:
        role = await get_user_project_role(
            db_session, user_id=user.id, project_id=project.id
        )

    if role is None:
        if project.type == ProjectType.PRIVATE:
            raise HTTPException(status_code=400, detail="Permission denied")
        if (
            user is None
            and project.permission_type == PermissionType.PROTOCOL_LEVEL
            and protocol is not None
        ):
            raise HTTPException(status_code=400, detail="Permission denied")
        role = ProjectRole(project.public_access_role)

    # Project owners and managers always have full access
    if role <= ProjectRole.MANAGER:
        return role

    # If user is protocol owner (creator), grant PROTOCOL_OWNER role
    if (
        user is not None
        and protocol is not None
        and protocol.user_id == user.id
        and role > ProjectRole.PROTOCOL_OWNER
    ):
        role = ProjectRole.PROTOCOL_OWNER

    # Handle protocol-level permissions when permission_type=2
    if (
        project.permission_type == PermissionType.PROTOCOL_LEVEL
        and protocol is not None
        and role > ProjectRole.PROTOCOL_OWNER
    ):
        if user is None:
            raise HTTPException(status_code=400, detail="Permission denied")

        # Check if user has protocol-level permission
        protocol_role = await get_user_protocol_role(
            db_session, user_id=user.id, protocol_id=protocol.id
        )
        if protocol_role is not None:
            role = protocol_role
        elif project.type == ProjectType.PRIVATE:
            # User has no protocol-level permission
            raise HTTPException(status_code=400, detail="Permission denied")

    if user is None and action == "read_record" and role in self_only_roles:
        raise HTTPException(status_code=400, detail="Permission denied")

    # some roles can only read their own records
    if record is not None:
        # for private project
        if (
            project.type == ProjectType.PRIVATE
            and user is not None
            and record.user_id != user.id
            and role == ProjectRole.RECORDER
        ):
            raise HTTPException(status_code=400, detail="Permission denied")

        # for public project
        if (
            project.type == ProjectType.PUBLIC
            and user is not None
            and record.user_id != user.id
            and role
            in [
                ProjectRole.RECORDER_SELF_ONLY,
                ProjectRole.EXPLORER_SELF_ONLY,
                ProjectRole.VIEWER_SELF_ONLY,
            ]
        ):
            raise HTTPException(status_code=400, detail="Permission denied")

    # project 的权限是基于协议的权限
    if action.endswith("_project"):
        action = action.replace("_project", "_protocol")

    roles = (
        private_project_permissions
        if project.type == ProjectType.PRIVATE
        else public_project_permissions
    )[action] or {}

    if role in roles:
        return role

    raise HTTPException(status_code=400, detail="Permission denied")
