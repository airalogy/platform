from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, StringConstraints
from pydash import py_
from sqlalchemy import and_, delete, select
from sqlalchemy.orm import selectinload
from typing_extensions import Annotated

from app.config import config
from app.database import DBSession
from app.libs.lab_force_delete import (
    LAB_FORCE_DELETE_PENDING,
    LAB_FORCE_DELETE_RUNNING,
    collect_lab_force_delete_manifest,
    run_lab_force_delete_job,
)
from app.models.group import Group, GroupProject, GroupUser
from app.models.lab import Lab, LabRole, LabUser
from app.models.lab_force_delete_job import LabForceDeleteJob
from app.models.pinned_item import PinnedItem, PinnedResourceType
from app.models.project import Project, ProjectUser
from app.models.project_group import ProjectGroup, ProjectGroupProtocol, ProjectGroupUser
from app.models.protocol import Protocol
from app.models.user import User
from app.models.user_alias import UserAlias
from app.routers.utils import UidStr

from .depends import CurrentUser, get_current_user

DEFAULT_PROJECT_UIDS = {"public_protocols", "lab_protocols"}

router = APIRouter(
    prefix="/labs", tags=["labs"], dependencies=[Depends(get_current_user)]
)


class LabQueryParams(BaseModel):
    name: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, max_length=64),
        ]
        | None
    ) = None


@router.get("")
async def get_labs(
    db_session: DBSession,
    params=Depends(LabQueryParams),
    page: int = 1,
    page_size: int = 10,
):
    where_conditions = Lab.conditions_from_dict(params.model_dump(exclude_none=True))
    total_count = await Lab.count(db_session, where_conditions)
    labs = await Lab.all(
        db_session,
        where_conditions,
        page,
        page_size,
        options=selectinload(Lab.logo_attachment),
    )
    [await lab.load_logo_attachment(db_session) for lab in labs]

    return {"data": labs, "total_count": total_count}


async def lab_response(
    lab: Lab,
    db_session: DBSession,
):
    query = (
        select(User, LabUser.role.label("lab_role"))
        .options(selectinload(User.avatar_attachment))
        .join(LabUser)
        .where(LabUser.lab_id == lab.id)
    )
    result = (await db_session.execute(query)).all()
    users = [d.User.as_dict(lab_role=d.lab_role) for d in result]

    users_count = await LabUser.count(db_session, [LabUser.lab_id == lab.id])

    active_projects = (
        await db_session.execute(
            select(Project.id, Project.uid).where(
                Project.lab_id == lab.id,
                Project.deleted_at.is_(None),
            )
        )
    ).all()
    project_ids = [project.id for project in active_projects]
    default_project_ids = [
        project.id for project in active_projects if project.uid in DEFAULT_PROJECT_UIDS
    ]
    default_projects_count = len(default_project_ids)
    custom_projects_count = len(active_projects) - default_projects_count

    protocols_count = 0
    if project_ids:
        protocols_count = await Protocol.count(
            db_session,
            [
                Protocol.project_id.in_(project_ids),
                Protocol.deleted_at.is_(None),
            ],
        )

    default_projects_protocols_count = 0
    if default_project_ids:
        default_projects_protocols_count = await Protocol.count(
            db_session,
            [Protocol.project_id.in_(default_project_ids)],
        )

    await lab.load_logo_attachment(db_session)
    lab_dict = lab.as_dict(
        users=users,
        users_count=users_count,
        protocols_count=protocols_count,
        default_projects_count=default_projects_count,
        custom_projects_count=custom_projects_count,
        default_projects_protocols_count=default_projects_protocols_count,
    )

    return {"data": lab_dict}


async def cleanup_empty_default_projects(db_session: DBSession, lab_id: UUID):
    default_projects = await Project.all(
        db_session,
        [Project.lab_id == lab_id, Project.uid.in_(DEFAULT_PROJECT_UIDS)],
        page=1,
        page_size=len(DEFAULT_PROJECT_UIDS),
    )

    for project in default_projects:
        active_protocols_count = await Protocol.count(
            db_session,
            [
                Protocol.project_id == project.id,
                Protocol.deleted_at.is_(None),
            ],
        )
        if active_protocols_count > 0:
            raise HTTPException(
                status_code=400,
                detail="Default projects contain protocols",
            )

        protocols_count = await Protocol.count(
            db_session,
            [Protocol.project_id == project.id],
        )
        if protocols_count > 0:
            raise HTTPException(
                status_code=400,
                detail="Default projects contain protocols",
            )

        await db_session.execute(
            delete(ProjectUser).where(ProjectUser.project_id == project.id)
        )
        await db_session.execute(
            delete(GroupProject).where(GroupProject.project_id == project.id)
        )
        project_group_ids = (
            await db_session.execute(
                select(ProjectGroup.id).where(ProjectGroup.project_id == project.id)
            )
        ).scalars().all()
        if project_group_ids:
            await db_session.execute(
                delete(ProjectGroupProtocol).where(
                    ProjectGroupProtocol.project_group_id.in_(project_group_ids)
                )
            )
            await db_session.execute(
                delete(ProjectGroupUser).where(
                    ProjectGroupUser.project_group_id.in_(project_group_ids)
                )
            )
            await db_session.execute(
                delete(ProjectGroup).where(ProjectGroup.id.in_(project_group_ids))
            )
        await db_session.delete(project)

    await db_session.flush()


async def check_lab_uid(db_session: DBSession, uid: UidStr, lab_id: UUID | None = None):
    # Check for duplicates
    conditions = [Lab.uid == uid]
    if lab_id is not None:
        conditions.append(Lab.id != lab_id)

    exists = await Lab.exists(db_session, conditions)
    if exists:
        raise HTTPException(status_code=400, detail="Lab UID already exists")

    exists = await User.exists(db_session, [User.username == uid])
    if exists:
        raise HTTPException(status_code=400, detail="Lab UID already exists")


async def ensure_user_can_create_lab(db_session: DBSession, user_id: UUID):
    max_labs_per_user = config.MAX_LABS_PER_USER
    if max_labs_per_user <= 0:
        return

    created_labs_count = await Lab.count(db_session, [Lab.create_user_id == user_id])
    if created_labs_count >= max_labs_per_user:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Lab limit reached. Each account can have up to "
                f"{max_labs_per_user} labs in total, including the default lab."
            ),
        )


@router.get("/check_uid")
async def check_lab_uid_exists(uid: UidStr, db_session: DBSession):
    await check_lab_uid(db_session, uid)
    return {"result": True, "message": "UID is valid and available"}


@router.get("/uid/{lab_uid}")
async def get_lab_by_uid(
    lab_uid: str,
    db_session: DBSession,
):
    lab = await Lab.find_by(
        db_session, [Lab.uid == lab_uid], options=selectinload(Lab.logo_attachment)
    )
    if lab is None:
        raise HTTPException(status_code=400, detail="NoResultFound")
    return await lab_response(lab=lab, db_session=db_session)


@router.get("/{lab_id}")
async def get_lab_by_id(
    lab_id: UUID,
    db_session: DBSession,
):
    lab = await Lab.find(
        db_session, id=lab_id, options=selectinload(Lab.logo_attachment)
    )
    return await lab_response(lab=lab, db_session=db_session)
class LabAddUserParams(BaseModel):
    user_id: UUID
    role: LabRole = LabRole.MEMBER
    alias: str | None = None


class LabCreateParams(BaseModel):
    name: Annotated[
        str, StringConstraints(max_length=64, min_length=3, strip_whitespace=True)
    ]
    uid: UidStr
    description: Annotated[
        str, StringConstraints(max_length=128, strip_whitespace=True)
    ] = ""
    logo: str | None = None
    members: list[LabAddUserParams]


@router.post("")
async def create_lab(
    params: LabCreateParams, current_user: CurrentUser, db_session: DBSession
):
    await ensure_user_can_create_lab(db_session, current_user.id)

    # Add UID validation
    await check_lab_uid(db_session, params.uid)

    name_exists = await Lab.exists(db_session, [Lab.name == params.name])
    if name_exists:
        raise HTTPException(status_code=400, detail="Lab name already exists")

    # Create lab instance
    lab_data = params.model_dump(exclude={"members", "logo"})
    lab = Lab(
        **lab_data,
        create_user_id=current_user.id,
    )

    # Add to session and get ID
    db_session.add(lab)
    await db_session.flush()

    # Add members
    params.members.append(LabAddUserParams(user_id=current_user.id, role=LabRole.OWNER))
    members = py_.uniq_by(params.members, lambda i: i.user_id)
    for m in members:
        lab_user = LabUser(
            lab_id=lab.id,
            user_id=m.user_id,
            role=m.role,
            create_user_id=current_user.id,
        )
        db_session.add(lab_user)

    lab.users_count = len(members)

    # Handle logo as final step
    if params.logo:
        lab.logo = params.logo

    # Commit all changes
    await db_session.commit()

    return lab


class LabUpdateParams(BaseModel):
    description: Annotated[
        str, StringConstraints(max_length=128, strip_whitespace=True)
    ]
    name: (
        Annotated[
            str, StringConstraints(max_length=64, min_length=3, strip_whitespace=True)
        ]
        | None
    ) = None
    logo: str | None = None


class LabForceDeleteParams(BaseModel):
    lab_uid: UidStr
    confirm_irreversible: bool = False


@router.put("/{lab_id}")
async def update_lab(
    lab_id: UUID,
    params: LabUpdateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab: Lab = await Lab.find(
        db_session, id=lab_id, options=selectinload(Lab.logo_attachment)
    )
    if lab.create_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if params.name:
        name_exists = await Lab.exists(
            db_session, [Lab.name == params.name, Lab.id != lab.id]
        )
        if name_exists:
            raise HTTPException(status_code=400, detail="Lab name already exists")

    lab.set_attrs(**params.model_dump(exclude_none=True))
    await db_session.commit()
    await lab.load_logo_attachment(db_session)
    return lab


@router.get("/{lab_id}/force_delete_preview")
async def get_lab_force_delete_preview(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab: Lab = await Lab.find(db_session, id=lab_id)
    if lab.create_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    manifest = await collect_lab_force_delete_manifest(db_session, lab)
    return {"data": manifest["preview"]}


@router.post("/{lab_id}/force_delete")
async def force_delete_lab(
    lab_id: UUID,
    params: LabForceDeleteParams,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab: Lab = await Lab.find(db_session, id=lab_id, with_for_update=True)
    if lab.create_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if params.lab_uid != lab.uid:
        raise HTTPException(
            status_code=400,
            detail="Lab UID confirmation does not match",
        )

    if not params.confirm_irreversible:
        raise HTTPException(
            status_code=400,
            detail="Irreversible confirmation is required",
        )

    existing_job = await LabForceDeleteJob.find_by(
        db_session,
        [
            LabForceDeleteJob.lab_id == lab.id,
            LabForceDeleteJob.status.in_(
                [LAB_FORCE_DELETE_PENDING, LAB_FORCE_DELETE_RUNNING]
            ),
        ],
        with_for_update=True,
    )
    if existing_job is not None:
        raise HTTPException(
            status_code=409,
            detail="Lab force delete already in progress",
        )

    manifest = await collect_lab_force_delete_manifest(db_session, lab)
    job = LabForceDeleteJob(
        lab_id=lab.id,
        lab_uid_snapshot=lab.uid,
        lab_name_snapshot=lab.name,
        requested_by_user_id=current_user.id,
        status=LAB_FORCE_DELETE_PENDING,
        impact_summary=manifest["preview"],
    )
    db_session.add(job)
    await db_session.flush()
    await db_session.commit()

    background_tasks.add_task(run_lab_force_delete_job, job.id)
    return {"data": job.as_dict()}


@router.get("/{lab_id}/force_delete_jobs/{job_id}")
async def get_lab_force_delete_job(
    lab_id: UUID,
    job_id: int,
    current_user: CurrentUser,
    db_session: DBSession,
):
    job = await LabForceDeleteJob.find_by(
        db_session,
        [
            LabForceDeleteJob.id == job_id,
            LabForceDeleteJob.lab_id == lab_id,
        ],
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Lab force delete job not found")

    if job.requested_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return {"data": job.as_dict()}


@router.delete("/{lab_id}")
async def delete_lab(lab_id: UUID, current_user: CurrentUser, db_session: DBSession):
    lab: Lab = await Lab.find(db_session, id=lab_id)
    if lab.create_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    await cleanup_empty_default_projects(db_session, lab.id)

    projects_count = await Project.count(db_session, [Project.lab_id == lab.id])
    if projects_count > 0:
        raise HTTPException(status_code=400, detail="Lab has projects")

    group_ids = (
        await db_session.execute(select(Group.id).where(Group.lab_id == lab.id))
    ).scalars().all()
    if group_ids:
        await db_session.execute(delete(GroupUser).where(GroupUser.group_id.in_(group_ids)))
        await db_session.execute(delete(Group).where(Group.id.in_(group_ids)))

    await db_session.execute(delete(LabUser).where(LabUser.lab_id == lab.id))
    await db_session.execute(
        delete(PinnedItem).where(
            PinnedItem.resource_type == PinnedResourceType.LAB,
            PinnedItem.resource_id == lab.id,
        )
    )
    await db_session.delete(lab)
    await db_session.commit()
    return {"message": "success"}


@router.get("/{lab_id}/users")
async def get_lab_users(
    lab_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 10,
):
    total_count = await LabUser.count(db_session, [LabUser.lab_id == lab_id])
    query = (
        select(
            User,
            LabUser.role.label("lab_role"),
            LabUser.alias.label("lab_alias"),
            UserAlias.alias.label("user_alias"),
        )
        .options(selectinload(User.avatar_attachment))
        .join(LabUser)
        .outerjoin(
            UserAlias,
            and_(
                UserAlias.target_user_id == User.id,
                UserAlias.user_id == current_user.id,
            ),
        )
        .where(LabUser.lab_id == lab_id)
        .order_by(LabUser.role.asc(), LabUser.id.asc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    result = (await db_session.execute(query)).all()
    users = []
    for d in result:
        await d.User.load_avatar_attachment()
        user = d.User.as_dict(
            lab_role=d.lab_role,
            lab_alias=d.lab_alias,
            user_alias=d.user_alias,
        )
        users.append(user)

    return {"users": users, "total_count": total_count}


@router.post("/{lab_id}/users")
async def add_user_to_lab(
    lab_id: UUID,
    params: LabAddUserParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab: Lab = await Lab.find(db_session, id=lab_id)
    user = await User.find(db_session, id=params.user_id)
    exists = await LabUser.find_by(
        db_session, [LabUser.lab_id == lab.id, LabUser.user_id == user.id]
    )
    if exists:
        raise HTTPException(status_code=400, detail="User already in lab")

    lab_user = LabUser(
        lab_id=lab.id,
        user_id=user.id,
        role=params.role,
        create_user_id=current_user.id,
        alias=params.alias,
    )
    db_session.add(lab_user)
    await db_session.flush()
    lab_users_count = await LabUser.count(
        db_session, where_conditions=[LabUser.lab_id == lab.id]
    )
    lab.users_count = lab_users_count
    await db_session.commit()

    return {"message": "success"}


@router.put("/{lab_id}/users/{user_id}")
async def change_user_role_or_alias_in_lab(
    lab_id: UUID,
    user_id: UUID,
    params: LabAddUserParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab = await Lab.find(db_session, id=lab_id)
    if lab.create_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    lab_user = await LabUser.find_by(
        db_session,
        [LabUser.lab_id == lab_id, LabUser.user_id == user_id],
    )
    if lab_user is None:
        raise HTTPException(status_code=404, detail="User not found in lab")
    lab_user.role = params.role
    lab_user.alias = params.alias
    await db_session.commit()
    return {"message": "success"}


@router.delete("/{lab_id}/users/{user_id}")
async def delete_user_from_lab(
    lab_id: UUID,
    user_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab: Lab = await Lab.find(db_session, id=lab_id)
    if lab.create_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if user_id == current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    lab_user = await LabUser.find_by(
        db_session, [LabUser.lab_id == lab.id, LabUser.user_id == user_id]
    )
    if lab_user is None:
        return {"message": "success"}

    await db_session.delete(lab_user)
    await db_session.flush()

    lab.users_count = await LabUser.count(
        db_session, where_conditions=[LabUser.lab_id == lab.id]
    )
    await db_session.commit()
    return {"message": "success"}
