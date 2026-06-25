from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StringConstraints
from pydash import py_
from sqlalchemy import delete, func, select
from typing_extensions import Annotated

from app.database import DBSession
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_folder import ProtocolFolder, ProtocolFolderProtocol
from app.routers.permission import check_user_permission

from .depends import CurrentUser, get_current_user
from .utils import UUID

router = APIRouter(
    prefix="/projects/{project_id}",
    tags=["protocol_folders"],
    dependencies=[Depends(get_current_user)],
)


class ProtocolFolderCreateParams(BaseModel):
    name: Annotated[str, StringConstraints(max_length=64, strip_whitespace=True)]
    description: Annotated[
        str, StringConstraints(max_length=128, strip_whitespace=True)
    ] = ""


class ProtocolFolderUpdateParams(BaseModel):
    name: (
        Annotated[str, StringConstraints(max_length=64, strip_whitespace=True)] | None
    ) = None
    description: (
        Annotated[str, StringConstraints(max_length=128, strip_whitespace=True)] | None
    ) = None


class ProtocolFolderAssignParams(BaseModel):
    folder_ids: list[int] = []


class ProtocolFolderProtocolsParams(BaseModel):
    protocol_ids: list[UUID] = []


@router.get("/protocol_folders")
async def get_protocol_folders(
    project_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 50,
):
    project = await Project.find(db_session, id=project_id)
    await check_user_permission(db_session, project, current_user, "read_protocol")

    count_query = select(func.count()).select_from(ProtocolFolder).where(
        ProtocolFolder.project_id == project_id
    )
    total_count = await db_session.scalar(count_query)

    query = (
        select(
            ProtocolFolder,
            func.count(ProtocolFolderProtocol.id).label("protocols_count"),
        )
        .outerjoin(
            ProtocolFolderProtocol,
            ProtocolFolderProtocol.protocol_folder_id == ProtocolFolder.id,
        )
        .where(ProtocolFolder.project_id == project_id)
        .group_by(ProtocolFolder.id)
        .order_by(ProtocolFolder.id.asc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    result = await db_session.execute(query)
    folders = [
        row.ProtocolFolder.as_dict(protocols_count=row.protocols_count) for row in result
    ]

    return {"folders": folders, "total_count": total_count}


@router.post("/protocol_folders")
async def create_protocol_folder(
    project_id: UUID,
    params: ProtocolFolderCreateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=project_id)
    await check_user_permission(db_session, project, current_user, "set_role_other")

    existing = await ProtocolFolder.find_by(
        db_session,
        [
            ProtocolFolder.project_id == project_id,
            ProtocolFolder.name == params.name,
        ],
    )
    if existing:
        raise HTTPException(status_code=400, detail="Folder name already exists")

    folder = ProtocolFolder(
        project_id=project_id,
        name=params.name,
        description=params.description or "",
        create_user_id=current_user.id,
    )
    db_session.add(folder)
    await db_session.commit()
    await db_session.refresh(folder)
    return folder


@router.put("/protocol_folders/{folder_id}")
async def update_protocol_folder(
    project_id: UUID,
    folder_id: int,
    params: ProtocolFolderUpdateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=project_id)
    await check_user_permission(db_session, project, current_user, "set_role_other")

    folder = await ProtocolFolder.find(db_session, id=folder_id)
    if folder.project_id != project_id:
        raise HTTPException(status_code=404, detail="Folder not found")

    if params.name:
        existing = await ProtocolFolder.find_by(
            db_session,
            [
                ProtocolFolder.project_id == project_id,
                ProtocolFolder.name == params.name,
            ],
        )
        if existing and existing.id != folder_id:
            raise HTTPException(status_code=400, detail="Folder name already exists")

    folder.set_attrs(**params.model_dump(exclude_none=True))
    await db_session.commit()
    return folder


@router.delete("/protocol_folders/{folder_id}")
async def delete_protocol_folder(
    project_id: UUID,
    folder_id: int,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=project_id)
    await check_user_permission(db_session, project, current_user, "set_role_other")

    folder = await ProtocolFolder.find(db_session, id=folder_id)
    if folder.project_id != project_id:
        raise HTTPException(status_code=404, detail="Folder not found")

    await db_session.execute(
        delete(ProtocolFolderProtocol).where(
            ProtocolFolderProtocol.protocol_folder_id == folder_id
        )
    )
    await db_session.delete(folder)
    await db_session.commit()
    return {"message": "success"}


@router.put("/protocol_folders/{folder_id}/protocols")
async def set_folder_protocols(
    project_id: UUID,
    folder_id: int,
    params: ProtocolFolderProtocolsParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=project_id)
    await check_user_permission(db_session, project, current_user, "set_role_other")

    folder = await ProtocolFolder.find(db_session, id=folder_id)
    if folder.project_id != project_id:
        raise HTTPException(status_code=404, detail="Folder not found")

    protocol_ids = py_.uniq(params.protocol_ids or [])
    if protocol_ids:
        result = await db_session.execute(
            select(Protocol.id).where(
                Protocol.project_id == project_id,
                Protocol.deleted_at.is_(None),
                Protocol.id.in_(protocol_ids),
            )
        )
        valid_ids = {row.id for row in result}
        if len(valid_ids) != len(set(protocol_ids)):
            raise HTTPException(status_code=400, detail="Protocol not found")

    await db_session.execute(
        delete(ProtocolFolderProtocol).where(
            ProtocolFolderProtocol.protocol_folder_id == folder_id
        )
    )
    for protocol_id in protocol_ids:
        db_session.add(
            ProtocolFolderProtocol(
                protocol_folder_id=folder_id,
                protocol_id=protocol_id,
                create_user_id=current_user.id,
            )
        )
    await db_session.commit()

    return {"message": "success", "protocol_ids": protocol_ids}


@router.put("/protocols/{protocol_id}/folders")
async def set_protocol_folders(
    project_id: UUID,
    protocol_id: UUID,
    params: ProtocolFolderAssignParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find(db_session, id=project_id)
    protocol = await Protocol.find(db_session, id=protocol_id)
    if protocol.project_id != project_id:
        raise HTTPException(status_code=404, detail="Protocol not in project")

    await check_user_permission(
        db_session, project, current_user, "update_protocol", protocol=protocol
    )

    folder_ids = py_.uniq(params.folder_ids or [])
    if folder_ids:
        result = await db_session.execute(
            select(ProtocolFolder.id).where(
                ProtocolFolder.project_id == project_id,
                ProtocolFolder.id.in_(folder_ids),
            )
        )
        valid_ids = {row.id for row in result}
        if len(valid_ids) != len(folder_ids):
            raise HTTPException(status_code=400, detail="Folder not found")

    await db_session.execute(
        delete(ProtocolFolderProtocol).where(
            ProtocolFolderProtocol.protocol_id == protocol_id
        )
    )
    for folder_id in folder_ids:
        db_session.add(
            ProtocolFolderProtocol(
                protocol_folder_id=folder_id,
                protocol_id=protocol_id,
                create_user_id=current_user.id,
            )
        )
    await db_session.commit()

    return {"message": "success", "folder_ids": folder_ids}
