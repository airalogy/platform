"""Discover Platform research capabilities without duplicating their sources."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.database import DBSession
from app.models.project import Project
from app.routers.depends import CurrentUser
from app.services.access_control import (
    resolve_resource_access,
    resolve_structured_access,
)
from app.services.research_capabilities import research_capability_catalog
from app.services.research_runtime import require_research_capability

router = APIRouter(prefix="/research-capabilities", tags=["research-capabilities"])


@router.get("")
async def list_research_capabilities(
    project_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    project = await Project.find_by(
        db_session, [Project.id == project_id, Project.deleted_at.is_(None)]
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await require_research_capability(
        db_session,
        user=current_user,
        project=project,
        capability="research.read",
    )
    access = await resolve_structured_access(
        db_session,
        current_user.id,
        project.lab_id,
        project,
        include_legacy=True,
    )
    catalog = await research_capability_catalog(
        db_session,
        project=project,
        include_resources=access.allows("resource.read"),
        include_instruments=access.allows("resource.read"),
        include_services=access.allows("research.service.use"),
        include_compute=access.allows("research.compute.use"),
    )
    instruments = []
    for item in catalog["instruments"]:
        metadata = item.metadata or {}
        resource_access = await resolve_resource_access(
            db_session,
            current_user.id,
            project.lab_id,
            resource_type_id=UUID(str(metadata["resource_type_id"])),
            resource_id=UUID(str(metadata["resource_id"])),
        )
        if resource_access.allows("equipment.book"):
            instruments.append(item.payload())
    return {
        "project_id": str(project.id),
        "lab_id": str(project.lab_id),
        "protocols": [item.payload() for item in catalog["protocols"]],
        "tools": [item.payload() for item in catalog["tools"]],
        "human_work": [item.payload() for item in catalog["human_work"]],
        "resources": [item.payload() for item in catalog["resources"]],
        "instruments": instruments,
        "services": [item.payload() for item in catalog["services"]],
        "compute": [item.payload() for item in catalog["compute"]],
    }
