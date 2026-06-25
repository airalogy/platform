from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import DBSession
from app.models.project import PermissionType, Project, ProjectRole, ProjectUser
from app.models.project_group import ProtocolUser
from app.models.protocol import Protocol
from app.models.user import User
from app.routers.permission import check_user_permission
from app.routers.utils import UUID

from .depends import CurrentUser, get_current_user

router = APIRouter(
    prefix="/protocols/{protocol_id}/users",
    tags=["protocol_users"],
    dependencies=[Depends(get_current_user)],
)


async def check_project_permission_type(project: Project):
    """Check that project uses protocol-level permissions"""
    if project.permission_type != PermissionType.PROTOCOL_LEVEL:
        raise HTTPException(
            status_code=400,
            detail="Project does not use protocol-level permissions",
        )


class ProtocolUserAddParams(BaseModel):
    user_id: UUID
    role: ProjectRole


@router.get("")
async def get_protocol_users(
    protocol_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 10,
):
    protocol = await Protocol.find(db_session, id=protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(db_session, project, current_user, "read_protocol")

    total_count = await ProtocolUser.count(
        db_session, [ProtocolUser.protocol_id == protocol_id]
    )

    query = (
        select(User, ProtocolUser.role.label("protocol_role"))
        .options(selectinload(User.avatar_attachment))
        .join(ProtocolUser, ProtocolUser.user_id == User.id)
        .where(ProtocolUser.protocol_id == protocol_id)
        .order_by(ProtocolUser.role.asc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    result = (await db_session.execute(query)).all()
    users = [r.User.as_dict(protocol_role=r.protocol_role) for r in result]

    return {"users": users, "total_count": total_count}


@router.post("")
async def add_user_to_protocol(
    protocol_id: UUID,
    params: ProtocolUserAddParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    protocol = await Protocol.find(db_session, id=protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_project_permission_type(project)
    await check_user_permission(db_session, project, current_user, "set_role_other")

    user = await User.find(db_session, id=params.user_id)

    existing = await ProtocolUser.find_by(
        db_session,
        [ProtocolUser.protocol_id == protocol_id, ProtocolUser.user_id == user.id],
    )
    if existing:
        raise HTTPException(status_code=400, detail="User already has access")

    existing_in_project = await ProjectUser.find_by(
        db_session,
        [ProjectUser.project_id == project.id, ProjectUser.user_id == user.id],
    )
    if not existing_in_project:
        project_user = ProjectUser(
            project_id=project.id,
            user_id=user.id,
            role=params.role,
            create_user_id=current_user.id,
        )
        db_session.add(project_user)

    protocol_user = ProtocolUser(
        protocol_id=protocol_id,
        user_id=user.id,
        role=params.role,
        create_user_id=current_user.id,
    )
    db_session.add(protocol_user)
    await db_session.commit()

    return {"message": "success"}


@router.put("/{user_id}")
async def update_protocol_user_role(
    protocol_id: UUID,
    user_id: UUID,
    params: ProtocolUserAddParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    protocol = await Protocol.find(db_session, id=protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_project_permission_type(project)
    await check_user_permission(db_session, project, current_user, "set_role_other")

    protocol_user = await ProtocolUser.find_by(
        db_session,
        [ProtocolUser.protocol_id == protocol_id, ProtocolUser.user_id == user_id],
    )
    if protocol_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    protocol_user.role = params.role
    await db_session.commit()

    return {"message": "success"}


@router.delete("/{user_id}")
async def delete_user_from_protocol(
    protocol_id: UUID,
    user_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    protocol = await Protocol.find(db_session, id=protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_project_permission_type(project)
    await check_user_permission(db_session, project, current_user, "set_role_other")

    protocol_user = await ProtocolUser.find_by(
        db_session,
        [ProtocolUser.protocol_id == protocol_id, ProtocolUser.user_id == user_id],
    )
    if protocol_user is None:
        return {"message": "success"}

    await db_session.delete(protocol_user)
    await db_session.commit()

    return {"message": "success"}
