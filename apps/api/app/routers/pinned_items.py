from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.database import DBSession
from app.models.lab import Lab
from app.models.pinned_item import PinnedItem, PinnedResourceType
from app.models.project import Project
from app.models.protocol import Protocol
from app.routers.depends import CurrentUser, get_current_user
from app.routers.permission import check_user_permission

router = APIRouter(
    prefix="/pinned_items",
    tags=["pinned_items"],
    dependencies=[Depends(get_current_user)],
)

# Maximum number of pinned items per user
MAX_PINNED_ITEMS = 10


# Pydantic models
class PinnedItemCreateParams(BaseModel):
    resource_type: PinnedResourceType
    resource_id: UUID


class PinnedItemReorderParams(BaseModel):
    pinned_item_ids: list[int]


# GET /pinned_items - Get user's pinned items
@router.get("")
async def get_pinned_items(
    db_session: DBSession,
    current_user: CurrentUser,
):
    """
    获取当前用户的置顶项列表
    返回置顶的 Labs, Projects, Protocols 及其完整信息
    按照 sort_order 排序
    """
    # Get pinned items
    pinned_items = await PinnedItem.all(
        db_session,
        where_conditions=[PinnedItem.user_id == current_user.id],
        order_by=[PinnedItem.sort_order.asc()],
    )

    if not pinned_items:
        return {"items": [], "total": 0}

    # Group pinned items by resource_type
    grouped_items: dict[PinnedResourceType, list[UUID]] = {}
    for item in pinned_items:
        resource_type = PinnedResourceType(item.resource_type)
        if resource_type not in grouped_items:
            grouped_items[resource_type] = []
        grouped_items[resource_type].append(item.resource_id)

    # Batch load resources by type
    resources_map: dict[UUID, Any] = {}

    # Load Labs
    if PinnedResourceType.LAB in grouped_items:
        lab_ids = grouped_items[PinnedResourceType.LAB]
        stmt = (
            select(Lab)
            .where(Lab.id.in_(lab_ids))
            .options(selectinload(Lab.logo_attachment))
        )
        result = await db_session.execute(stmt)
        labs = result.scalars().all()
        for lab in labs:
            await lab.load_logo_attachment(db_session)
            resources_map[lab.id] = lab.as_dict()

    # Load Projects
    if PinnedResourceType.PROJECT in grouped_items:
        project_ids = grouped_items[PinnedResourceType.PROJECT]
        stmt = (
            select(Project)
            .where(Project.id.in_(project_ids))
            .options(selectinload(Project.lab))
        )
        result = await db_session.execute(stmt)
        projects = result.scalars().all()
        valid_projects = [project for project in projects if project.deleted_at is None]
        child_counts_map: dict[UUID, int] = {}
        if valid_projects:
            child_counts_result = await db_session.execute(
                select(Project.parent_project_id, func.count(Project.id))
                .where(
                    Project.parent_project_id.in_([project.id for project in valid_projects]),
                    Project.deleted_at.is_(None),
                )
                .group_by(Project.parent_project_id)
            )
            child_counts_map = {
                parent_project_id: children_count
                for parent_project_id, children_count in child_counts_result
                if parent_project_id is not None
            }

        parent_projects_map: dict[UUID, Project] = {}
        parent_project_ids = list(
            {
                project.parent_project_id
                for project in valid_projects
                if project.parent_project_id is not None
            }
        )
        if parent_project_ids:
            parent_projects_result = await db_session.execute(
                select(Project).where(
                    Project.id.in_(parent_project_ids),
                    Project.deleted_at.is_(None),
                )
            )
            parent_projects_map = {
                project.id: project for project in parent_projects_result.scalars().all()
            }

        for project in projects:
            if project.deleted_at is not None:
                continue

            parent_project = (
                parent_projects_map.get(project.parent_project_id)
                if project.parent_project_id is not None
                else None
            )
            children_count = child_counts_map.get(project.id, 0)
            resources_map[project.id] = project.as_dict(
                lab_name=project.lab.name,
                lab_uid=project.lab.uid,
                parent_project_uid=parent_project.uid if parent_project else None,
                parent_project_name=parent_project.name if parent_project else None,
                children_count=children_count,
                has_children=children_count > 0,
                depth=1 if project.parent_project_id else 0,
            )

    # Load Protocols
    if PinnedResourceType.PROTOCOL in grouped_items:
        protocol_ids = grouped_items[PinnedResourceType.PROTOCOL]
        stmt = (
            select(Protocol)
            .where(Protocol.id.in_(protocol_ids))
            .options(selectinload(Protocol.project).selectinload(Project.lab))
        )
        result = await db_session.execute(stmt)
        protocols = result.scalars().all()
        for protocol in protocols:
            if protocol.deleted_at is not None:
                continue

            protocol.lab_uid = protocol.project.lab.uid
            protocol.project_uid = protocol.project.uid
            resources_map[protocol.id] = protocol.as_dict(
                project_uid=protocol.project.uid,
                lab_uid=protocol.project.lab.uid,
            )

    # Build response maintaining original sort order
    response = []
    for pinned_item in pinned_items:
        resource = resources_map.get(pinned_item.resource_id)
        if resource:
            response.append(
                {
                    "id": pinned_item.id,
                    "resource_type": pinned_item.resource_type,
                    "resource_id": pinned_item.resource_id,
                    "sort_order": pinned_item.sort_order,
                    "created_at": pinned_item.created_at,
                    "resource": resource,
                }
            )
        else:
            await db_session.delete(pinned_item)

    if len(response) < len(pinned_items):
        await db_session.commit()

    return {"items": response, "total": len(response)}


# POST /pinned_items - Pin a new item
@router.post("")
async def create_pinned_item(
    params: PinnedItemCreateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    """
    置顶一个 Lab/Project/Protocol
    用户必须有权限访问该资源
    最多置顶 10 个项目
    """

    """Get resource details (name, uid, etc.)"""
    if params.resource_type == PinnedResourceType.LAB:
        resource = await Lab.find(db_session, params.resource_id)
    elif params.resource_type == PinnedResourceType.PROJECT:
        resource = await Project.find(db_session, params.resource_id)
        await check_user_permission(
            db_session, resource, current_user, action="read_project"
        )

    elif params.resource_type == PinnedResourceType.PROTOCOL:
        resource = await Protocol.find(db_session, params.resource_id)
        project = await Project.find(db_session, resource.project_id)
        await check_user_permission(
            db_session, project, current_user, action="read_protocol", protocol=resource
        )

    # Check if already pinned
    existing = await PinnedItem.exists(
        db_session,
        where_conditions=[
            PinnedItem.user_id == current_user.id,
            PinnedItem.resource_type == params.resource_type,
            PinnedItem.resource_id == params.resource_id,
        ],
    )

    if existing:
        raise HTTPException(status_code=409, detail="This resource is already pinned")

    # Check if user has reached the limit
    count = await PinnedItem.count(
        db_session,
        where_conditions=[PinnedItem.user_id == current_user.id],
    )

    if count >= MAX_PINNED_ITEMS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum pinned items limit reached ({MAX_PINNED_ITEMS})",
        )

    if count > 0:
        # Get the next sort_order
        items = await PinnedItem.all(
            db_session,
            where_conditions=[PinnedItem.user_id == current_user.id],
            order_by=[PinnedItem.sort_order.desc()],
            page=1,
            page_size=1,
        )
        max_order = items[0]
        next_order = (max_order.sort_order or 0) + 1
    else:
        next_order = 1

    # Create pinned item
    pinned_item = PinnedItem(
        user_id=current_user.id,
        resource_type=params.resource_type,
        resource_id=params.resource_id,
        sort_order=next_order,
    )
    db_session.add(pinned_item)
    await db_session.commit()

    return {"success": True}


# DELETE /pinned_items/{pinned_id} - Unpin an item
@router.delete("/{pinned_id}")
async def delete_pinned_item(
    pinned_id: int,
    current_user: CurrentUser,
    db_session: DBSession,
):
    """
    取消置顶一个项目
    只能取消自己置顶的项目
    """
    # Get the pinned item
    pinned_item = await PinnedItem.find_by(
        db_session, [PinnedItem.id == pinned_id, PinnedItem.user_id == current_user.id]
    )

    if not pinned_item:
        raise HTTPException(status_code=404, detail="Pinned item not found")

    # Delete the pinned item
    await db_session.delete(pinned_item)

    await db_session.commit()

    return {"success": True}


# PUT /pinned_items/reorder - Reorder pinned items
@router.put("/reorder")
async def reorder_pinned_items(
    params: PinnedItemReorderParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    """
    重新排序置顶项
    传入排序后的 pinned_item_ids 数组
    """
    # Get all pinned items for the user
    pinned_items = await PinnedItem.all(
        db_session,
        where_conditions=[
            PinnedItem.user_id == current_user.id,
            PinnedItem.id.in_(params.pinned_item_ids),
        ],
        page_size=len(params.pinned_item_ids),
    )

    # Verify all IDs exist and belong to the user
    if len(pinned_items) != len(params.pinned_item_ids):
        raise HTTPException(
            status_code=400, detail="Some pinned items not found or don't belong to you"
        )

    # Create a mapping of id to item
    item_map = {item.id: item for item in pinned_items}

    # Update sort_order based on array position
    for index, pinned_id in enumerate(params.pinned_item_ids):
        if pinned_id in item_map:
            item_map[pinned_id].sort_order = index + 1

    await db_session.commit()

    return {"success": True}
