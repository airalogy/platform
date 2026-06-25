from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StringConstraints
from pydash import py_
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from typing_extensions import Annotated

from app.database import DBSession
from app.models.lab import Lab
from app.models.project import PermissionType, Project, ProjectRole
from app.models.project_group import (
    ProjectGroup,
    ProjectGroupProtocol,
    ProjectGroupUser,
)
from app.models.protocol import Protocol
from app.models.user import User
from app.routers.permission import check_user_permission
from app.routers.utils import UUID, UidStr

from .depends import CurrentUser, get_current_user

router = APIRouter(
    prefix="/projects/{project_id}/project_groups",
    tags=["project_groups"],
    dependencies=[Depends(get_current_user)],
)


def check_project_permission_type(project: Project):
    """Check that project uses protocol-level permissions"""
    if project.permission_type != PermissionType.PROTOCOL_LEVEL:
        raise HTTPException(
            status_code=400,
            detail="Project does not use protocol-level permissions",
        )


class ProjectGroupQueryParams(BaseModel):
    page: int = 1
    page_size: int = 10


@router.get("")
async def get_project_groups(
    project_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 10,
):
    project = await Project.find(db_session, id=project_id)
    await check_user_permission(db_session, project, current_user, "read_protocol")

    # Build query
    query = (
        select(ProjectGroup)
        .where(ProjectGroup.project_id == project_id)
        .order_by(ProjectGroup.id.asc())
    )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_count = await db_session.scalar(count_query)

    # Apply pagination
    query = query.limit(page_size).offset((page - 1) * page_size)

    result = await db_session.execute(query)
    groups = [g.ProjectGroup.as_dict() for g in result]

    return {"groups": groups, "total_count": total_count}


@router.get("/{group_id}")
async def get_project_group(
    project_id: UUID,
    group_id: int,
    db_session: DBSession,
    current_user: CurrentUser,
):
    project = await Project.find(db_session, id=project_id)
    await check_user_permission(db_session, project, current_user, "read_protocol")

    group = await ProjectGroup.find(db_session, id=group_id)
    if group.project_id != project_id:
        raise HTTPException(status_code=404, detail="Group not found")

    # Get users in this group
    user_query = (
        select(User)
        .options(selectinload(User.avatar_attachment))
        .join(ProjectGroupUser)
        .where(ProjectGroupUser.project_group_id == group_id)
        .order_by(ProjectGroupUser.id.asc())
    )
    user_result = (await db_session.execute(user_query)).all()
    users = [u.User.as_dict() for u in user_result]

    # Get protocols in this group
    protocol_query = (
        select(Protocol, ProjectGroupProtocol.role.label("group_role"))
        .join(ProjectGroupProtocol)
        .where(ProjectGroupProtocol.project_group_id == group_id)
        .order_by(ProjectGroupProtocol.role.asc())
    )
    protocol_result = (await db_session.execute(protocol_query)).all()
    protocols = [p.Protocol.as_dict(group_role=p.group_role) for p in protocol_result]

    return {"data": group.as_dict(users=users, protocols=protocols)}


class ProjectGroupAddProtocolParams(BaseModel):
    protocol_id: UUID
    role: ProjectRole


class ProjectGroupCreateParams(BaseModel):
    uid: UidStr
    name: Annotated[str, StringConstraints(max_length=64, strip_whitespace=True)]
    description: Annotated[
        str, StringConstraints(max_length=128, strip_whitespace=True)
    ] = ""
    member_ids: list[UUID] = []
    protocols: list[ProjectGroupAddProtocolParams] = []


@router.post("")
async def create_project_group(
    project_id: UUID,
    params: ProjectGroupCreateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=project_id)
    check_project_permission_type(project)
    await check_user_permission(db_session, project, current_user, "set_role_other")

    # Check if group uid already exists
    existing = await ProjectGroup.find_by(
        db_session,
        [ProjectGroup.uid == params.uid, ProjectGroup.project_id == project_id],
    )
    if existing:
        raise HTTPException(status_code=400, detail="Group uid already exists")

    group = ProjectGroup(
        project_id=project_id,
        name=params.name,
        uid=params.uid,
        description=params.description,
        create_user_id=current_user.id,
    )
    db_session.add(group)
    await db_session.flush()

    # Add protocols
    protocols = py_.uniq_by(params.protocols, lambda i: i.protocol_id)
    for p in protocols:
        protocol = await Protocol.find(db_session, id=p.protocol_id)
        if protocol.project_id != project_id:
            raise HTTPException(
                status_code=400, detail=f"Protocol {p.protocol_id} not in project"
            )
        group_protocol = ProjectGroupProtocol(
            project_group_id=group.id,
            protocol_id=p.protocol_id,
            role=p.role,
            create_user_id=current_user.id,
        )
        db_session.add(group_protocol)
    group.protocols_count = len(protocols)

    # Add members
    member_ids = py_.uniq(params.member_ids)
    for user_id in member_ids:
        await User.find(db_session, id=user_id)  # Verify user exists
        group_user = ProjectGroupUser(
            project_group_id=group.id,
            user_id=user_id,
            create_user_id=current_user.id,
        )
        db_session.add(group_user)
    group.users_count = len(member_ids)

    await db_session.commit()
    return group


class ProjectGroupUpdateParams(BaseModel):
    name: (
        Annotated[str, StringConstraints(max_length=64, strip_whitespace=True)] | None
    ) = None
    description: (
        Annotated[str, StringConstraints(max_length=128, strip_whitespace=True)] | None
    ) = None


@router.put("/{group_id}")
async def update_project_group(
    project_id: UUID,
    group_id: int,
    params: ProjectGroupUpdateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=project_id)
    check_project_permission_type(project)
    await check_user_permission(db_session, project, current_user, "set_role_other")

    group = await ProjectGroup.find(db_session, id=group_id)
    if group.project_id != project_id:
        raise HTTPException(status_code=404, detail="Group not found")

    group.set_attrs(**params.model_dump(exclude_none=True))
    await db_session.commit()
    return group


@router.delete("/{group_id}")
async def delete_project_group(
    project_id: UUID,
    group_id: int,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=project_id)
    check_project_permission_type(project)
    await check_user_permission(db_session, project, current_user, "set_role_other")

    group = await ProjectGroup.find(db_session, id=group_id)
    if group.project_id != project_id:
        raise HTTPException(status_code=404, detail="Group not found")

    # Check if group has users
    users_count = await ProjectGroupUser.count(
        db_session, [ProjectGroupUser.project_group_id == group.id]
    )
    if users_count > 0:
        raise HTTPException(status_code=400, detail="Group has users")

    # Check if group has protocols
    protocols_count = await ProjectGroupProtocol.count(
        db_session, [ProjectGroupProtocol.project_group_id == group.id]
    )
    if protocols_count > 0:
        raise HTTPException(status_code=400, detail="Group has protocols")

    await db_session.delete(group)
    await db_session.commit()
    return {"message": "success"}


# --- User Management ---


class ProjectGroupAddUserParams(BaseModel):
    user_id: UUID


@router.get("/{group_id}/users")
async def get_project_group_users(
    project_id: UUID,
    group_id: int,
    db_session: DBSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 10,
):
    project = await Project.find(db_session, id=project_id)
    await check_user_permission(db_session, project, current_user, "read_protocol")

    group = await ProjectGroup.find(db_session, id=group_id)
    if group.project_id != project_id:
        raise HTTPException(status_code=404, detail="Group not found")

    total_count = await ProjectGroupUser.count(
        db_session, [ProjectGroupUser.project_group_id == group_id]
    )

    query = (
        select(User)
        .options(selectinload(User.avatar_attachment))
        .join(ProjectGroupUser)
        .where(ProjectGroupUser.project_group_id == group_id)
        .order_by(ProjectGroupUser.id.asc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    users = (await db_session.execute(query)).scalars().all()

    return {"users": users, "total_count": total_count}


@router.post("/{group_id}/users")
async def add_user_to_project_group(
    project_id: UUID,
    group_id: int,
    params: ProjectGroupAddUserParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=project_id)
    check_project_permission_type(project)
    await check_user_permission(db_session, project, current_user, "set_role_other")

    group = await ProjectGroup.find(db_session, id=group_id)
    if group.project_id != project_id:
        raise HTTPException(status_code=404, detail="Group not found")

    user = await User.find(db_session, id=params.user_id)

    existing = await ProjectGroupUser.find_by(
        db_session,
        [
            ProjectGroupUser.project_group_id == group.id,
            ProjectGroupUser.user_id == user.id,
        ],
    )
    if existing:
        raise HTTPException(status_code=400, detail="User already in group")

    await ProjectGroupUser.create(
        db_session,
        project_group_id=group.id,
        user_id=user.id,
        create_user_id=current_user.id,
    )
    group.users_count = await ProjectGroupUser.count(
        db_session, [ProjectGroupUser.project_group_id == group.id]
    )
    await db_session.commit()

    return {"message": "success"}


@router.delete("/{group_id}/users/{user_id}")
async def delete_user_from_project_group(
    project_id: UUID,
    group_id: int,
    user_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=project_id)
    check_project_permission_type(project)
    await check_user_permission(db_session, project, current_user, "set_role_other")

    group = await ProjectGroup.find(db_session, id=group_id)
    if group.project_id != project_id:
        raise HTTPException(status_code=404, detail="Group not found")

    group_user = await ProjectGroupUser.find_by(
        db_session,
        [
            ProjectGroupUser.project_group_id == group.id,
            ProjectGroupUser.user_id == user_id,
        ],
    )
    if group_user is None:
        return {"message": "success"}

    await db_session.delete(group_user)
    await db_session.flush()

    group.users_count = await ProjectGroupUser.count(
        db_session, [ProjectGroupUser.project_group_id == group.id]
    )
    await db_session.commit()
    return {"message": "success"}


# --- Protocol Management ---


@router.get("/{group_id}/protocols")
async def get_project_group_protocols(
    project_id: UUID,
    group_id: int,
    db_session: DBSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 10,
):
    project = await Project.find(db_session, id=project_id)
    await check_user_permission(db_session, project, current_user, "read_protocol")
    lab = await Lab.find(db_session, project.lab_id)

    group = await ProjectGroup.find(db_session, id=group_id)
    if group.project_id != project_id:
        raise HTTPException(status_code=404, detail="Group not found")

    total_count = await ProjectGroupProtocol.count(
        db_session, [ProjectGroupProtocol.project_group_id == group_id]
    )

    query = (
        select(Protocol, ProjectGroupProtocol.role.label("group_role"))
        .join(ProjectGroupProtocol)
        .where(ProjectGroupProtocol.project_group_id == group_id)
        .order_by(ProjectGroupProtocol.role.asc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    result = (await db_session.execute(query)).all()
    for p in result:
        p.Protocol.lab_uid = lab.uid
        p.Protocol.project_uid = project.uid
    protocols = [p.Protocol.as_dict(group_role=p.group_role) for p in result]

    return {"protocols": protocols, "total_count": total_count}


@router.post("/{group_id}/protocols")
async def add_protocol_to_project_group(
    project_id: UUID,
    group_id: int,
    params: ProjectGroupAddProtocolParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=project_id)
    check_project_permission_type(project)
    await check_user_permission(db_session, project, current_user, "set_role_other")

    group = await ProjectGroup.find(db_session, id=group_id)
    if group.project_id != project_id:
        raise HTTPException(status_code=404, detail="Group not found")

    protocol = await Protocol.find(db_session, id=params.protocol_id)
    if protocol.project_id != project_id:
        raise HTTPException(status_code=400, detail="Protocol not in project")

    existing = await ProjectGroupProtocol.find_by(
        db_session,
        [
            ProjectGroupProtocol.project_group_id == group.id,
            ProjectGroupProtocol.protocol_id == protocol.id,
        ],
    )
    if existing:
        raise HTTPException(status_code=400, detail="Protocol already in group")

    group_protocol = ProjectGroupProtocol(
        project_group_id=group.id,
        protocol_id=protocol.id,
        role=params.role,
        create_user_id=current_user.id,
    )
    db_session.add(group_protocol)
    await db_session.flush()

    group.protocols_count = await ProjectGroupProtocol.count(
        db_session, [ProjectGroupProtocol.project_group_id == group.id]
    )
    await db_session.commit()

    return {"message": "success"}


@router.put("/{group_id}/protocols/{protocol_id}")
async def update_protocol_role_in_project_group(
    project_id: UUID,
    group_id: int,
    protocol_id: UUID,
    params: ProjectGroupAddProtocolParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=project_id)
    check_project_permission_type(project)
    await check_user_permission(db_session, project, current_user, "set_role_other")

    group = await ProjectGroup.find(db_session, id=group_id)
    if group.project_id != project_id:
        raise HTTPException(status_code=404, detail="Group not found")

    group_protocol = await ProjectGroupProtocol.find_by(
        db_session,
        [
            ProjectGroupProtocol.project_group_id == group_id,
            ProjectGroupProtocol.protocol_id == protocol_id,
        ],
    )
    if group_protocol is None:
        raise HTTPException(status_code=404, detail="Protocol not in group")

    group_protocol.role = params.role
    await db_session.commit()
    return {"message": "success"}


@router.delete("/{group_id}/protocols/{protocol_id}")
async def delete_protocol_from_project_group(
    project_id: UUID,
    group_id: int,
    protocol_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=project_id)
    check_project_permission_type(project)
    await check_user_permission(db_session, project, current_user, "set_role_other")

    group = await ProjectGroup.find(db_session, id=group_id)
    if group.project_id != project_id:
        raise HTTPException(status_code=404, detail="Group not found")

    group_protocol = await ProjectGroupProtocol.find_by(
        db_session,
        [
            ProjectGroupProtocol.project_group_id == group.id,
            ProjectGroupProtocol.protocol_id == protocol_id,
        ],
    )
    if group_protocol is None:
        return {"message": "success"}

    await db_session.delete(group_protocol)
    await db_session.flush()

    group.protocols_count = await ProjectGroupProtocol.count(
        db_session, [ProjectGroupProtocol.project_group_id == group.id]
    )
    await db_session.commit()
    return {"message": "success"}
