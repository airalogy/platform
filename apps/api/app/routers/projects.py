from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StringConstraints
from pydash import py_
from sqlalchemy import and_, case, delete, distinct, func, or_, select
from sqlalchemy.orm import aliased, selectinload
from typing_extensions import Annotated

from app.config import config
from app.database import DBSession
from app.models.group import Group, GroupProject, GroupUser
from app.models.lab import Lab, LabUser
from app.models.project import (
    PermissionType,
    Project,
    ProjectRole,
    ProjectStatus,
    ProjectType,
    ProjectUser,
)
from app.models.protocol import Protocol
from app.models.user import User
from app.models.user_alias import UserAlias
from app.routers.permission import (
    check_user_permission,
    private_project_permissions,
    public_project_permissions,
)
from app.services.access_control import structured_project_ids_for_action

DEFAULT_PROJECT_UIDS = {"public_protocols", "lab_protocols"}


def is_protected_default_project(uid: str) -> bool:
    return uid in DEFAULT_PROJECT_UIDS or (
        config.is_single_lab and uid == config.SINGLE_LAB_DEFAULT_PROJECT_UID
    )

from .depends import CurrentUser, OptionalCurrentUser
from .utils import UidStr

router = APIRouter(prefix="/projects", tags=["projects"])


def get_project_hierarchy_kwargs(
    project: Project,
    *,
    parent_project: Project | None = None,
    children_count: int = 0,
):
    return {
        "parent_project_uid": parent_project.uid if parent_project else None,
        "parent_project_name": parent_project.name if parent_project else None,
        "children_count": children_count,
        "has_children": children_count > 0,
        "depth": 1 if project.parent_project_id else 0,
    }


def build_project_permission_condition(
    current_user: CurrentUser | None,
    permission_action: str | None = None,
):
    if current_user is None:
        if permission_action is None:
            return Project.type == ProjectType.PUBLIC

        if permission_action.endswith("_project"):
            permission_action = permission_action.replace("_project", "_protocol")

        public_roles = tuple(public_project_permissions.get(permission_action, set()))
        if not public_roles:
            raise HTTPException(status_code=400, detail="Invalid permission action")

        return and_(
            Project.type == ProjectType.PUBLIC,
            Project.public_access_role.in_(public_roles),
        )

    # Subquery for projects user has direct access to via ProjectUser
    direct_access_subquery = select(ProjectUser.project_id).where(
        ProjectUser.user_id == current_user.id
    )

    # Subquery for projects user has access to via groups
    group_access_subquery = (
        select(GroupProject.project_id)
        .join(GroupUser, GroupProject.group_id == GroupUser.group_id)
        .where(GroupUser.user_id == current_user.id)
    )

    if permission_action is None:
        return or_(
            Project.type == ProjectType.PUBLIC,
            Project.id.in_(direct_access_subquery),
            Project.id.in_(group_access_subquery),
        )

    if permission_action.endswith("_project"):
        permission_action = permission_action.replace("_project", "_protocol")

    private_roles = tuple(private_project_permissions.get(permission_action, set()))
    public_roles = tuple(public_project_permissions.get(permission_action, set()))
    if not private_roles and not public_roles:
        raise HTTPException(status_code=400, detail="Invalid permission action")

    direct_private_subquery = select(ProjectUser.project_id).where(
        ProjectUser.user_id == current_user.id,
        ProjectUser.role.in_(private_roles),
    )
    direct_public_subquery = select(ProjectUser.project_id).where(
        ProjectUser.user_id == current_user.id,
        ProjectUser.role.in_(public_roles),
    )
    group_private_subquery = (
        select(GroupProject.project_id)
        .join(GroupUser, GroupProject.group_id == GroupUser.group_id)
        .where(
            GroupUser.user_id == current_user.id,
            GroupProject.role.in_(private_roles),
        )
    )
    group_public_subquery = (
        select(GroupProject.project_id)
        .join(GroupUser, GroupProject.group_id == GroupUser.group_id)
        .where(
            GroupUser.user_id == current_user.id,
            GroupProject.role.in_(public_roles),
        )
    )

    return or_(
        and_(
            Project.type == ProjectType.PRIVATE,
            or_(
                Project.id.in_(direct_private_subquery),
                Project.id.in_(group_private_subquery),
            ),
        ),
        and_(
            Project.type == ProjectType.PUBLIC,
            or_(
                Project.public_access_role.in_(public_roles),
                Project.id.in_(direct_public_subquery),
                Project.id.in_(group_public_subquery),
            ),
        ),
    )


async def get_parent_project_for_create(
    params,
    current_user: CurrentUser,
    db_session: DBSession,
) -> Project | None:
    if params.parent_project_id is None:
        return None

    parent_project = await Project.find_by(
        db_session,
        [Project.id == params.parent_project_id, Project.deleted_at.is_(None)],
    )
    if parent_project is None:
        raise HTTPException(status_code=404, detail="Parent project not found")
    if parent_project.lab_id != params.lab_id:
        raise HTTPException(
            status_code=400, detail="Parent project must belong to the same lab"
        )
    depth = 1
    current_parent = parent_project
    visited = {current_parent.id}
    while current_parent.parent_project_id is not None:
        current_parent = await Project.find_by(
            db_session, [Project.id == current_parent.parent_project_id]
        )
        if current_parent is None or current_parent.id in visited:
            raise HTTPException(status_code=409, detail="Invalid Project hierarchy")
        visited.add(current_parent.id)
        depth += 1
    if depth >= 3:
        raise HTTPException(
            status_code=400, detail="Project hierarchy supports at most 3 levels"
        )
    if is_protected_default_project(parent_project.uid):
        raise HTTPException(
            status_code=400, detail="Default projects cannot be used as parent projects"
        )

    await check_user_permission(
        db_session,
        project=parent_project,
        user=current_user,
        action="set_role_other",
    )
    return parent_project


@router.get("/check_uid")
async def check_project_uid_exists(
    lab_uid: UidStr,
    uid: UidStr,
    db_session: DBSession,
):
    lab = await Lab.find_by(db_session, [Lab.uid == lab_uid])
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")

    await check_project_uid(db_session, lab.id, uid)
    return {"result": True, "message": "UID is valid and available"}


@router.get("")
async def get_projects(
    db_session: DBSession,
    current_user: OptionalCurrentUser,
    lab_id: UUID | None = None,
    lab_uid: UidStr | None = None,
    parent_project_id: UUID | None = None,
    root_only: bool = False,
    uid: UidStr | None = None,
    name: str | None = None,
    permission_action: Literal["create_protocol"] | None = None,
    page: int = 1,
    page_size: int = 10,
):
    # Start with base conditions
    conditions = [Project.deleted_at.is_(None)]

    # Handle lab_id directly
    if lab_id is not None:
        conditions.append(Project.lab_id == lab_id)
    if lab_uid is not None:
        conditions.append(Lab.uid == lab_uid)
    if lab_id is None and lab_uid is None and permission_action is None:
        raise HTTPException(
            status_code=400, detail="lab_id or lab_uid is required"
        )

    if parent_project_id is not None:
        conditions.append(Project.parent_project_id == parent_project_id)
    elif root_only:
        conditions.append(Project.parent_project_id.is_(None))

    # Handle uid
    if uid is not None:
        conditions.append(Project.uid == uid)

    # Handle name
    if name is not None:
        conditions.append(Project.name.ilike(f"%{name}%"))

    permission_condition = build_project_permission_condition(
        current_user=current_user,
        permission_action=permission_action,
    )
    if (
        current_user is not None
        and config.effective_lab_structure_mode == "structured"
    ):
        candidate_projects = (
            await db_session.scalars(
                select(Project).join(Lab).where(*conditions)
            )
        ).all()
        structured_ids = await structured_project_ids_for_action(
            db_session,
            current_user.id,
            list(candidate_projects),
            permission_action or "read_project",
        )
        if structured_ids:
            permission_condition = or_(
                permission_condition, Project.id.in_(structured_ids)
            )
    conditions.append(permission_condition)

    ParentProject = aliased(Project)
    ChildProject = aliased(Project)
    child_counts_subquery = (
        select(
            ChildProject.parent_project_id.label("parent_id"),
            func.count(ChildProject.id).label("children_count"),
        )
        .where(
            ChildProject.deleted_at.is_(None),
            ChildProject.parent_project_id.is_not(None),
        )
        .group_by(ChildProject.parent_project_id)
        .subquery()
    )

    # Build base query with counts
    query = (
        select(
            Project,
            Lab.name.label("lab_name"),
            Lab.uid.label("lab_uid"),
            ParentProject.uid.label("parent_project_uid"),
            ParentProject.name.label("parent_project_name"),
            func.coalesce(child_counts_subquery.c.children_count, 0).label(
                "children_count"
            ),
            func.count(distinct(ProjectUser.id)).label("users_count"),
            func.count(distinct(Protocol.id)).label("protocols_count"),
        )
        .join(Lab, Lab.id == Project.lab_id)
        .outerjoin(ParentProject, ParentProject.id == Project.parent_project_id)
        .outerjoin(child_counts_subquery, child_counts_subquery.c.parent_id == Project.id)
        .outerjoin(ProjectUser, ProjectUser.project_id == Project.id)
        .outerjoin(
            Protocol,
            and_(
                Protocol.project_id == Project.id,
                Protocol.deleted_at.is_(None),
            ),
        )
        .group_by(
            Project.id,
            Lab.name,
            Lab.uid,
            ParentProject.uid,
            ParentProject.name,
            child_counts_subquery.c.children_count,
        )
    )

    # Apply all conditions
    query = query.where(*conditions)

    # Get total count
    count_query = select(func.count()).select_from(
        select(Project).join(Lab).where(*conditions).group_by(Project.id).subquery()
    )
    total_count = await db_session.scalar(count_query)

    # Add pagination and ordering
    query = (
        query.order_by(
            case((Project.parent_project_id.is_(None), 0), else_=1),
            func.coalesce(Project.parent_project_id, Project.id),
            Project.id.asc(),
        )
        .limit(page_size)
        .offset((page - 1) * page_size)
    )

    result = await db_session.execute(query)
    projects = [
        d.Project.as_dict(
            lab_name=d.lab_name,
            lab_uid=d.lab_uid,
            parent_project_uid=d.parent_project_uid,
            parent_project_name=d.parent_project_name,
            children_count=d.children_count,
            has_children=d.children_count > 0,
            depth=1 if d.Project.parent_project_id else 0,
            users_count=d.users_count,
            protocols_count=d.protocols_count,
        )
        for d in result
    ]

    return {"projects": projects, "total_count": total_count}


async def project_response(
    project: Project | None,
    lab: Lab,
    current_user: CurrentUser | None,
    db_session: DBSession,
):
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    user_role = None
    user_lab_role = None
    if current_user is not None:
        user_role = await check_user_permission(
            db_session,
            project=project,
            user=current_user,
            action="read_project",
        )
    elif project.type != ProjectType.PUBLIC:
        raise HTTPException(status_code=404, detail="Project not found")

    users_count = await ProjectUser.count(
        db_session, [ProjectUser.project_id == project.id]
    )
    _stmt = (
        select(func.count())
        .select_from(GroupUser)
        .join(GroupProject, GroupUser.group_id == GroupProject.group_id)
        .where(GroupProject.project_id == project.id)
    )
    group_users_count = await db_session.scalar(_stmt)
    users_count += group_users_count
    protocols_count = await Protocol.count(
        db_session,
        [Protocol.project_id == project.id, Protocol.deleted_at.is_(None)],
    )
    children_count = await Project.count(
        db_session,
        [Project.parent_project_id == project.id, Project.deleted_at.is_(None)],
    )
    parent_project = None
    if project.parent_project_id is not None:
        parent_project = await Project.find_by(
            db_session,
            [Project.id == project.parent_project_id, Project.deleted_at.is_(None)],
        )

    if current_user is not None:
        lab_user = await LabUser.find_by(
            db_session, [LabUser.lab_id == lab.id, LabUser.user_id == current_user.id]
        )
        user_lab_role = lab_user.role if lab_user else None

    return project.as_dict(
        lab_name=lab.name,
        lab_uid=lab.uid,
        user_role=user_role,
        user_lab_role=user_lab_role,
        users_count=users_count,
        protocols_count=protocols_count,
        **get_project_hierarchy_kwargs(
            project,
            parent_project=parent_project,
            children_count=children_count,
        ),
    )


@router.get("/by_uid")
async def get_project_by_uid(
    lab_uid: UidStr,
    project_uid: UidStr,
    current_user: OptionalCurrentUser,
    db_session: DBSession,
):
    # Find the lab first
    lab = await Lab.find_by(db_session, [Lab.uid == lab_uid])
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")

    project = await Project.find_by(
        db_session,
        [
            Project.uid == project_uid,
            Project.lab_id == lab.id,
            Project.deleted_at.is_(None),
        ],
    )
    return await project_response(project, lab, current_user, db_session)


@router.get("/{project_id}")
async def get_project(
    project_id: UUID,
    current_user: OptionalCurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    lab = await Lab.find(db_session, project.lab_id)
    return await project_response(project, lab, current_user, db_session)
class ProjectCreateParams(BaseModel):
    lab_id: UUID
    parent_project_id: UUID | None = None
    name: Annotated[
        str, StringConstraints(max_length=64, min_length=3, strip_whitespace=True)
    ]
    uid: UidStr
    type: ProjectType
    public_access_role: (
        Literal[ProjectRole.RECORDER, ProjectRole.EXPLORER, ProjectRole.VIEWER] | None
    ) = ProjectRole.EXPLORER
    permission_type: Literal[PermissionType.INHERIT, PermissionType.PROTOCOL_LEVEL] = (
        PermissionType.INHERIT
    )
    description: Annotated[
        str, StringConstraints(max_length=128, strip_whitespace=True)
    ] = ""
    copy_members: bool = True


@router.post("")
async def create_project(
    params: ProjectCreateParams, current_user: CurrentUser, db_session: DBSession
):
    lab = await Lab.find(db_session, id=params.lab_id)
    if config.is_single_lab and lab.uid != config.SINGLE_LAB_UID:
        raise HTTPException(status_code=404, detail="Lab not found")
    if config.is_single_lab and params.type != ProjectType.PRIVATE:
        raise HTTPException(
            status_code=400,
            detail="Public Projects are disabled in single-Lab mode",
        )
    user_in_lab = await LabUser.exists(
        db_session, [LabUser.user_id == current_user.id, LabUser.lab_id == lab.id]
    )
    if not user_in_lab:
        raise HTTPException(status_code=403, detail="Permission denied")

    proj = await Project.find_by(
        db_session,
        [
            Project.uid == params.uid,
            Project.lab_id == params.lab_id,
            Project.deleted_at.is_(None),
        ],
    )
    if proj:
        raise HTTPException(status_code=400, detail="Project name already exists")

    parent_project = await get_parent_project_for_create(params, current_user, db_session)
    if (
        config.is_single_lab
        and parent_project is not None
        and parent_project.type != ProjectType.PRIVATE
    ):
        raise HTTPException(
            status_code=400,
            detail="Public Projects are disabled in single-Lab mode",
        )

    project_payload = params.model_dump(
        exclude_none=True,
        exclude={"copy_members"},
    )
    if parent_project is not None:
        project_payload["type"] = parent_project.type
        project_payload["public_access_role"] = parent_project.public_access_role
        project_payload["permission_type"] = parent_project.permission_type

    project = Project(create_user_id=current_user.id, **project_payload)
    db_session.add(project)
    await db_session.flush()
    project_user = ProjectUser(
        project_id=project.id,
        user_id=current_user.id,
        create_user_id=current_user.id,
        role=ProjectRole.OWNER,
    )
    db_session.add(project_user)

    if parent_project is not None and params.copy_members:
        parent_project_users = (
            await db_session.execute(
                select(ProjectUser).where(ProjectUser.project_id == parent_project.id)
            )
        ).scalars()
        for parent_project_user in parent_project_users:
            if parent_project_user.user_id == current_user.id:
                continue
            db_session.add(
                ProjectUser(
                    project_id=project.id,
                    user_id=parent_project_user.user_id,
                    create_user_id=current_user.id,
                    role=parent_project_user.role,
                )
            )

        parent_group_projects = (
            await db_session.execute(
                select(GroupProject).where(GroupProject.project_id == parent_project.id)
            )
        ).scalars()
        for parent_group_project in parent_group_projects:
            db_session.add(
                GroupProject(
                    group_id=parent_group_project.group_id,
                    project_id=project.id,
                    create_user_id=current_user.id,
                    role=parent_group_project.role,
                )
            )

    lab.projects_count = await Project.count(
        db_session,
        where_conditions=[Project.lab_id == lab.id, Project.deleted_at.is_(None)],
    )
    await db_session.commit()

    return await project_response(project, lab, current_user, db_session)


class ProjectUpdateParams(BaseModel):
    name: Annotated[
        str | None,
        StringConstraints(min_length=3, max_length=64, strip_whitespace=True),
    ] = None
    type: ProjectType | None = None
    public_access_role: (
        Literal[ProjectRole.RECORDER, ProjectRole.EXPLORER, ProjectRole.VIEWER] | None
    ) = None
    permission_type: Literal[PermissionType.INHERIT, PermissionType.PROTOCOL_LEVEL] = (
        PermissionType.INHERIT
    )
    description: Annotated[
        str | None, StringConstraints(max_length=128, strip_whitespace=True)
    ] = None


@router.put("/{project_id}")
async def update_project(
    project_id: UUID,
    params: ProjectUpdateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project: Project = await Project.find(db_session, id=project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="update_project",
    )

    if (
        config.is_single_lab
        and params.type is not None
        and params.type != ProjectType.PRIVATE
    ):
        raise HTTPException(
            status_code=400,
            detail="Public Projects are disabled in single-Lab mode",
        )

    if (
        is_protected_default_project(project.uid)
        and params.type is not None
        and params.type != project.type
    ):
        raise HTTPException(
            status_code=400, detail="Default projects cannot change visibility"
        )

    project.set_attrs(**params.model_dump(exclude_none=True))
    await db_session.commit()
    return project


@router.delete("/{project_id}")
async def delete_project(
    project_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    project: Project = await Project.find(db_session, id=project_id)
    lab = await Lab.find(db_session, project.lab_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="delete_project",
    )

    if is_protected_default_project(project.uid):
        raise HTTPException(
            status_code=400, detail="Default projects cannot be deleted"
        )

    active_subprojects_count = await Project.count(
        db_session,
        [Project.parent_project_id == project_id, Project.deleted_at.is_(None)],
    )
    if active_subprojects_count > 0:
        raise HTTPException(status_code=400, detail="Project has active subprojects")

    active_protocols_count = await Protocol.count(
        db_session,
        [
            Protocol.project_id == project_id,
            Protocol.deleted_at.is_(None),
        ],
    )
    if active_protocols_count > 0:
        raise HTTPException(status_code=400, detail="Project has active protocols")

    protocols_count = await Protocol.count(
        db_session,
        [Protocol.project_id == project.id],
    )
    if protocols_count == 0:
        stmt1 = delete(ProjectUser).where(ProjectUser.project_id == project_id)
        stmt2 = delete(GroupProject).where(GroupProject.project_id == project_id)
        await db_session.delete(project)
        await db_session.execute(stmt1)
        await db_session.execute(stmt2)
        await db_session.flush()
    else:
        project.status = ProjectStatus.DELETED
        project.deleted_at = datetime.now()
        await db_session.flush()

    lab.projects_count = await Project.count(
        db_session,
        [Project.lab_id == project.lab_id, Project.deleted_at.is_(None)],
    )
    await db_session.commit()
    return {"message": "success"}


class ProjectAddUserParams(BaseModel):
    user_id: UUID
    role: ProjectRole


@router.post("/{project_id}/users")
async def add_user_to_project(
    project_id: UUID,
    params: ProjectAddUserParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project: Project = await Project.find(db_session, id=project_id)
    action = (
        "set_role_manager" if params.role <= ProjectRole.MANAGER else "set_role_other"
    )
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action=action,
    )

    user = await User.find(db_session, id=params.user_id)
    exists = await ProjectUser.exists(
        db_session,
        [ProjectUser.project_id == project.id, ProjectUser.user_id == user.id],
    )
    if exists:
        raise HTTPException(status_code=400, detail="User already in project")

    project_user = ProjectUser(
        project_id=project.id,
        user_id=user.id,
        role=params.role,
        create_user_id=current_user.id,
    )
    db_session.add(project_user)
    await db_session.commit()

    return {"message": "success"}


@router.put("/{project_id}/users/{user_id}")
async def change_user_role_in_project(
    project_id: UUID,
    user_id: UUID,
    params: ProjectAddUserParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=project_id)
    action = (
        "set_role_manager" if params.role <= ProjectRole.MANAGER else "set_role_other"
    )
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action=action,
    )

    project_user = await ProjectUser.find_by(
        db_session,
        [ProjectUser.project_id == project_id, ProjectUser.user_id == user_id],
    )
    if project_user is None:
        raise HTTPException(status_code=404, detail="User not found in project")

    project_user.role = params.role
    await db_session.commit()
    return {"message": "success"}


@router.delete("/{project_id}/users/{user_id}")
async def delete_user_from_project(
    project_id: UUID,
    user_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project: Project = await Project.find(db_session, id=project_id)
    if user_id == current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    project_user = await ProjectUser.find_by(
        db_session,
        [ProjectUser.project_id == project.id, ProjectUser.user_id == user_id],
    )
    if project_user is None:
        return {"message": "success"}

    action = (
        "set_role_manager"
        if project_user.role <= ProjectRole.MANAGER
        else "set_role_other"
    )
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action=action,
    )

    await db_session.delete(project_user)
    await db_session.commit()
    return {"message": "success"}


@router.get("/{project_id}/users")
async def get_project_users(
    project_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 10,
):
    project = await Project.find(db_session, id=project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_project",
    )

    count_stmt = select(func.count()).where(ProjectUser.project_id == project_id)
    total_count = (await db_session.execute(count_stmt)).scalar()

    stmt = (
        select(
            User,
            ProjectUser.role.label("project_role"),
            UserAlias.alias.label("user_alias"),
            LabUser.alias.label("lab_alias"),
        )
        .options(selectinload(User.avatar_attachment))
        .join(ProjectUser)
        .outerjoin(
            UserAlias,
            and_(
                UserAlias.target_user_id == User.id,
                UserAlias.user_id == current_user.id,
            ),
        )
        .outerjoin(
            LabUser,
            and_(
                LabUser.user_id == User.id,
                LabUser.lab_id == project.lab_id,
            ),
        )
        .where(ProjectUser.project_id == project_id)
        .order_by(ProjectUser.role.asc(), ProjectUser.created_at.asc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    result = (await db_session.execute(stmt)).all()
    users = []
    for d in result:
        await d.User.load_avatar_attachment()
        user = d.User.as_dict(
            project_role=d.project_role,
            user_alias=d.user_alias,
            lab_alias=d.lab_alias,
        )
        users.append(user)
    return {"users": users, "total_count": total_count}


@router.get("/{project_id}/all_users")
async def get_project_all_users(
    project_id: UUID,
    db_session: DBSession,
    page: int = 1,
    page_size: int = 10,
):
    q1 = (
        select(
            User,
            GroupProject.role.label("project_role"),
            Group.id.label("group_id"),
            Group.name.label("group_name"),
            Group.uid.label("group_uid"),
        )
        .options(selectinload(User.avatar_attachment))
        .join(GroupUser, GroupUser.user_id == User.id)
        .join(GroupProject, GroupProject.group_id == GroupUser.group_id)
        .join(Group, GroupProject.group_id == Group.id)
        .where(GroupProject.project_id == project_id)
        .order_by(GroupProject.role.asc())
    )
    r1 = (await db_session.execute(q1)).all()
    group_users = []
    for d in r1:
        await d.User.load_avatar_attachment()
        group_users.append(
            d.User.as_dict(
                project_role=d.project_role,
                group_id=d.group_id,
                group_name=d.group_name,
                group_uid=d.group_uid,
            )
        )

    q2 = (
        select(User, ProjectUser.role.label("project_role"))
        .options(selectinload(User.avatar_attachment))
        .join(ProjectUser)
        .where(ProjectUser.project_id == project_id)
        .order_by(ProjectUser.role.asc())
    )
    r2 = (await db_session.execute(q2)).all()
    project_users = []
    for d in r2:
        await d.User.load_avatar_attachment()
        project_users.append(d.User.as_dict(project_role=d.project_role))
    users = (
        py_(project_users + group_users)
        .sort_by(lambda i: i["project_role"])
        .uniq_by(lambda i: i["id"])
        .value()
    )

    start = (page - 1) * page_size
    end = start + page_size
    return {
        "users": users[start:end],
        "total_count": len(users),
    }


async def check_project_uid(
    db_session: DBSession,
    lab_id: UUID,
    uid: UidStr,
    project_id: UUID | None = None,
):
    conditions = [
        Project.uid == uid,
        Project.lab_id == lab_id,
        Project.deleted_at.is_(None),
    ]
    if project_id is not None:
        conditions.append(Project.id != project_id)

    exists = await Project.exists(db_session, conditions)
    if exists:
        raise HTTPException(
            status_code=400, detail="Project UID already exists in this lab"
        )
