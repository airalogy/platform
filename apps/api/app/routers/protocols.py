from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from fastapi.params import Query
from pydantic import BaseModel, StringConstraints
from sqlalchemy import and_, distinct, exists, func, or_, select, update

from app.config import config
from app.database import DBSession
from app.models.lab import Lab
from app.models.project import PermissionType, Project, ProjectRole
from app.models.project_group import (
    ProjectGroupProtocol,
    ProjectGroupUser,
    ProtocolUser,
)
from app.models.protocol_folder import ProtocolFolder, ProtocolFolderProtocol
from app.models.protocol import Protocol, ProtocolStatus
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.user import User
from app.routers.permission import check_user_permission
from app.routers.utils import UUID, UidStr
from app.services.access_control import structured_protocol_ids_for_action

from .depends import CurrentUser, OptionalCurrentUser

router = APIRouter(
    prefix="/protocols",
    tags=["protocols"],
)


@router.get("")
async def get_protocols(
    db_session: DBSession,
    current_user: OptionalCurrentUser,
    lab_uid: UidStr | None = None,
    project_uid: UidStr | None = None,
    project_id: UUID | None = None,
    uid: UidStr | None = None,
    search_by: Literal["uid", "name"] | None = "name",
    search_str: str | None = None,
    sorted_by: Literal["stars_count", "forks_count", "updated_at"] | None = None,
    folder_id: int | None = None,
    folder_empty: bool | None = None,
    page: int = 1,
    page_size: int = 10,
):
    if project_id is None and (project_uid is None or lab_uid is None):
        raise HTTPException(
            status_code=400,
            detail="project_id or (project_uid and lab_uid) is required",
        )

    # Build conditions
    conditions = [Protocol.deleted_at.is_(None)]
    # project = None

    if project_id is not None:
        project = await Project.find(db_session, id=project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        conditions.append(Protocol.project_id == project_id)
    elif project_uid is not None:
        lab = await Lab.find_by(db_session, [Lab.uid == lab_uid])
        if lab is None:
            raise HTTPException(status_code=404, detail="Lab not found")
        project = await Project.find_by(
            db_session,
            [
                Project.lab_id == lab.id,
                Project.uid == project_uid,
                Project.deleted_at.is_(None),
            ],
        )
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        conditions.append(Protocol.project_id == project.id)
    if uid is not None:
        conditions.append(Protocol.uid == uid)

    if folder_id is not None and folder_empty:
        raise HTTPException(
            status_code=400, detail="folder_id and folder_empty cannot both be set"
        )

    if folder_id is not None:
        folder = await ProtocolFolder.find(db_session, id=folder_id)
        if folder.project_id != project.id:
            raise HTTPException(status_code=404, detail="Folder not found")
        conditions.append(
            Protocol.id.in_(
                select(ProtocolFolderProtocol.protocol_id).where(
                    ProtocolFolderProtocol.protocol_folder_id == folder_id
                )
            )
        )
    elif folder_empty:
        conditions.append(
            ~exists().where(ProtocolFolderProtocol.protocol_id == Protocol.id)
        )

    structured_protocol_ids: set[UUID] = set()
    structured_only = False
    if (
        current_user is not None
        and config.effective_lab_structure_mode == "structured"
    ):
        candidate_protocols = (
            await db_session.scalars(
                select(Protocol).where(
                    Protocol.project_id == project.id,
                    Protocol.deleted_at.is_(None),
                )
            )
        ).all()
        structured_protocol_ids = await structured_protocol_ids_for_action(
            db_session,
            current_user.id,
            project,
            list(candidate_protocols),
            "read_protocol",
        )
    try:
        user_role = await check_user_permission(
            db_session,
            project=project,
            user=current_user,
            action="read_protocol",
        )
    except HTTPException:
        if not structured_protocol_ids:
            raise
        user_role = ProjectRole.VIEWER
        structured_only = True

    if current_user is None and project.permission_type == PermissionType.PROTOCOL_LEVEL:
        return {"protocols": [], "total_count": 0}

    # Filter protocols by permission when permission_type=2
    # Project owners and managers see all protocols
    if (
        project.permission_type == PermissionType.PROTOCOL_LEVEL
        and current_user is not None
        and user_role > ProjectRole.MANAGER
    ):
        # User needs explicit protocol permission - filter by direct or group assignment
        # Subquery for protocols user has direct access to
        direct_access = select(ProtocolUser.protocol_id).where(
            ProtocolUser.user_id == current_user.id
        )
        # Subquery for protocols user has access to via project groups
        group_access = (
            select(ProjectGroupProtocol.protocol_id)
            .select_from(ProjectGroupProtocol)
            .join(
                ProjectGroupUser,
                ProjectGroupProtocol.project_group_id
                == ProjectGroupUser.project_group_id,
            )
            .where(ProjectGroupUser.user_id == current_user.id)
        )
        # Also include protocols where user is the creator
        conditions.append(
            or_(
                Protocol.id.in_(direct_access),
                Protocol.id.in_(group_access),
                Protocol.user_id == current_user.id,
                Protocol.id.in_(structured_protocol_ids),
            )
        )
    elif structured_only:
        conditions.append(Protocol.id.in_(structured_protocol_ids))

    if search_str is not None:
        if search_by == "uid":
            conditions.append(Protocol.uid.ilike(f"%{search_str}%"))
        elif search_by == "name":
            conditions.append(Protocol.name.ilike(f"%{search_str}%"))

    # Start building the query
    query = (
        select(
            Protocol,
            ProtocolVersion,
            Project.name.label("project_name"),
            Project.uid.label("project_uid"),
            Lab.id.label("lab_id"),
            Lab.name.label("lab_name"),
            Lab.uid.label("lab_uid"),
            User.username.label("user_username"),
            User.name.label("user_name"),
        )
        .select_from(Protocol)
        .join(
            ProtocolVersion,
            and_(
                ProtocolVersion.protocol_id == Protocol.id,
                ProtocolVersion.version == Protocol.latest_version,
            ),
        )
        .join(Project, Project.id == Protocol.project_id)
        .join(Lab, Lab.id == Project.lab_id)
        .join(User, User.id == Protocol.user_id)
    )

    # Apply order by
    if sorted_by == "stars_count":
        query_order = [Protocol.stars_count.desc(), Protocol.id.desc()]
    elif sorted_by == "forks_count":
        query_order = [Protocol.forks_count.desc(), Protocol.id.desc()]
    elif sorted_by == "updated_at":
        query_order = [Protocol.updated_at.desc()]
    else:  # default to id
        query_order = [Protocol.id.desc()]

    # Apply conditions
    if conditions:
        query = query.where(*conditions)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_count = await db_session.scalar(count_query)

    # Add pagination
    query = query.order_by(*query_order).limit(page_size).offset((page - 1) * page_size)

    # Execute query
    result = await db_session.execute(query)
    rows = result.all()

    folder_map: dict[UUID, list[int]] = {}
    protocol_ids = [row.Protocol.id for row in rows]
    if protocol_ids:
        folder_result = await db_session.execute(
            select(
                ProtocolFolderProtocol.protocol_id,
                ProtocolFolderProtocol.protocol_folder_id,
            ).where(ProtocolFolderProtocol.protocol_id.in_(protocol_ids))
        )
        for row in folder_result:
            folder_map.setdefault(row.protocol_id, []).append(
                row.protocol_folder_id
            )

    # Process results with additional counts
    protocols = []
    for row in rows:
        # Get records count
        record_conditions = [
            Record.protocol_id == row.Protocol.id,
            Record.deleted_at.is_(None),
        ]
        if project.is_private and user_role == ProjectRole.RECORDER:
            record_conditions.append(Record.user_id == current_user.id)
        record_query = (
            select(func.count(distinct(Record.id)))
            .select_from(Record)
            .where(*record_conditions)
        )
        records_count = await db_session.scalar(record_query)

        row.Protocol.lab_uid = row.lab_uid
        row.Protocol.project_uid = row.project_uid
        protocol_dict = row.Protocol.as_dict(
            project={
                "id": row.Protocol.project_id,
                "name": row.project_name,
                "uid": row.project_uid,
            },
            lab={
                "id": row.lab_id,
                "name": row.lab_name,
                "uid": row.lab_uid,
            },
            user={
                "id": row.Protocol.user_id,
                "username": row.user_username,
                "name": row.user_name,
            },
            json_schema=row.ProtocolVersion.json_schema,
            fields=row.ProtocolVersion.fields,
            aimd=row.ProtocolVersion.aimd,
            assigners=row.ProtocolVersion.assigners,
            assigner_graph=row.ProtocolVersion.assigner_graph,
            records_count=records_count,
        )
        protocol_dict["folder_ids"] = folder_map.get(row.Protocol.id, [])

        protocols.append(protocol_dict)

    return {"protocols": protocols, "total_count": total_count}


async def protocol_response(
    db_session: DBSession,
    current_user: User | None,
    protocol: Protocol | None = None,
    version: str | None = None,
    project: Project | None = None,
    lab: Lab | None = None,
) -> dict:
    if protocol is None:
        raise HTTPException(status_code=404, detail="Protocol not found")

    if project is None:
        project = await Project.find(db_session, id=protocol.project_id)
    if lab is None:
        lab = await Lab.find(db_session, id=project.lab_id)
    if version is None:
        version = protocol.latest_version
    protocol_version = await ProtocolVersion.find_by(
        db_session,
        [
            ProtocolVersion.protocol_id == protocol.id,
            ProtocolVersion.version == version,
        ],
    )
    if protocol_version is None:
        raise HTTPException(
            status_code=404,
            detail=f"Protocol version: {version} not found",
        )

    # Check user permission
    user_role = await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
        protocol=protocol,
    )

    # Get user info
    user = await User.find(db_session, id=protocol.user_id)

    record_conditions = [
        Record.protocol_id == protocol.id,
        Record.deleted_at.is_(None),
    ]
    if (
        current_user is not None
        and project.is_private
        and user_role == ProjectRole.RECORDER
    ):
        record_conditions.append(Record.user_id == current_user.id)
    record_query = (
        select(func.count(distinct(Record.id)))
        .select_from(Record)
        .where(*record_conditions)
    )
    records_count = await db_session.scalar(record_query)

    folder_result = await db_session.execute(
        select(ProtocolFolderProtocol.protocol_folder_id).where(
            ProtocolFolderProtocol.protocol_id == protocol.id
        )
    )
    folder_ids = [row.protocol_folder_id for row in folder_result]

    # Build response
    protocol.lab_uid = lab.uid
    protocol.project_uid = project.uid
    protocol.version = version
    return protocol.as_dict(
        project={
            "id": project.id,
            "name": project.name,
            "uid": project.uid,
        },
        lab={
            "id": lab.id,
            "name": lab.name,
            "uid": lab.uid,
        },
        user={
            "id": user.id,
            "username": user.username,
            "name": user.name,
        },
        json_schema=protocol_version.json_schema,
        fields=protocol_version.fields,
        aimd=protocol_version.aimd,
        assigners=protocol_version.assigners,
        assigner_graph=protocol_version.assigner_graph,
        metadata=protocol_version.meta_data,
        records_count=records_count,
        folder_ids=folder_ids,
    )


@router.get("/by_uid")
async def get_protocol_by_uid(
    lab_uid: UidStr,
    project_uid: UidStr,
    protocol_uid: UidStr,
    db_session: DBSession,
    current_user: OptionalCurrentUser,
    version: str | None = None,
):
    # Find the lab first
    lab = await Lab.find_by(db_session, [Lab.uid == lab_uid])
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")

    # Find the project
    project = await Project.find_by(
        db_session,
        [
            Project.uid == project_uid,
            Project.lab_id == lab.id,
            Project.deleted_at.is_(None),
        ],
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    protocol = await Protocol.find_by(
        db_session,
        [
            Protocol.uid == protocol_uid,
            Protocol.project_id == project.id,
            Protocol.deleted_at.is_(None),
        ],
    )

    return await protocol_response(
        db_session=db_session,
        current_user=current_user,
        protocol=protocol,
        project=project,
        lab=lab,
        version=version,
    )


@router.get("/by_airalogy_id")
async def get_protocol_by_airalogy_id(
    db_session: DBSession,
    current_user: OptionalCurrentUser,
    airalogy_protocol_id: Annotated[
        str,
        StringConstraints(
            max_length=256,
            strip_whitespace=True,
            pattern=r"airalogy\.id\.lab\.[a-zA-Z0-9_-]+\.project\.[a-zA-Z0-9_-]+\.protocol\.[a-zA-Z0-9_-]+\.v\.[0-9]+\.[0-9]+\.[0-9]+",
        ),
    ],
):
    # airalogy_protocol_id format: airalogy.id.lab.<lab_id>.project.<project_id>.protocol.<protocol_id>.version.<version>
    if not airalogy_protocol_id.startswith("airalogy.id.lab."):
        raise HTTPException(
            status_code=404,
            detail=f"Invalid airalogy_protocol_id: {airalogy_protocol_id}",
        )
    ary = airalogy_protocol_id.split(".")
    if len(ary) != 12:
        raise HTTPException(
            status_code=404,
            detail=f"Invalid airalogy_protocol_id: {airalogy_protocol_id}",
        )
    lab_uid = ary[3]
    project_uid = ary[5]
    protocol_uid = ary[7]
    version = f"{ary[9]}.{ary[10]}.{ary[11]}"

    lab = await Lab.find_by(db_session, [Lab.uid == lab_uid])
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")

    project = await Project.find_by(
        db_session,
        [
            Project.uid == project_uid,
            Project.lab_id == lab.id,
            Project.deleted_at.is_(None),
        ],
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    protocol = await Protocol.find_by(
        db_session,
        [
            Protocol.uid == protocol_uid,
            Protocol.project_id == project.id,
            Protocol.deleted_at.is_(None),
        ],
    )
    return await protocol_response(
        db_session=db_session,
        current_user=current_user,
        protocol=protocol,
        project=project,
        lab=lab,
        version=version,
    )


@router.get("/check_uid")
async def check_protocol_uid_exists(
    db_session: DBSession,
    lab_uid: UidStr = Query(),
    project_uid: UidStr = Query(),
    uid: UidStr = Query(),
):
    lab = await Lab.find_by(db_session, [Lab.uid == lab_uid])
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")

    project = await Project.find_by(
        db_session,
        [
            Project.uid == project_uid,
            Project.lab_id == lab.id,
            Project.deleted_at.is_(None),
        ],
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    await check_protocol_uid(db_session, project.id, uid)
    return {"valid": True, "message": "Protocol UID is valid and available"}


class ProtocolReuseParams(BaseModel):
    target_project_id: UUID
    name: (
        Annotated[
            str, StringConstraints(min_length=1, max_length=128, strip_whitespace=True)
        ]
        | None
    ) = None
    uid: UidStr | None = None


@router.get("/{protocol_id}")
async def get_protocol_by_id(
    protocol_id: UUID,
    db_session: DBSession,
    current_user: OptionalCurrentUser,
    version: str | None = None,
):
    protocol = await Protocol.find(db_session, id=protocol_id)
    return await protocol_response(
        db_session=db_session,
        current_user=current_user,
        protocol=protocol,
        version=version,
    )


@router.post("/{protocol_id}/reuse")
async def reuse_protocol(
    protocol_id: UUID,
    params: ProtocolReuseParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=params.target_project_id)
    lab = await Lab.find(db_session, id=project.lab_id)
    if not project:
        raise HTTPException(status_code=400, detail="Project not exists")
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="create_protocol",
    )

    parent_protocol = await Protocol.find(db_session, id=protocol_id)
    parent_project = await Project.find(db_session, id=parent_protocol.project_id)
    await check_user_permission(
        db_session,
        project=parent_project,
        user=current_user,
        action="read_protocol",
        protocol=parent_protocol,
    )
    parent_protocol_version = await ProtocolVersion.find_by(
        db_session,
        [
            ProtocolVersion.protocol_id == parent_protocol.id,
            ProtocolVersion.version == parent_protocol.latest_version,
        ],
    )

    if params.uid is None:
        params.uid = parent_protocol.uid
    if params.name is None:
        params.name = parent_protocol.name

    protocol = await Protocol.find_by(
        db_session,
        [
            Protocol.project_id == params.target_project_id,
            Protocol.uid == params.uid,
            Protocol.deleted_at.is_(None),
        ],
    )
    if protocol:
        raise HTTPException(
            status_code=400,
            detail=f"Protocol uid {params.uid} already exists in your project",
        )

    protocol = Protocol(
        user_id=current_user.id,
        name=params.name,
        uid=params.uid,
        project_id=params.target_project_id,
        parent_protocol_id=parent_protocol.id,
        parent_protocol_version=parent_protocol.latest_version,
        latest_version=parent_protocol.latest_version,
        description=parent_protocol.description,
        disciplines=parent_protocol.disciplines,
        keywords=parent_protocol.keywords,
    )
    db_session.add(protocol)
    await db_session.flush()
    protocol.lab_uid = lab.uid
    protocol.project_uid = project.uid

    protocol_version = ProtocolVersion(
        protocol_id=protocol.id,
        json_schema=parent_protocol_version.json_schema,
        fields=parent_protocol_version.fields,
        aimd=parent_protocol_version.aimd,
        assigners=parent_protocol_version.assigners,
        assigner_graph=parent_protocol_version.assigner_graph,
        version=parent_protocol_version.version,
        meta_data=parent_protocol_version.meta_data,
    )
    db_session.add(protocol_version)
    await db_session.flush()

    await parent_protocol_version.copy_package(protocol_version.package_object_key)

    parent_protocol.forks_count = await Protocol.count(
        db_session,
        where_conditions=[
            Protocol.parent_protocol_id == parent_protocol.id,
            Protocol.deleted_at.is_(None),
        ],
    )
    await db_session.commit()
    return protocol


@router.get("/{protocol_id}/reuses")
async def get_protocol_reuses(
    protocol_id: UUID,
    db_session: DBSession,
    current_user: OptionalCurrentUser,
    page: int = 1,
    page_size: int = 20,
):
    protocol = await Protocol.find(db_session, id=protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
        protocol=protocol,
    )
    # Start building the query
    query = (
        select(
            Protocol,
            Project.name.label("project_name"),
            Project.uid.label("project_uid"),
            Project.type.label("project_type"),
            Lab.id.label("lab_id"),
            Lab.name.label("lab_name"),
            Lab.uid.label("lab_uid"),
            User.username.label("user_username"),
            User.name.label("user_name"),
        )
        .select_from(Protocol)
        .join(Project, Project.id == Protocol.project_id)
        .join(Lab, Lab.id == Project.lab_id)
        .join(User, User.id == Protocol.user_id)
        .where(
            Protocol.parent_protocol_id == protocol.id,
            Protocol.deleted_at.is_(None),
        )
        .order_by(Protocol.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )

    result = await db_session.execute(query)
    reuses = []
    for row in result:
        row.Protocol.lab_uid = row.lab_uid
        row.Protocol.project_uid = row.project_uid
        protocol_dict = row.Protocol.as_dict(
            only=[
                "id",
                "uid",
                "name",
                "project_id",
                "created_at",
                "airalogy_id",
                "parent_protocol_id",
                "parent_protocol_version",
            ],
            project={
                "id": row.Protocol.project_id,
                "name": row.project_name,
                "uid": row.project_uid,
                "type": row.project_type,
            },
            lab={
                "id": row.lab_id,
                "name": row.lab_name,
                "uid": row.lab_uid,
            },
            user={
                "id": row.Protocol.user_id,
                "username": row.user_username,
                "name": row.user_name,
            },
        )
        reuses.append(protocol_dict)
    return {"protocols": reuses, "total_count": protocol.forks_count}


class ProtocolUpdateParams(BaseModel):
    name: (
        Annotated[
            str, StringConstraints(min_length=1, max_length=128, strip_whitespace=True)
        ]
        | None
    ) = None
    description: (
        Annotated[str, StringConstraints(max_length=1024, strip_whitespace=True)] | None
    ) = None
    env_vars: str | None = None
    disciplines: list[str] | None = None
    keywords: list[str] | None = None


@router.put("/{protocol_id}")
async def update_protocol(
    protocol_id: UUID,
    params: ProtocolUpdateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    protocol = await Protocol.find(db_session, id=protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="update_protocol",
        protocol=protocol,
    )

    if params.env_vars is not None and params.env_vars != protocol.env_vars:
        protocol.env_vars = params.env_vars
    if params.name is not None and params.name != protocol.name:
        protocol.name = params.name
    if params.description is not None and params.description != protocol.description:
        protocol.description = params.description
    if params.disciplines is not None and params.disciplines != protocol.disciplines:
        protocol.disciplines = params.disciplines
    if params.keywords is not None and params.keywords != protocol.keywords:
        protocol.keywords = params.keywords

    if db_session.is_modified(protocol):
        protocol.updated_at = datetime.now()

    await db_session.commit()
    return protocol


@router.delete("/{protocol_id}")
async def delete_protocol(
    protocol_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    protocol: Protocol = await Protocol.find(db_session, id=protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="delete_protocol",
        protocol=protocol,
    )

    protocol.status = ProtocolStatus.DELETED
    protocol.deleted_at = datetime.now()
    await db_session.flush()

    # update parent protocol forks_count
    if protocol.parent_protocol_id:
        parent_forks_count = await Protocol.count(
            db_session,
            [
                Protocol.parent_protocol_id == protocol.parent_protocol_id,
                Protocol.deleted_at.is_(None),
            ],
        )
        await db_session.execute(
            (
                update(Protocol)
                .where(Protocol.id == protocol.parent_protocol_id)
                .values(forks_count=parent_forks_count)
            )
        )

    await db_session.commit()
    return {"message": "success"}


@router.get("/{protocol_id}/env_vars")
async def get_protocol_env_vars(
    protocol_id: UUID, db_session: DBSession, current_user: CurrentUser
):
    protocol = await Protocol.find(db_session, id=protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="update_protocol",
        protocol=protocol,
    )

    return {"env_vars": protocol.env_vars}


async def check_protocol_uid(
    db_session: DBSession,
    project_id: UUID,
    uid: UidStr,
    protocol_id: UUID | None = None,
):
    # Check for duplicates within the same project
    conditions = [
        Protocol.uid == uid,
        Protocol.project_id == project_id,
        Protocol.deleted_at.is_(None),
    ]
    if protocol_id is not None:
        conditions.append(Protocol.id != protocol_id)

    exists = await Protocol.exists(db_session, conditions)
    if exists:
        raise HTTPException(
            status_code=400, detail="Protocol UID already exists in this project"
        )
