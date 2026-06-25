from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StringConstraints
from sqlalchemy import any_, delete, func, select
from sqlalchemy.orm import selectinload

from app.database import DBSession
from app.models.answer import Answer
from app.models.lab import Lab
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.question import Question
from app.models.star import Star, StarFolder, StarResourceType
from app.models.user import User
from app.routers.depends import CurrentUser, get_current_user
from app.routers.permission import check_user_permission

router = APIRouter(
    prefix="/stars",
    tags=["stars"],
    dependencies=[Depends(get_current_user)],
)

DEFAULT_STAR_FOLDER_NAME = "default"


def _is_default_folder_name(name: str | None) -> bool:
    return (name or "").strip().lower() == DEFAULT_STAR_FOLDER_NAME


async def _get_or_create_default_star_folder(
    db_session: DBSession,
    current_user: CurrentUser,
) -> StarFolder:
    default_folder = await StarFolder.find_by(
        db_session,
        [
            StarFolder.user_id == current_user.id,
            StarFolder.is_default.is_(True),
        ],
        with_for_update=True,
    )
    if default_folder:
        return default_folder

    fallback_folder = await StarFolder.find_by(
        db_session,
        [
            StarFolder.user_id == current_user.id,
            func.lower(StarFolder.name) == DEFAULT_STAR_FOLDER_NAME,
        ],
        with_for_update=True,
    )
    if fallback_folder:
        fallback_folder.is_default = True
        return fallback_folder

    folder = StarFolder(
        user_id=current_user.id,
        name=DEFAULT_STAR_FOLDER_NAME,
        is_default=True,
    )
    db_session.add(folder)
    await db_session.flush()
    return folder


async def _attach_star_route_info(
    db_session: DBSession,
    star_data: dict,
    protocol: Protocol | None,
    question_id: UUID | None = None,
):
    if protocol is None:
        return

    project = await Project.find_by(
        db_session,
        [
            Project.id == protocol.project_id,
            Project.deleted_at.is_(None),
        ],
    )
    if project is None:
        return

    lab = await Lab.find_by(db_session, [Lab.id == project.lab_id])
    if lab is None:
        return

    star_data["lab_uid"] = lab.uid
    star_data["project_uid"] = project.uid
    star_data["protocol_uid"] = protocol.uid
    if question_id is not None:
        star_data["question_id"] = str(question_id)


# StarFolder 相关的 Pydantic 模型
class StarFolderCreateParams(BaseModel):
    name: Annotated[
        str, StringConstraints(min_length=1, max_length=100, strip_whitespace=True)
    ]


class StarFolderUpdateParams(BaseModel):
    name: Annotated[
        str, StringConstraints(min_length=1, max_length=100, strip_whitespace=True)
    ]


# Star 相关的 Pydantic 模型
class StarCreateParams(BaseModel):
    resource_type: StarResourceType
    resource_id: UUID
    folder_ids: list[int] = []


class StarUpdateParams(BaseModel):
    folder_ids: list[int] | None = None


# StarFolder 接口
@router.get("/folders")
async def get_star_folders(
    db_session: DBSession,
    current_user: CurrentUser,
):
    """获取用户的收藏夹列表，包含不同资源类型的数量统计"""
    # 获取用户的所有收藏夹
    folders = await StarFolder.all(
        db_session,
        where_conditions=[StarFolder.user_id == current_user.id],
        order_by=[StarFolder.is_default.desc(), StarFolder.id.asc()],
    )

    # 统计每个收藏夹中不同资源类型的数量
    folder_stats = []
    for folder in folders:
        # 统计该收藏夹中各种资源类型的数量
        stats_query = (
            select(Star.resource_type, func.count(Star.id).label("count"))
            .where(Star.user_id == current_user.id, any_(Star.folder_ids) == folder.id)
            .group_by(Star.resource_type)
        )

        stats_result = (await db_session.execute(stats_query)).all()

        resource_counts = {"QUESTION": 0, "ANSWER": 0, "PROTOCOL": 0}

        for resource_type, scount in stats_result:
            if resource_type == StarResourceType.QUESTION:
                resource_counts["QUESTION"] = scount
            elif resource_type == StarResourceType.ANSWER:
                resource_counts["ANSWER"] = scount
            elif resource_type == StarResourceType.PROTOCOL:
                resource_counts["PROTOCOL"] = scount

        folder_data = folder.as_dict()
        folder_data["resource_counts"] = resource_counts
        folder_data["total_count"] = sum(resource_counts.values())
        folder_stats.append(folder_data)

    return {"folders": folder_stats}


@router.post("/folders")
async def create_star_folder(
    params: StarFolderCreateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    """创建收藏夹"""
    # 检查同名收藏夹
    existing_folder = await StarFolder.find_by(
        db_session,
        [StarFolder.user_id == current_user.id, StarFolder.name == params.name],
    )
    if existing_folder:
        raise HTTPException(status_code=400, detail="folder name already exists")

    has_default_folder = await StarFolder.find_by(
        db_session,
        [
            StarFolder.user_id == current_user.id,
            StarFolder.is_default.is_(True),
        ],
    )

    folder = StarFolder(
        user_id=current_user.id,
        name=params.name,
        is_default=(
            has_default_folder is None and _is_default_folder_name(params.name)
        ),
    )
    db_session.add(folder)
    await db_session.commit()
    return folder


@router.put("/folders/{folder_id}")
async def update_star_folder(
    folder_id: int,
    params: StarFolderUpdateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    """更新收藏夹"""
    folder = await StarFolder.find(db_session, id=folder_id)
    if folder.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")

    if folder.is_default and params.name != folder.name:
        raise HTTPException(
            status_code=400,
            detail="default folder cannot be renamed",
        )

    # 检查同名收藏夹（排除当前收藏夹）
    existing_folder = await StarFolder.find_by(
        db_session,
        [
            StarFolder.user_id == current_user.id,
            StarFolder.name == params.name,
            StarFolder.id != folder_id,
        ],
    )
    if existing_folder:
        raise HTTPException(status_code=400, detail="folder name already exists")

    folder.name = params.name
    await db_session.commit()
    return folder


@router.delete("/folders/{folder_id}")
async def delete_star_folder(
    folder_id: int,
    current_user: CurrentUser,
    db_session: DBSession,
):
    """删除收藏夹"""
    folder = await StarFolder.find(db_session, id=folder_id)
    if folder.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")
    if folder.is_default:
        raise HTTPException(status_code=400, detail="default folder cannot be deleted")

    # 删除收藏夹时，需要更新相关收藏的 folder_ids
    stars_in_folder = await Star.all(
        db_session,
        where_conditions=[
            Star.user_id == current_user.id,
            folder_id == any_(Star.folder_ids),
        ],
    )

    default_folder: StarFolder | None = None
    for star in stars_in_folder:
        if folder_id in star.folder_ids:
            star.folder_ids = [fid for fid in star.folder_ids if fid != folder_id]
            if not star.folder_ids:
                if default_folder is None:
                    default_folder = await _get_or_create_default_star_folder(
                        db_session, current_user
                    )
                star.folder_ids = [default_folder.id]

    await db_session.execute(delete(StarFolder).where(StarFolder.id == folder_id))
    await db_session.commit()
    return {"message": "folder deleted successfully"}


# Star 接口
@router.get("")
async def get_stars(
    db_session: DBSession,
    current_user: CurrentUser,
    folder_id: int | None = None,
    resource_type: StarResourceType | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """获取收藏列表，包含资源简介"""
    where_conditions = [Star.user_id == current_user.id]

    if folder_id is not None:
        where_conditions.append(any_(Star.folder_ids) == folder_id)

    if resource_type is not None:
        where_conditions.append(Star.resource_type == resource_type)

    total_count = await Star.count(db_session, where_conditions)
    stars = await Star.all(
        db_session,
        where_conditions=where_conditions,
        page=page,
        page_size=page_size,
        order_by=[Star.created_at.desc()],
    )

    # 获取资源简介
    enriched_stars = []
    for star in stars:
        star_data = star.as_dict()

        # 根据资源类型获取简介
        if star.resource_type == StarResourceType.QUESTION:
            question = await Question.find_by(
                db_session,
                [Question.id == star.resource_id],
            )
            if question:
                star_data["resource_summary"] = question.title
                protocol = await Protocol.find_by(
                    db_session,
                    [
                        Protocol.id == question.protocol_id,
                        Protocol.deleted_at.is_(None),
                    ],
                )
                await _attach_star_route_info(
                    db_session,
                    star_data,
                    protocol,
                    question_id=question.id,
                )
            else:
                star_data["resource_summary"] = "question deleted"

        elif star.resource_type == StarResourceType.ANSWER:
            answer = await Answer.find_by(
                db_session,
                [Answer.id == star.resource_id],
            )
            if answer:
                # 截取前100个字符作为简介
                content = (
                    answer.content[:100] + "..."
                    if len(answer.content) > 100
                    else answer.content
                )
                star_data["resource_summary"] = content
                question = await Question.find_by(
                    db_session,
                    [Question.id == answer.question_id],
                )
                protocol = None
                if question is not None:
                    protocol = await Protocol.find_by(
                        db_session,
                        [
                            Protocol.id == question.protocol_id,
                            Protocol.deleted_at.is_(None),
                        ],
                    )
                await _attach_star_route_info(
                    db_session,
                    star_data,
                    protocol,
                    question_id=question.id if question is not None else None,
                )
            else:
                star_data["resource_summary"] = "Answer deleted"

        elif star.resource_type == StarResourceType.PROTOCOL:
            protocol = await Protocol.find_by(
                db_session,
                [
                    Protocol.id == star.resource_id,
                    Protocol.deleted_at.is_(None),
                ],
            )
            if protocol:
                star_data["resource_summary"] = protocol.name
                await _attach_star_route_info(db_session, star_data, protocol)
            else:
                star_data["resource_summary"] = "Protocol deleted"

        enriched_stars.append(star_data)

    return {"stars": enriched_stars, "total_count": total_count}


@router.post("")
async def create_star(
    params: StarCreateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    """创建收藏"""
    # 检查是否已经收藏过
    existing_star = await Star.find_by(
        db_session,
        [
            Star.user_id == current_user.id,
            Star.resource_type == params.resource_type,
            Star.resource_id == params.resource_id,
        ],
    )
    if existing_star:
        raise HTTPException(status_code=400, detail="already starred")

    # 验证资源是否存在
    if params.resource_type == StarResourceType.QUESTION:
        resource = await Question.find_by(
            db_session,
            [Question.id == params.resource_id],
        )
    elif params.resource_type == StarResourceType.ANSWER:
        resource = await Answer.find_by(
            db_session,
            [Answer.id == params.resource_id],
        )
    elif params.resource_type == StarResourceType.PROTOCOL:
        resource = await Protocol.find_by(
            db_session,
            [
                Protocol.id == params.resource_id,
                Protocol.deleted_at.is_(None),
            ],
        )
    else:
        raise HTTPException(status_code=400, detail="invalid resource type")

    if resource is None:
        raise HTTPException(status_code=404, detail="resource not found")

    protocol: Protocol | None = None
    if type(resource) is Protocol:
        protocol = resource
    elif type(resource) is Question:
        protocol = await Protocol.find(db_session, id=resource.protocol_id)
    elif type(resource) is Answer:
        question = await Question.find(db_session, id=resource.question_id)
        protocol = await Protocol.find(db_session, id=question.protocol_id)
    if protocol is None:
        raise HTTPException(status_code=400, detail="invalid resource type")

    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
    )

    target_folder_ids = list(dict.fromkeys(params.folder_ids or []))
    if not target_folder_ids:
        default_folder = await _get_or_create_default_star_folder(db_session, current_user)
        target_folder_ids = [default_folder.id]

    # 验证收藏夹是否属于当前用户
    folders = await StarFolder.all(
        db_session,
        where_conditions=[StarFolder.id.in_(target_folder_ids)],
        page=1,
        page_size=max(len(target_folder_ids), 1),
        order_by=[StarFolder.id.asc()],
    )
    valid_folder_ids = {
        folder.id for folder in folders if folder.user_id == current_user.id
    }
    if len(valid_folder_ids) != len(set(target_folder_ids)):
        raise HTTPException(
            status_code=403,
            detail="some folders not found or permission denied",
        )

    star = Star(
        user_id=current_user.id,
        resource_type=params.resource_type,
        resource_id=params.resource_id,
        folder_ids=target_folder_ids,
    )
    db_session.add(star)
    await db_session.flush()

    resource.stars_count = await Star.count(
        db_session,
        where_conditions=[
            Star.resource_type == params.resource_type,
            Star.resource_id == params.resource_id,
        ],
    )
    await db_session.commit()
    return star


@router.put("/{star_id}")
async def update_star(
    star_id: int,
    params: StarUpdateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    """更新收藏"""
    star = await Star.find(db_session, id=star_id)
    if star.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")

    next_folder_ids: list[int] | None = None
    if params.folder_ids is not None:
        next_folder_ids = list(dict.fromkeys(params.folder_ids))
        if not next_folder_ids:
            default_folder = await _get_or_create_default_star_folder(
                db_session, current_user
            )
            next_folder_ids = [default_folder.id]

        folders = await StarFolder.all(
            db_session,
            where_conditions=[StarFolder.id.in_(next_folder_ids)],
            page=1,
            page_size=max(len(next_folder_ids), 1),
            order_by=[StarFolder.id.asc()],
        )
        valid_folder_ids = {
            folder.id for folder in folders if folder.user_id == current_user.id
        }
        if len(valid_folder_ids) != len(set(next_folder_ids)):
            raise HTTPException(
                status_code=403,
                detail="some folders not found or permission denied",
            )

    if next_folder_ids is not None:
        star.folder_ids = next_folder_ids

    await db_session.commit()
    return star


@router.delete("/{star_id}")
async def delete_star(
    star_id: int,
    current_user: CurrentUser,
    db_session: DBSession,
):
    """删除收藏"""
    star = await Star.find(db_session, id=star_id)
    if star.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")

    await db_session.execute(delete(Star).where(Star.id == star_id))
    await db_session.flush()

    if star.resource_type == StarResourceType.QUESTION:
        resource = await Question.find_by(
            db_session,
            [Question.id == star.resource_id],
        )
    elif star.resource_type == StarResourceType.ANSWER:
        resource = await Answer.find_by(
            db_session,
            [Answer.id == star.resource_id],
        )
    elif star.resource_type == StarResourceType.PROTOCOL:
        resource = await Protocol.find_by(
            db_session,
            [
                Protocol.id == star.resource_id,
            ],
        )
    else:
        raise HTTPException(status_code=400, detail="invalid resource type")

    if resource is not None:
        resource.stars_count = await Star.count(
            db_session,
            where_conditions=[
                Star.resource_type == star.resource_type,
                Star.resource_id == star.resource_id,
            ],
        )

    await db_session.commit()
    return {"message": "star deleted successfully"}


@router.get("/users")
async def get_star_users(
    resource_type: StarResourceType,
    resource_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
):
    """获取某个资源被收藏的用户列表，返回用户 id、用户名/姓名、头像"""
    # 权限校验：根据资源找到所属 Protocol，再校验可读权限
    resource = None
    if resource_type == StarResourceType.QUESTION:
        resource = await Question.find_by(db_session, [Question.id == resource_id])
        if resource is None:
            raise HTTPException(status_code=404, detail="resource not found")
        protocol = await Protocol.find(db_session, id=resource.protocol_id)
    elif resource_type == StarResourceType.ANSWER:
        resource = await Answer.find_by(db_session, [Answer.id == resource_id])
        if resource is None:
            raise HTTPException(status_code=404, detail="resource not found")
        question = await Question.find(db_session, id=resource.question_id)
        protocol = await Protocol.find(db_session, id=question.protocol_id)
    elif resource_type == StarResourceType.PROTOCOL:
        protocol = await Protocol.find_by(
            db_session, [Protocol.id == resource_id, Protocol.deleted_at.is_(None)]
        )
        if protocol is None:
            raise HTTPException(status_code=404, detail="resource not found")
    else:
        raise HTTPException(status_code=400, detail="invalid resource type")

    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session, project=project, user=current_user, action="read_protocol"
    )

    total_count = await Star.count(
        db_session,
        [Star.resource_type == resource_type, Star.resource_id == resource_id],
    )

    stmt = (
        select(User)
        .options(selectinload(User.avatar_attachment))
        .join(Star, Star.user_id == User.id)
        .where(Star.resource_type == resource_type, Star.resource_id == resource_id)
        .order_by(Star.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    result = (await db_session.execute(stmt)).scalars().all()

    for u in result:
        await u.load_avatar_attachment()
    users = [u.as_dict(only=["id", "username", "name", "avatar_url"]) for u in result]

    return {"users": users, "total_count": total_count}
