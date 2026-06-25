from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StringConstraints
from pydash import py_
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload
from typing_extensions import Annotated

from app.database import DBSession
from app.models.group import Group, GroupProject, GroupUser
from app.models.lab import Lab, LabRole, LabUser
from app.models.project import Project, ProjectRole, ProjectType, ProjectUser
from app.models.user import User
from app.routers.permission import check_user_permission
from app.routers.utils import UUID, UidStr

from .depends import CurrentUser, get_current_user

router = APIRouter(
    prefix="/groups", tags=["groups"], dependencies=[Depends(get_current_user)]
)


class GroupQueryParams(BaseModel):
    lab_id: UUID | None = None
    lab_uid: UidStr | None = None


async def check_user_lab_permission(db_session: DBSession, user_id: UUID, lab_id: UUID):
    user_in_lab = await LabUser.find_by(
        db_session, [LabUser.lab_id == lab_id, LabUser.user_id == user_id]
    )
    if user_in_lab is None or user_in_lab.role > LabRole.MANAGER:
        raise HTTPException(status_code=403, detail="Permission denied")


@router.get("")
async def get_groups(
    db_session: DBSession,
    params=Depends(GroupQueryParams),
    page: int = 1,
    page_size: int = 10,
):
    if params.lab_id is None and params.lab_uid is None:
        raise HTTPException(status_code=400, detail="Lab ID or UID is required")

    # Build base query with joins
    query = select(Group).join(Lab, Lab.id == Group.lab_id)

    # Build conditions
    conditions = []
    if params.lab_id is not None:
        conditions.append(Group.lab_id == params.lab_id)
    if params.lab_uid is not None:
        conditions.append(Lab.uid == params.lab_uid)

    # Apply conditions
    if conditions:
        query = query.where(*conditions)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_count = await db_session.scalar(count_query)

    # Add pagination
    query = (
        query.order_by(Group.id.asc()).limit(page_size).offset((page - 1) * page_size)
    )

    result = await db_session.execute(query)
    groups = [d.Group.as_dict() for d in result]

    return {"groups": groups, "total_count": total_count}


@router.get("/{group_id}")
async def get_group(group_id: int, db_session: DBSession):
    group = await Group.find(db_session, id=group_id)
    lab = await Lab.find(db_session, id=group.lab_id)

    query = (
        select(User)
        .options(selectinload(User.avatar_attachment))
        .join(GroupUser)
        .where(GroupUser.group_id == group_id)
        .order_by(GroupUser.id.asc())
    )
    result = (await db_session.execute(query)).all()
    users = [d.User.as_dict() for d in result]

    query2 = (
        select(Project, GroupProject.role.label("group_role"))
        .join(GroupProject)
        .where(GroupProject.group_id == group_id)
        .order_by(GroupProject.role.asc())
    )
    result2 = (await db_session.execute(query2)).all()
    projects = [d.Project.as_dict(group_role=d.group_role) for d in result2]

    return {"data": group.as_dict(lab_uid=lab.uid, users=users, projects=projects)}


class GroupAddProjectParams(BaseModel):
    project_id: UUID
    role: ProjectRole


class GroupCreateParams(BaseModel):
    lab_id: UUID
    uid: UidStr
    name: Annotated[str, StringConstraints(max_length=64, strip_whitespace=True)]
    description: Annotated[
        str, StringConstraints(max_length=128, strip_whitespace=True)
    ] = ""
    member_ids: list[UUID]
    projects: list[GroupAddProjectParams]


@router.post("")
async def create_group(
    params: GroupCreateParams, current_user: CurrentUser, db_session: DBSession
):
    group = await Group.find_by(
        db_session, [Group.uid == params.uid, Group.lab_id == params.lab_id]
    )
    if group:
        raise HTTPException(status_code=400, detail="Group name already exists")

    user_in_lab = await LabUser.find_by(
        db_session,
        [LabUser.lab_id == params.lab_id, LabUser.user_id == current_user.id],
    )

    if user_in_lab is None or user_in_lab.role > LabRole.MANAGER:
        raise HTTPException(status_code=403, detail="Permission denied")

    group = Group(
        lab_id=params.lab_id,
        name=params.name,
        uid=params.uid,
        description=params.description,
        create_user_id=current_user.id,
    )
    db_session.add(group)
    await db_session.flush()

    projects = py_.uniq_by(params.projects, lambda i: i.project_id)
    for m in projects:
        project = await Project.find(db_session, id=m.project_id)
        action = (
            "set_role_manager" if m.role <= ProjectRole.MANAGER else "set_role_other"
        )
        await check_user_permission(db_session, project, current_user, action)
        group_project = GroupProject(
            group_id=group.id,
            project_id=m.project_id,
            role=m.role,
            create_user_id=current_user.id,
        )
        db_session.add(group_project)

    group.projects_count = len(projects)

    params.member_ids.append(current_user.id)
    member_ids = py_.uniq(params.member_ids)
    for user_id in member_ids:
        group_user = GroupUser(
            group_id=group.id, user_id=user_id, create_user_id=current_user.id
        )
        db_session.add(group_user)
    group.users_count = len(member_ids)
    await db_session.commit()
    return group


class GroupUpdateParams(BaseModel):
    description: (
        Annotated[str, StringConstraints(max_length=128, strip_whitespace=True)] | None
    ) = None
    name: (
        Annotated[str, StringConstraints(max_length=128, strip_whitespace=True)] | None
    ) = None


@router.put("/groups/{group_id}")
async def update_group(
    group_id: int,
    params: GroupUpdateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    group: Group = await Group.find(db_session, id=group_id)
    await check_user_lab_permission(db_session, current_user.id, group.lab_id)

    group.set_attrs(**params.model_dump(exclude_none=True))
    await db_session.commit()
    return group


@router.delete("/{group_id}")
async def delete_group(group_id: int, current_user: CurrentUser, db_session: DBSession):
    group: Group = await Group.find(db_session, id=group_id)
    await check_user_lab_permission(db_session, current_user.id, group.lab_id)

    users_count = await GroupUser.count(db_session, [GroupUser.group_id == group.id])
    if users_count > 1:
        raise HTTPException(status_code=400, detail="Group has users")
    projects_count = await GroupProject.count(
        db_session, [GroupProject.group_id == group.id]
    )
    if projects_count > 0:
        raise HTTPException(status_code=400, detail="Group has projects")

    await db_session.delete(group)
    await db_session.commit()
    return {"message": "success"}


@router.get("/{group_id}/users")
async def get_group_users(
    group_id: int,
    db_session: DBSession,
    page: int = 1,
    page_size: int = 10,
):
    total_count = await GroupUser.count(db_session, [GroupUser.group_id == group_id])
    query = (
        select(User)
        .options(selectinload(User.avatar_attachment))
        .join(GroupUser)
        .where(GroupUser.group_id == group_id)
        .order_by(GroupUser.id.asc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    users = (await db_session.execute(query)).scalars().all()

    return {"users": users, "total_count": total_count}


class GroupAddUserParams(BaseModel):
    user_id: UUID


@router.post("/{group_id}/users")
async def add_user_to_group(
    group_id: int,
    params: GroupAddUserParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    group: Group = await Group.find(db_session, id=group_id)
    await check_user_lab_permission(db_session, current_user.id, group.lab_id)

    user = await User.find(db_session, id=params.user_id)
    exists = await GroupUser.find_by(
        db_session, [GroupUser.group_id == group.id, GroupUser.user_id == user.id]
    )
    if exists:
        raise HTTPException(status_code=400, detail="User already in group")

    await GroupUser.create(
        db_session, group_id=group.id, user_id=user.id, create_user_id=current_user.id
    )
    group_users_count = await GroupUser.count(
        db_session, where_conditions=[GroupUser.group_id == group.id]
    )
    group.users_count = group_users_count
    await db_session.commit()

    return {"message": "success"}


@router.delete("/{group_id}/users/{user_id}")
async def delete_user_from_group(
    group_id: int,
    user_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    group: Group = await Group.find(db_session, id=group_id)
    await check_user_lab_permission(db_session, current_user.id, group.lab_id)

    group_user = await GroupUser.find_by(
        db_session, [GroupUser.group_id == group.id, GroupUser.user_id == user_id]
    )
    if group_user is None:
        return {"message": "success"}

    await db_session.delete(group_user)
    await db_session.flush()

    group.users_count = await GroupUser.count(
        db_session, where_conditions=[GroupUser.group_id == group.id]
    )
    await db_session.commit()
    return {"message": "success"}


@router.get("/{group_id}/projects")
async def get_group_projects(
    group_id: int,
    db_session: DBSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 10,
):
    # 检查当前用户是否在此group中
    user_in_group = await GroupUser.find_by(
        db_session,
        [GroupUser.group_id == group_id, GroupUser.user_id == current_user.id],
    )

    if user_in_group is not None:
        # 用户在group中，返回group里的所有projects
        total_count = await GroupProject.count(
            db_session, [GroupProject.group_id == group_id]
        )
        query = (
            select(Project, GroupProject.role.label("group_role"))
            .join(GroupProject)
            .where(GroupProject.group_id == group_id)
            .order_by(GroupProject.role.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    else:
        # 用户不在group中，只返回用户有权限查看的projects
        # 权限条件：1. public project 或 2. 用户在ProjectUser中有记录
        permission_conditions = or_(
            Project.type == ProjectType.PUBLIC,
            Project.id.in_(
                select(ProjectUser.project_id).where(
                    ProjectUser.user_id == current_user.id
                )
            ),
        )

        # 统计符合权限条件的项目总数
        total_count_query = (
            select(func.count(Project.id))
            .select_from(Project)
            .join(GroupProject, GroupProject.project_id == Project.id)
            .where(and_(GroupProject.group_id == group_id, permission_conditions))
        )
        total_count = await db_session.scalar(total_count_query)

        # 查询符合权限条件的项目
        query = (
            select(Project, GroupProject.role.label("group_role"))
            .join(GroupProject, GroupProject.project_id == Project.id)
            .where(and_(GroupProject.group_id == group_id, permission_conditions))
            .order_by(GroupProject.role.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )

    result = (await db_session.execute(query)).all()
    projects = [d.Project.as_dict(group_role=d.group_role) for d in result]

    return {"projects": projects, "total_count": total_count}


@router.post("/{group_id}/projects")
async def add_project_to_group(
    group_id: int,
    params: GroupAddProjectParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    group: Group = await Group.find(db_session, id=group_id)
    await check_user_lab_permission(db_session, current_user.id, group.lab_id)

    project = await Project.find(db_session, id=params.project_id)
    if group.lab_id != project.lab_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    action = (
        "set_role_manager" if params.role <= ProjectRole.MANAGER else "set_role_other"
    )
    await check_user_permission(db_session, project, current_user, action)

    exists = await GroupProject.find_by(
        db_session,
        [GroupProject.group_id == group.id, GroupProject.project_id == project.id],
    )
    if exists:
        raise HTTPException(status_code=400, detail="Project already in group")

    group_project = GroupProject(
        group_id=group.id,
        project_id=project.id,
        role=params.role,
        create_user_id=current_user.id,
    )
    db_session.add(group_project)
    await db_session.flush()
    group.projects_count = await GroupProject.count(
        db_session, where_conditions=[GroupProject.group_id == group.id]
    )
    await db_session.commit()

    return {"message": "success"}


@router.put("/{group_id}/projects/{project_id}")
async def change_project_role_in_group(
    group_id: int,
    project_id: UUID,
    params: GroupAddProjectParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    group: Group = await Group.find(db_session, id=group_id)
    await check_user_lab_permission(db_session, current_user.id, group.lab_id)

    project = await Project.find(db_session, id=project_id)
    action = (
        "set_role_manager" if params.role <= ProjectRole.MANAGER else "set_role_other"
    )
    await check_user_permission(db_session, project, current_user, action)

    group_project = await GroupProject.find_by(
        db_session,
        [GroupProject.group_id == group_id, GroupProject.project_id == project_id],
    )
    if group_project is None:
        raise HTTPException(status_code=404, detail="Project not in group")

    group_project.role = params.role
    await db_session.commit()
    return {"message": "success"}


@router.delete("/{group_id}/projects/{project_id}")
async def delete_project_from_group(
    group_id: int,
    project_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    group = await Group.find(db_session, id=group_id)
    await check_user_lab_permission(db_session, current_user.id, group.lab_id)

    group_project = await GroupProject.find_by(
        db_session,
        [GroupProject.group_id == group.id, GroupProject.project_id == project_id],
    )
    if group_project is None:
        return {"message": "success"}

    project = await Project.find(db_session, id=project_id)
    action = (
        "set_role_manager"
        if group_project.role <= ProjectRole.MANAGER
        else "set_role_other"
    )
    await check_user_permission(db_session, project, current_user, action)

    await db_session.delete(group_project)
    await db_session.flush()

    group.projects_count = await GroupProject.count(
        db_session, where_conditions=[GroupProject.group_id == group.id]
    )
    await db_session.commit()
    return {"message": "success"}
