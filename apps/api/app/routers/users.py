import os
from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.params import Body
from pydantic import BaseModel, PositiveInt, StringConstraints, model_validator
from sqlalchemy import (
    String,
    and_,
    case,
    cast,
    distinct,
    func,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy.orm import aliased, selectinload

from app.config import config
from app.database import DBSession
from app.models.attachment import Attachment
from app.models.group import Group, GroupProject, GroupUser
from app.models.lab import Lab, LabUser
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
from app.routers.depends import CurrentUser, create_access_token, get_current_user
from app.routers.permission import get_user_project_role, get_user_protocol_role
from app.routers.utils import UidStr, check_sms_verify_code, send_sms_verify_code
from app.services.account_security import bump_auth_version

router = APIRouter(
    prefix="/users", tags=["users"], dependencies=[Depends(get_current_user)]
)


class UserQueryParams(BaseModel):
    username: (
        Annotated[
            str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True)
        ]
        | None
    ) = None
    email: (
        Annotated[
            str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True)
        ]
        | None
    ) = None
    name_or_email: (
        Annotated[
            str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True)
        ]
        | None
    ) = None


@router.get("")
async def get_users(
    db_session: DBSession,
    page: PositiveInt = Query(1),
    page_size: PositiveInt = Query(10),
    params=Depends(UserQueryParams),
):
    where_conditions = User.conditions_from_dict(params.model_dump(exclude_none=True))
    if params.name_or_email:
        match_str = f"{params.name_or_email}%"
        where_conditions.append(
            or_(
                User.username.like(match_str),
                User.email.like(match_str),
            )
        )

    total_count = await User.count(db_session, where_conditions)

    users = await User.all(
        db_session,
        where_conditions,
        page,
        page_size,
        options=selectinload(User.avatar_attachment),
    )
    [await user.load_avatar_attachment() for user in users]
    users = [
        user.as_dict(only=["id", "username", "name", "avatar_url"]) for user in users
    ]
    return {"data": users, "total_count": total_count}


class UserLabQueryParams(BaseModel):
    name: (
        Annotated[
            str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True)
        ]
        | None
    ) = None
    uid: (
        Annotated[
            str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True)
        ]
        | None
    ) = None


SortByOption = Literal["updated_at", "created_at", "name", "uid"]


def _resolve_sort_clause(model, sorted_by: SortByOption | None):
    if sorted_by == "updated_at":
        return model.updated_at.desc()
    if sorted_by == "created_at":
        return model.created_at.desc()
    if sorted_by == "name":
        return model.name.asc()
    if sorted_by == "uid":
        return model.uid.asc()
    return None


@router.get("/{user_id}/labs")
async def get_user_labs(
    user_id: UUID,
    db_session: DBSession,
    page: PositiveInt = Query(1),
    page_size: PositiveInt = Query(10),
    sorted_by: SortByOption | None = Query(None),
    params=Depends(UserLabQueryParams),
):
    # Base condition for user_id
    where_conditions = [LabUser.user_id == user_id]

    # Add lab-specific conditions
    lab_conditions = Lab.conditions_from_dict(params.model_dump(exclude_none=True))
    where_conditions.extend(lab_conditions)
    if config.is_single_lab:
        where_conditions.append(Lab.uid == config.SINGLE_LAB_UID)

    # Use count_with_join for proper join handling
    total_count = await Lab.count_with_join(db_session, LabUser, where_conditions)

    # Get paginated results
    query = (
        select(Lab, LabUser.role.label("user_role"))
        .options(selectinload(Lab.logo_attachment))
        .join(LabUser)
        .where(*where_conditions)
    )
    sort_clause = _resolve_sort_clause(Lab, sorted_by)
    if sort_clause is not None:
        query = query.order_by(sort_clause)

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = (await db_session.execute(query)).all()

    labs = []
    for d in result:
        await d.Lab.load_logo_attachment(db_session)
        lab = d.Lab.as_dict(user_role=d.user_role)
        labs.append(lab)

    return {"labs": labs, "total_count": total_count}


class UserGroupQueryParams(BaseModel):
    name: (
        Annotated[
            str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True)
        ]
        | None
    ) = None


@router.get("/{user_id}/groups")
async def get_user_groups(
    user_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    page: PositiveInt = Query(1),
    page_size: PositiveInt = Query(10),
    params=Depends(UserGroupQueryParams),
):
    where_conditions = [GroupUser.user_id == user_id]
    group_conditions = Group.conditions_from_dict(params.model_dump(exclude_none=True))
    where_conditions.extend(group_conditions)

    # Use count_with_join for proper join handling
    total_count = await Group.count_with_join(db_session, GroupUser, where_conditions)

    gu1 = aliased(GroupUser, name="gu1")
    gu2 = aliased(GroupUser, name="gu2")
    query = (
        select(Group)
        .select_from(gu1)
        .join(gu2, gu2.group_id == gu1.group_id)
        .join(Group, Group.id == gu1.group_id)
        .where(
            and_(
                gu1.user_id == user_id,
                gu2.user_id == current_user.id,
            )
        )
        .where(*where_conditions)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    groups = (await db_session.execute(query)).all()

    return {"groups": [g.Group.as_dict() for g in groups], "total_count": total_count}


class UserProjectQueryParams(BaseModel):
    name: (
        Annotated[
            str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True)
        ]
        | None
    ) = None
    lab_uid: UidStr | None = None


class UserRecordQueryParams(BaseModel):
    lab_uid: UidStr | None = None
    project_uid: UidStr | None = None
    submitter: Literal["all", "me"] = "all"
    date_from: date | None = None
    date_to: date | None = None


def _get_user_own_project_ids(
    user_id: UUID,
):
    """获取用户自己的所有项目（不需要权限检查）"""

    # 直接参与的项目
    projects_with_direct_role = (
        select(Project.id)
        .select_from(Project)
        .join(ProjectUser, ProjectUser.project_id == Project.id)
        .where(
            ProjectUser.user_id == user_id,
            Project.deleted_at.is_(None),
        )
    )

    # 通过组间接参与的项目（排除已有直接角色的项目）
    projects_with_group_role = (
        select(Project.id)
        .select_from(Project)
        .join(GroupProject, GroupProject.project_id == Project.id)
        .join(GroupUser, GroupUser.group_id == GroupProject.group_id)
        .where(
            GroupUser.user_id == user_id,
            # 排除已经通过直接参与获得的project_id
            Project.id.notin_(
                select(ProjectUser.project_id).where(ProjectUser.user_id == user_id)
            ),
            Project.deleted_at.is_(None),
        )
    )

    # 合并两个查询
    user_projects_query = union_all(
        projects_with_direct_role, projects_with_group_role
    ).cte("user_project_ids")

    return select(user_projects_query.c.id)


def _get_user_accessible_project_ids(
    user_id: UUID,
    current_user: CurrentUser,
):
    def get_user_project_ids(target_user_id: UUID):
        """获取指定用户的所有协议所属的项目ID"""
        # 通过直接参与项目获得的协议的项目ID
        direct_project_ids = (
            select(Project.id, Project.type)
            .join(ProjectUser, ProjectUser.project_id == Project.id)
            .where(
                and_(
                    ProjectUser.user_id == target_user_id,
                    Project.deleted_at.is_(None),
                )
            )
        )

        # 通过组间接参与项目获得的协议的项目ID
        indirect_project_ids = (
            select(Project.id, Project.type)
            .join(GroupProject, GroupProject.project_id == Project.id)
            .join(GroupUser, GroupUser.group_id == GroupProject.group_id)
            .where(
                # 排除已经通过直接参与获得的project_id
                Project.id.notin_(
                    select(ProjectUser.project_id).where(
                        ProjectUser.user_id == target_user_id
                    )
                ),
                GroupUser.user_id == target_user_id,
                Project.deleted_at.is_(None),
            )
        )

        return union_all(direct_project_ids, indirect_project_ids)

    # 获取当前用户可访问的项目
    current_user_accessible_projects = get_user_project_ids(current_user.id).cte(
        "current_user_accessible_projects"
    )

    # 获取指定用户的协议所属项目
    target_user_projects = get_user_project_ids(user_id).cte("target_user_projects")

    # 计算交集：指定用户的协议项目 ∩ 当前用户可访问的项目
    return select(target_user_projects.c.id).where(
        or_(
            target_user_projects.c.type == ProjectType.PUBLIC,
            target_user_projects.c.id.in_(
                select(current_user_accessible_projects.c.id)
            ),
        )
    )


@router.get("/{user_id}/projects")
async def get_user_projects(
    user_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    page: PositiveInt = Query(1),
    page_size: PositiveInt = Query(10),
    sorted_by: SortByOption | None = Query(None),
    params=Depends(UserProjectQueryParams),
):
    """
    获取指定用户的项目列表

    - 如果指定用户就是当前用户，返回所有项目（不需要权限检查）
    - 如果指定用户不是当前用户，只返回当前用户有权限访问的项目
    """

    project_filter_conditions = Project.conditions_from_dict(
        params.model_dump(exclude_none=True, exclude={"lab_uid"})
    )
    project_filter_conditions.append(Project.deleted_at.is_(None))
    if params.lab_uid:
        project_filter_conditions.append(
            Project.lab_id.in_(select(Lab.id).where(Lab.uid == params.lab_uid))
        )

    if user_id == current_user.id:
        # 当前用户查看自己的项目，返回所有项目
        user_projects_query = _get_user_own_project_ids(user_id)
    else:
        # 当前用户查看其他用户的项目，需要权限过滤
        user_projects_query = _get_user_accessible_project_ids(user_id, current_user)

    project_filter_conditions.append(Project.id.in_(user_projects_query))
    # 计算总数
    count_query = select(func.count()).select_from(
        select(Project).where(*project_filter_conditions)
    )
    total_count = await db_session.scalar(count_query)

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

    query = (
        select(
            Project,
            ProjectUser.role.label("project_role"),
            GroupProject.role.label("group_role"),
            Lab.uid.label("lab_uid"),
            Lab.name.label("lab_name"),
            ParentProject.uid.label("parent_project_uid"),
            ParentProject.name.label("parent_project_name"),
            func.coalesce(child_counts_subquery.c.children_count, 0).label(
                "children_count"
            ),
        )
        .select_from(Project)
        .outerjoin(
            ProjectUser,
            and_(
                ProjectUser.project_id == Project.id,
                ProjectUser.user_id == user_id,
            ),
        )
        .outerjoin(GroupProject, GroupProject.project_id == Project.id)
        .outerjoin(
            GroupUser,
            and_(
                GroupUser.group_id == GroupProject.group_id,
                GroupUser.user_id == user_id,
            ),
        )
        .outerjoin(Lab, Lab.id == Project.lab_id)
        .outerjoin(ParentProject, ParentProject.id == Project.parent_project_id)
        .outerjoin(child_counts_subquery, child_counts_subquery.c.parent_id == Project.id)
        .where(*project_filter_conditions)
    )
    sort_clause = _resolve_sort_clause(Project, sorted_by)
    if sort_clause is None:
        query = query.order_by(
            case((Project.parent_project_id.is_(None), 0), else_=1),
            func.coalesce(Project.parent_project_id, Project.id),
            Project.id.asc(),
        )
    else:
        query = query.order_by(sort_clause)
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db_session.execute(query)

    # 构建返回结果
    projects = []
    for row in result:
        projects.append(
            row.Project.as_dict(
                lab_uid=row.lab_uid,
                lab_name=row.lab_name,
                user_role=row.project_role or row.group_role,
                parent_project_uid=row.parent_project_uid,
                parent_project_name=row.parent_project_name,
                children_count=row.children_count,
                has_children=row.children_count > 0,
                depth=1 if row.Project.parent_project_id else 0,
            )
    )

    return {"projects": projects, "total_count": total_count}


@router.get("/records")
async def get_current_user_records(
    current_user: CurrentUser,
    db_session: DBSession,
    params=Depends(UserRecordQueryParams),
    page: PositiveInt = Query(1),
    page_size: PositiveInt = Query(10),
):
    return await get_visible_user_record_history(
        target_user_id=current_user.id,
        current_user=current_user,
        db_session=db_session,
        params=params,
        page=page,
        page_size=page_size,
    )


@router.get("/record_diary")
async def get_accessible_record_diary(
    current_user: CurrentUser,
    db_session: DBSession,
    params=Depends(UserRecordQueryParams),
    page: PositiveInt = Query(1),
    page_size: PositiveInt = Query(10),
):
    return await get_visible_user_record_history(
        target_user_id=current_user.id if params.submitter == "me" else None,
        current_user=current_user,
        db_session=db_session,
        params=params,
        page=page,
        page_size=page_size,
    )


@router.get("/record_diary/summary")
async def get_accessible_record_diary_summary(
    current_user: CurrentUser,
    db_session: DBSession,
    params=Depends(UserRecordQueryParams),
):
    return await get_visible_user_record_summary(
        target_user_id=current_user.id if params.submitter == "me" else None,
        current_user=current_user,
        db_session=db_session,
        params=params,
    )


@router.get("/record_diary/events")
async def get_accessible_record_diary_events(
    current_user: CurrentUser,
    db_session: DBSession,
    params=Depends(UserRecordQueryParams),
    limit: int = Query(500, ge=1, le=1000),
):
    return await get_visible_user_record_events(
        target_user_id=current_user.id if params.submitter == "me" else None,
        current_user=current_user,
        db_session=db_session,
        params=params,
        limit=limit,
    )


@router.get("/{user_id}/records")
async def get_user_records(
    user_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    params=Depends(UserRecordQueryParams),
    page: PositiveInt = Query(1),
    page_size: PositiveInt = Query(10),
):
    return await get_visible_user_record_history(
        target_user_id=user_id,
        current_user=current_user,
        db_session=db_session,
        params=params,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}/records/summary")
async def get_user_record_summary(
    user_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    params=Depends(UserRecordQueryParams),
):
    return await get_visible_user_record_summary(
        target_user_id=user_id,
        current_user=current_user,
        db_session=db_session,
        params=params,
    )


@router.get("/{user_id}/records/events")
async def get_user_record_events(
    user_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    params=Depends(UserRecordQueryParams),
    limit: int = Query(500, ge=1, le=1000),
):
    return await get_visible_user_record_events(
        target_user_id=user_id,
        current_user=current_user,
        db_session=db_session,
        params=params,
        limit=limit,
    )


def serialize_user_record_history_item(
    record: Record,
    protocol: Protocol,
    project: Project,
    lab: Lab,
    submit_user: User,
    init_record: Record,
):
    protocol.lab_uid = lab.uid
    protocol.project_uid = project.uid
    protocol.version = record.protocol_version

    submit_user_payload = submit_user.as_dict(
        only=["id", "username", "name", "avatar", "avatar_url"]
    )

    return {
        "airalogy_record_id": record.airalogy_id,
        "record_id": record.id,
        "record_version": record.version,
        "metadata": {
            "airalogy_protocol_id": protocol.airalogy_id,
            "protocol_id": protocol.uid,
            "protocol_uuid": record.protocol_id,
            "protocol_version": record.protocol_version,
            "record_current_version_submission_time": record.created_at,
            "record_current_version_submission_user_id": str(submit_user.id),
            "record_current_version_submission_username": submit_user.username,
            "record_initial_version_submission_time": init_record.created_at,
            "record_initial_version_submission_user_id": str(submit_user.id),
            "record_initial_version_submission_username": submit_user.username,
            "lab_id": lab.uid,
            "project_id": project.uid,
            "record_num": record.number,
            "sha1": record.hash,
        },
        "data": record.data,
        "user": submit_user_payload,
        "lab": {
            "id": lab.id,
            "uid": lab.uid,
            "name": lab.name,
        },
        "project": {
            "id": project.id,
            "uid": project.uid,
            "name": project.name,
        },
        "protocol": {
            "id": protocol.id,
            "uid": protocol.uid,
            "name": protocol.name,
        },
    }


def serialize_user_record_event_item(
    *,
    record_id: UUID,
    record_version: int,
    record_protocol_id: UUID,
    record_protocol_version: str,
    record_user_id: UUID,
    record_created_at: datetime,
    record_number: int,
    record_hash: str,
    protocol: Protocol,
    project: Project,
    lab: Lab,
    submit_user: User,
):
    airalogy_record_id = f"airalogy.id.record.{record_id}.v.{record_version}"
    airalogy_protocol_id = (
        f"airalogy.id.lab.{lab.uid}.project.{project.uid}."
        f"protocol.{protocol.uid}.v.{record_protocol_version}"
    )
    return {
        "airalogy_record_id": airalogy_record_id,
        "record_id": record_id,
        "record_version": record_version,
        "metadata": {
            "airalogy_protocol_id": airalogy_protocol_id,
            "protocol_id": protocol.uid,
            "protocol_uuid": record_protocol_id,
            "protocol_version": record_protocol_version,
            "record_current_version_submission_time": record_created_at,
            "record_current_version_submission_user_id": str(record_user_id),
            "record_current_version_submission_username": submit_user.username,
            "lab_id": lab.uid,
            "project_id": project.uid,
            "record_num": record_number,
            "sha1": record_hash,
        },
        "user": submit_user.as_dict(only=["id", "username", "name"]),
        "lab": {
            "id": lab.id,
            "uid": lab.uid,
            "name": lab.name,
        },
        "project": {
            "id": project.id,
            "uid": project.uid,
            "name": project.name,
        },
        "protocol": {
            "id": protocol.id,
            "uid": protocol.uid,
            "name": protocol.name,
        },
    }


def build_user_project_role_expr(user_id: UUID):
    direct_role_query = select(ProjectUser.role).where(
        ProjectUser.user_id == user_id,
        ProjectUser.project_id == Project.id,
    )
    group_role_query = (
        select(GroupProject.role)
        .select_from(GroupProject)
        .join(GroupUser, GroupProject.group_id == GroupUser.group_id)
        .where(
            GroupProject.project_id == Project.id,
            GroupUser.user_id == user_id,
        )
    )
    roles = union_all(direct_role_query, group_role_query).alias(
        "record_diary_project_roles"
    )
    return select(func.min(roles.c.role)).scalar_subquery()


def build_user_protocol_role_expr(user_id: UUID):
    direct_role_query = select(ProtocolUser.role).where(
        ProtocolUser.user_id == user_id,
        ProtocolUser.protocol_id == Protocol.id,
    )
    group_role_query = (
        select(ProjectGroupProtocol.role)
        .select_from(ProjectGroupProtocol)
        .join(
            ProjectGroupUser,
            ProjectGroupProtocol.project_group_id
            == ProjectGroupUser.project_group_id,
        )
        .where(
            ProjectGroupProtocol.protocol_id == Protocol.id,
            ProjectGroupUser.user_id == user_id,
        )
    )
    roles = union_all(direct_role_query, group_role_query).alias(
        "record_diary_protocol_roles"
    )
    return select(func.min(roles.c.role)).scalar_subquery()


def build_record_readable_condition(user_id: UUID, record_alias):
    project_role = build_user_project_role_expr(user_id)
    protocol_role = build_user_protocol_role_expr(user_id)
    base_role = case(
        (project_role.is_(None), Project.public_access_role),
        else_=project_role,
    )
    owner_adjusted_role = case(
        (
            and_(
                Protocol.user_id == user_id,
                base_role > ProjectRole.PROTOCOL_OWNER.value,
            ),
            ProjectRole.PROTOCOL_OWNER.value,
        ),
        else_=base_role,
    )
    effective_role = case(
        (
            and_(
                Project.permission_type == PermissionType.PROTOCOL_LEVEL,
                owner_adjusted_role > ProjectRole.PROTOCOL_OWNER.value,
                protocol_role.is_not(None),
            ),
            protocol_role,
        ),
        else_=owner_adjusted_role,
    )
    private_protocol_level_without_protocol_role = and_(
        Project.type == ProjectType.PRIVATE,
        Project.permission_type == PermissionType.PROTOCOL_LEVEL,
        owner_adjusted_role > ProjectRole.PROTOCOL_OWNER.value,
        protocol_role.is_(None),
    )

    return or_(
        and_(
            Project.type == ProjectType.PRIVATE,
            project_role.is_not(None),
            ~private_protocol_level_without_protocol_role,
            effective_role.in_(
                [
                    ProjectRole.OWNER,
                    ProjectRole.MANAGER,
                    ProjectRole.PROTOCOL_OWNER,
                    ProjectRole.COLLABORATOR,
                    ProjectRole.RECORDER,
                ]
            ),
            or_(
                effective_role != ProjectRole.RECORDER,
                record_alias.user_id == user_id,
            ),
        ),
        and_(
            Project.type == ProjectType.PUBLIC,
            effective_role.in_(
                [
                    ProjectRole.OWNER,
                    ProjectRole.MANAGER,
                    ProjectRole.PROTOCOL_OWNER,
                    ProjectRole.COLLABORATOR,
                    ProjectRole.RECORDER,
                    ProjectRole.RECORDER_SELF_ONLY,
                    ProjectRole.EXPLORER,
                    ProjectRole.EXPLORER_SELF_ONLY,
                    ProjectRole.VIEWER,
                ]
            ),
            or_(
                effective_role.notin_(
                    [
                        ProjectRole.RECORDER_SELF_ONLY,
                        ProjectRole.EXPLORER_SELF_ONLY,
                        ProjectRole.VIEWER_SELF_ONLY,
                    ]
                ),
                record_alias.user_id == user_id,
            ),
        ),
    )


def build_user_record_history_conditions(
    target_user_id: UUID | None,
    params: UserRecordQueryParams,
):
    conditions = [
        Record.deleted_at.is_(None),
        Protocol.deleted_at.is_(None),
        Project.deleted_at.is_(None),
    ]
    if target_user_id is not None:
        conditions.append(Record.user_id == target_user_id)
    if params.lab_uid:
        conditions.append(Lab.uid == params.lab_uid)
    if params.project_uid:
        conditions.append(Project.uid == params.project_uid)

    return conditions


def build_user_record_history_date_conditions(
    record_alias,
    params: UserRecordQueryParams,
):
    conditions = []
    if params.date_from:
        conditions.append(
            record_alias.created_at
            >= datetime.combine(params.date_from, datetime.min.time())
        )
    if params.date_to:
        conditions.append(
            record_alias.created_at
            < datetime.combine(params.date_to + timedelta(days=1), datetime.min.time())
        )

    return conditions


def build_latest_user_record_subquery(
    target_user_id: UUID | None,
    params: UserRecordQueryParams,
):
    return (
        select(
            Record,
            func.row_number()
            .over(
                partition_by=Record.id,
                order_by=Record.version.desc(),
            )
            .label("row_number"),
        )
        .join(Protocol, Protocol.id == Record.protocol_id)
        .join(Project, Project.id == Protocol.project_id)
        .join(Lab, Lab.id == Project.lab_id)
        .where(*build_user_record_history_conditions(target_user_id, params))
        .subquery()
    )


def build_latest_user_record_metadata_subquery(
    target_user_id: UUID | None,
    params: UserRecordQueryParams,
):
    return (
        select(
            Record.id.label("id"),
            Record.version.label("version"),
            Record.protocol_id.label("protocol_id"),
            Record.protocol_version.label("protocol_version"),
            Record.user_id.label("user_id"),
            Record.created_at.label("created_at"),
            Record.number.label("number"),
            Record.hash.label("hash"),
            func.row_number()
            .over(
                partition_by=Record.id,
                order_by=Record.version.desc(),
            )
            .label("row_number"),
        )
        .join(Protocol, Protocol.id == Record.protocol_id)
        .join(Project, Project.id == Protocol.project_id)
        .join(Lab, Lab.id == Project.lab_id)
        .where(*build_user_record_history_conditions(target_user_id, params))
        .subquery()
    )


async def get_visible_user_record_history(
    *,
    target_user_id: UUID | None,
    current_user: CurrentUser,
    db_session: DBSession,
    params: UserRecordQueryParams,
    page: int,
    page_size: int,
):
    latest_records_subquery = build_latest_user_record_subquery(
        target_user_id,
        params,
    )
    LatestRecord = aliased(Record, latest_records_subquery)
    readable_condition = build_record_readable_condition(current_user.id, LatestRecord)
    date_conditions = build_user_record_history_date_conditions(LatestRecord, params)

    visible_record_ids_query = (
        select(LatestRecord.id)
        .join(Protocol, Protocol.id == LatestRecord.protocol_id)
        .join(Project, Project.id == Protocol.project_id)
        .join(Lab, Lab.id == Project.lab_id)
        .where(
            latest_records_subquery.c.row_number == 1,
            readable_condition,
            *date_conditions,
        )
    )
    total_count = await db_session.scalar(
        select(func.count()).select_from(visible_record_ids_query.subquery())
    )

    query = (
        select(
            LatestRecord,
            Protocol,
            Project,
            Lab,
            User,
        )
        .join(Protocol, Protocol.id == LatestRecord.protocol_id)
        .join(Project, Project.id == Protocol.project_id)
        .join(Lab, Lab.id == Project.lab_id)
        .join(User, User.id == LatestRecord.user_id)
        .options(selectinload(User.avatar_attachment))
        .where(
            latest_records_subquery.c.row_number == 1,
            readable_condition,
            *date_conditions,
        )
        .order_by(LatestRecord.created_at.desc(), LatestRecord.number.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = (await db_session.execute(query)).all()
    records = []
    for record, protocol, project, lab, submit_user in result:
        if record.version > 1:
            init_record = await Record.find_by(
                db_session,
                [
                    Record.id == record.id,
                    Record.version == 1,
                ],
            )
        else:
            init_record = record

        if submit_user.avatar:
            await submit_user.load_avatar_attachment()

        records.append(
            serialize_user_record_history_item(
                record=record,
                protocol=protocol,
                project=project,
                lab=lab,
                submit_user=submit_user,
                init_record=init_record or record,
            )
        )

    return {
        "records": records,
        "total_count": total_count,
    }


async def get_visible_user_record_summary(
    *,
    target_user_id: UUID | None,
    current_user: CurrentUser,
    db_session: DBSession,
    params: UserRecordQueryParams,
):
    latest_records_subquery = build_latest_user_record_metadata_subquery(
        target_user_id,
        params,
    )
    LatestRecord = latest_records_subquery.c
    readable_condition = build_record_readable_condition(current_user.id, LatestRecord)
    date_conditions = build_user_record_history_date_conditions(LatestRecord, params)
    day_expr = cast(func.date(LatestRecord.created_at), String)

    query = (
        select(
            day_expr.label("date"),
            func.count().label("count"),
        )
        .select_from(latest_records_subquery)
        .join(Protocol, Protocol.id == LatestRecord.protocol_id)
        .join(Project, Project.id == Protocol.project_id)
        .join(Lab, Lab.id == Project.lab_id)
        .where(
            latest_records_subquery.c.row_number == 1,
            readable_condition,
            *date_conditions,
        )
        .group_by(day_expr)
        .order_by(day_expr)
    )
    result = (await db_session.execute(query)).all()

    return {
        "summary": [
            {
                "date": row._mapping["date"],
                "count": row._mapping["count"],
            }
            for row in result
        ]
    }


async def get_visible_user_record_events(
    *,
    target_user_id: UUID | None,
    current_user: CurrentUser,
    db_session: DBSession,
    params: UserRecordQueryParams,
    limit: int,
):
    latest_records_subquery = build_latest_user_record_metadata_subquery(
        target_user_id,
        params,
    )
    LatestRecord = latest_records_subquery.c
    readable_condition = build_record_readable_condition(current_user.id, LatestRecord)
    date_conditions = build_user_record_history_date_conditions(LatestRecord, params)

    query = (
        select(
            LatestRecord.id,
            LatestRecord.version,
            LatestRecord.protocol_id,
            LatestRecord.protocol_version,
            LatestRecord.user_id,
            LatestRecord.created_at,
            LatestRecord.number,
            LatestRecord.hash,
            Protocol,
            Project,
            Lab,
            User,
        )
        .select_from(latest_records_subquery)
        .join(Protocol, Protocol.id == LatestRecord.protocol_id)
        .join(Project, Project.id == Protocol.project_id)
        .join(Lab, Lab.id == Project.lab_id)
        .join(User, User.id == LatestRecord.user_id)
        .where(
            latest_records_subquery.c.row_number == 1,
            readable_condition,
            *date_conditions,
        )
        .order_by(LatestRecord.created_at.asc(), LatestRecord.number.asc())
        .limit(limit + 1)
    )

    result = (await db_session.execute(query)).all()
    truncated = len(result) > limit
    events = []
    for (
        record_id,
        record_version,
        record_protocol_id,
        record_protocol_version,
        record_user_id,
        record_created_at,
        record_number,
        record_hash,
        protocol,
        project,
        lab,
        submit_user,
    ) in result[:limit]:
        events.append(
            serialize_user_record_event_item(
                record_id=record_id,
                record_version=record_version,
                record_protocol_id=record_protocol_id,
                record_protocol_version=record_protocol_version,
                record_user_id=record_user_id,
                record_created_at=record_created_at,
                record_number=record_number,
                record_hash=record_hash,
                protocol=protocol,
                project=project,
                lab=lab,
                submit_user=submit_user,
            )
        )

    return {
        "events": events,
        "truncated": truncated,
        "limit": limit,
    }


@router.get("/{user_id}/activities")
async def get_user_activities(
    user_id: UUID,
    db_session: DBSession,
    start_date: date | None = None,
    end_date: date | None = None,
    page: PositiveInt = Query(1),
    page_size: PositiveInt = Query(10),
):
    """Get user activities in the date range
    Activities include:
    1. Protocol records created
    2. Projects joined/created
    3. Groups joined/created
    4. Labs joined/created
    """
    # Handle date range
    if not start_date:
        start_date = datetime.now().date() - timedelta(days=30)
    if not end_date:
        end_date = datetime.now().date()

    if start_date > end_date:
        raise HTTPException(
            status_code=400, detail="Start date must be before end date"
        )

    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())

    # Common columns for all queries
    def get_base_columns():
        return [
            literal(None).label("protocol_id"),
            literal(None).label("protocol_version"),
            literal(None).label("record_number"),
            literal(None).label("record_version"),
        ]

    # Create a CTE for all activities
    activities_cte = union_all(
        # Protocol records with protocol info
        select(
            cast(Record.id, String).label("id"),
            Protocol.name,
            Record.created_at,
            Protocol.uid,
            Project.name.label("project_name"),
            Project.uid.label("project_uid"),
            Project.id.label("project_id"),
            Lab.name.label("lab_name"),
            Lab.uid.label("lab_uid"),
            Lab.id.label("lab_id"),
            literal("record").label("type"),
            literal("created").label("action"),
            literal(None).label("role"),
            Protocol.id.label("protocol_id"),
            Protocol.latest_version.label("protocol_version"),
            Record.number.label("record_number"),
            Record.version.label("record_version"),
        )
        .join(Protocol, Protocol.id == Record.protocol_id)
        .join(Project, Project.id == Protocol.project_id)
        .join(Lab, Lab.id == Project.lab_id)
        .where(
            and_(
                Record.user_id == user_id,
                Record.created_at.between(start_datetime, end_datetime),
            )
        ),
        # Projects
        select(
            cast(ProjectUser.project_id, String).label("id"),
            Project.name,
            ProjectUser.created_at,
            Project.uid,
            literal(None).label("project_name"),
            literal(None).label("project_uid"),
            literal(None).label("project_id"),
            Lab.name.label("lab_name"),
            Lab.uid.label("lab_uid"),
            Lab.id.label("lab_id"),
            literal("project").label("type"),
            case(
                (ProjectUser.create_user_id == user_id, literal("created")),
                else_=literal("joined"),
            ).label("action"),
            ProjectUser.role,
            *get_base_columns(),
        )
        .select_from(ProjectUser)
        .join(Project, Project.id == ProjectUser.project_id)
        .join(Lab, Lab.id == Project.lab_id)
        .where(
            and_(
                ProjectUser.user_id == user_id,
                ProjectUser.created_at.between(start_datetime, end_datetime),
            )
        ),
        # Groups
        select(
            cast(GroupUser.group_id, String).label("id"),
            Group.name,
            GroupUser.created_at,
            Group.uid,
            literal(None).label("project_name"),
            literal(None).label("project_uid"),
            literal(None).label("project_id"),
            Lab.name.label("lab_name"),
            Lab.uid.label("lab_uid"),
            Lab.id.label("lab_id"),
            literal("group").label("type"),
            case(
                (GroupUser.create_user_id == user_id, literal("created")),
                else_=literal("joined"),
            ).label("action"),
            literal(None).label("role"),
            *get_base_columns(),
        )
        .select_from(GroupUser)
        .join(Group, Group.id == GroupUser.group_id)
        .join(Lab, Lab.id == Group.lab_id)
        .where(
            and_(
                GroupUser.user_id == user_id,
                GroupUser.created_at.between(start_datetime, end_datetime),
            )
        ),
        # Labs
        select(
            cast(LabUser.lab_id, String).label("id"),
            Lab.name,
            LabUser.created_at,
            Lab.uid,
            literal(None).label("project_name"),
            literal(None).label("project_uid"),
            literal(None).label("project_id"),
            literal(None).label("lab_name"),
            literal(None).label("lab_uid"),
            literal(None).label("lab_id"),
            literal("lab").label("type"),
            case(
                (LabUser.create_user_id == user_id, literal("created")),
                else_=literal("joined"),
            ).label("action"),
            LabUser.role,
            *get_base_columns(),
        )
        .select_from(LabUser)
        .join(Lab, Lab.id == LabUser.lab_id)
        .where(
            and_(
                LabUser.user_id == user_id,
                LabUser.created_at.between(start_datetime, end_datetime),
            )
        ),
    ).cte("activities")

    # Query with pagination
    paginated_query = (
        select(activities_cte)
        .order_by(activities_cte.c.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    # Execute query
    result = await db_session.execute(paginated_query)

    # Group activities by type
    activities_by_type = {
        "records": [],
        "projects": [],
        "groups": [],
        "labs": [],
    }

    # Process results
    for row in result:
        activity = create_activity_dict(row, include_context=(row.type != "lab"))
        activities_by_type[f"{row.type}s"].append(activity)

    return activities_by_type


@router.post("/send_verify_code")
async def send_verify_code(
    type: Annotated[Literal["reset_password", "change_phone"], Body(embed=True)],
    current_user: CurrentUser,
):
    await send_sms_verify_code(current_user.full_phone_number, type)
    return {"success": True}


class UpdatePasswordParams(BaseModel):
    verify_code: Annotated[str, StringConstraints(min_length=6, max_length=6)]
    new_password: Annotated[str, StringConstraints(min_length=8, max_length=32)]
    comfirm_password: Annotated[str, StringConstraints(min_length=8, max_length=32)]

    @model_validator(mode="after")
    def check_passwords_match(self) -> "UpdatePasswordParams":
        if self.new_password != self.comfirm_password:
            raise ValueError("new_password and comfirm_password do not match")
        return self


class ChangePhoneParams(BaseModel):
    new_country_code: Annotated[
        str,
        StringConstraints(pattern=r"^\d{1,4}$", min_length=1, max_length=4),
    ]
    new_phone: Annotated[
        str,
        StringConstraints(pattern=r"^\d{7,11}$", min_length=7, max_length=11),
    ]
    current_phone_verify_code: Annotated[
        str, StringConstraints(min_length=6, max_length=6)
    ]
    new_phone_verify_code: Annotated[str, StringConstraints(min_length=6, max_length=6)]

    @property
    def new_full_phone_number(self) -> str:
        return f"{self.new_country_code}{self.new_phone}"


@router.put("/change_password")
async def user_change_password(
    params: UpdatePasswordParams, current_user: CurrentUser, db_session: DBSession
):
    await check_sms_verify_code(
        current_user.full_phone_number, params.verify_code, "reset_password"
    )
    current_user.password = params.new_password
    auth_version = await bump_auth_version(db_session, current_user.id)
    await db_session.commit()
    return {
        "message": "success",
        "token": create_access_token(current_user, auth_version),
    }


@router.put("/change_phone")
async def change_phone(
    params: ChangePhoneParams, current_user: CurrentUser, db_session: DBSession
):
    # 检查新手机号是否已被其他用户使用
    new_full_phone = params.new_full_phone_number
    existing_user = await User.find_by(
        db_session,
        [
            User.country_code == params.new_country_code,
            User.phone == params.new_phone,
        ],
    )
    if existing_user and existing_user.id != current_user.id:
        raise HTTPException(status_code=400, detail="Phone number already exists")

    # 验证当前手机号的验证码
    await check_sms_verify_code(
        current_user.full_phone_number, params.current_phone_verify_code, "change_phone"
    )

    # 验证新手机号的验证码
    await check_sms_verify_code(
        new_full_phone, params.new_phone_verify_code, "change_phone"
    )

    # 更新用户手机号
    current_user.country_code = params.new_country_code
    current_user.phone = params.new_phone
    await db_session.commit()

    return {"message": "success", "new_phone": new_full_phone}


@router.put("/update_profile")
async def update_user(
    db_session: DBSession,
    current_user: CurrentUser,
    name: Annotated[
        str | None,
        Body(
            embed=True,
            min_length=1,
            max_length=64,
            strip_whitespace=True,
        ),
    ] = None,
    email: Annotated[
        str | None,
        Body(
            embed=True,
            min_length=6,
            max_length=64,
            strip_whitespace=True,
            pattern=r"^[a-zA-Z0-9._]+@([\w-]+\.)+[\w-]{2,4}$",
        ),
    ] = None,
    bio: Annotated[
        str | None,
        Body(
            embed=True,
            min_length=1,
            max_length=500,
            strip_whitespace=True,
        ),
    ] = None,
    avatar_file: UploadFile | None = None,
):
    if email is not None and email != current_user.email:
        email_exists = await User.exists(db_session, [User.email == email])
        if email_exists:
            raise HTTPException(status_code=400, detail="Email already exists")

        current_user.email = email

    if avatar_file:
        att = Attachment(
            filename=avatar_file.filename,
            content_type=avatar_file.content_type,
            user_id=current_user.id,
        )
        db_session.add(att)
        await db_session.flush()
        await att.save_file(file=avatar_file.file, length=avatar_file.size)
        current_user.avatar = att.id

    if name:
        current_user.name = name

    if bio:
        current_user.bio = bio

    await current_user.load_avatar_attachment()
    await db_session.commit()

    return current_user


@router.get("/api_key")
async def get_api_key(
    current_user: CurrentUser,
):
    return {"api_key": current_user.api_key}


@router.put("/generate_api_key")
async def generate_api_key(
    current_user: CurrentUser,
    db_session: DBSession,
):
    current_user.api_key_iv = os.urandom(16).hex()
    await db_session.commit()
    return {"api_key": current_user.api_key}


class UserIdentifierParams(BaseModel):
    username: UidStr | None = None
    id: UUID | None = None

    @model_validator(mode="after")
    def check_identifier_provided(self) -> "UserIdentifierParams":
        if not any([self.username, self.id]):
            raise ValueError(
                "At least one identifier (username, or id) must be provided"
            )
        return self


@router.get("/query")
async def get_user_by_username(
    db_session: DBSession,
    params=Depends(UserIdentifierParams),
):
    """Get user by username or id"""
    where_conditions = User.conditions_from_dict(params.model_dump(exclude_none=True))

    user = await User.find_by(
        db_session, where_conditions, options=selectinload(User.avatar_attachment)
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await user.load_avatar_attachment()
    return user


def create_activity_dict(row, include_context=False):
    """Helper function to create activity dictionary from query result
    Args:
        row: Query result row
        include_context: Whether to include context information
    Returns:
        dict: Activity dictionary
    """
    activity = {
        "id": row.id,
        "name": row.name,
        "created_at": row.created_at,
        "uid": row.uid,
        "role": row.role,
        "action": row.action,
    }
    if include_context:
        if row.type == "record":
            activity.update(
                {
                    "project": {
                        "id": row.project_id,
                        "name": row.project_name,
                        "uid": row.project_uid,
                    },
                    "lab": {
                        "id": row.lab_id,
                        "name": row.lab_name,
                        "uid": row.lab_uid,
                    },
                    "record": {
                        "id": row.id,
                        "number": row.record_number,
                        "version": row.record_version,
                    },
                    "protocol": {
                        "id": row.protocol_id,
                        "name": row.name,
                        "uid": row.uid,
                    },
                }
            )
        else:
            activity.update(
                {
                    "lab": {
                        "id": row.lab_id,
                        "name": row.lab_name,
                        "uid": row.lab_uid,
                    }
                }
            )
    return activity


# Add this after the UserProjectQueryParams class
class UserProtocolQueryParams(BaseModel):
    name: (
        Annotated[
            str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True)
        ]
        | None
    ) = None


@router.get("/{user_id}/protocols")
async def get_user_protocols(
    user_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    page: PositiveInt = Query(1),
    page_size: PositiveInt = Query(10),
    sorted_by: SortByOption | None = Query(None),
    params=Depends(UserProtocolQueryParams),
):
    """
    获取指定用户的协议列表

    - 如果指定用户就是当前用户，返回所有协议（不需要权限检查）
    - 如果指定用户不是当前用户，只返回当前用户有权限访问的协议
    """
    where_conditions = [
        Protocol.deleted_at.is_(None),
    ]

    if params and params.name:
        where_conditions.append(Protocol.name.ilike(f"%{params.name}%"))

    if user_id == current_user.id:
        # 当前用户查看自己的协议，返回所有协议
        user_projects_query = _get_user_own_project_ids(user_id)
    else:
        # 当前用户查看其他用户的协议，需要权限过滤
        user_projects_query = _get_user_accessible_project_ids(user_id, current_user)

    # 计算总数
    count_query = (
        select(func.count())
        .select_from(Protocol)
        .where(
            and_(
                Protocol.project_id.in_(user_projects_query),
                *where_conditions,
            )
        )
    )
    total_count: int = await db_session.scalar(count_query)

    # Build the main query
    query = (
        select(
            Protocol,
            Project.name.label("project_name"),
            Project.uid.label("project_uid"),
            Project.permission_type.label("permission_type"),
            Lab.name.label("lab_name"),
            Lab.uid.label("lab_uid"),
            func.count(distinct(Record.id)).label("records_count"),
        )
        .outerjoin(Project, Project.id == Protocol.project_id)
        .outerjoin(Lab, Lab.id == Project.lab_id)
        .outerjoin(Record, Record.protocol_id == Protocol.id)
        .where(
            and_(
                Protocol.project_id.in_(user_projects_query),
                *where_conditions,
            )
        )
        .group_by(
            Protocol.id,
            Project.name,
            Project.uid,
            Project.permission_type,
            Lab.name,
            Lab.uid,
        )
    )
    sort_clause = _resolve_sort_clause(Protocol, sorted_by)
    if sort_clause is None:
        sort_clause = Protocol.id.desc()
    query = query.order_by(sort_clause).offset((page - 1) * page_size).limit(page_size)

    result = await db_session.execute(query)

    # Filter protocols based on permission_type
    # For permission_type=2 projects, check if current_user has protocol-level access
    protocols = []
    for row in result:
        # Check if current user should see this protocol
        should_include = True

        if (
            row.permission_type == PermissionType.PROTOCOL_LEVEL
            and row.Protocol.user_id != current_user.id
        ):
            project_role = await get_user_project_role(
                db_session, current_user.id, row.Protocol.project_id
            )

            # Project owners and managers see all protocols
            if project_role is None or project_role > ProjectRole.MANAGER:
                # Check protocol-level access
                protocol_role = await get_user_protocol_role(
                    db_session, current_user.id, row.Protocol.id
                )

                should_include = protocol_role is not None

        if not should_include:
            total_count -= 1
            continue

        row.Protocol.lab_uid = row.lab_uid
        row.Protocol.project_uid = row.project_uid
        protocol_dict = row.Protocol.as_dict(
            lab={
                "name": row.lab_name,
                "uid": row.lab_uid,
            },
            project={
                "name": row.project_name,
                "uid": row.project_uid,
            },
            records_count=row.records_count,
        )
        protocols.append(protocol_dict)

    return {"protocols": protocols, "total_count": total_count}
