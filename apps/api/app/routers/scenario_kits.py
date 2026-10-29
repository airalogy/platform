"""Built-in kit catalog and deterministic installation/application endpoints."""

import csv
import io
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.database import DBSession
from app.models.scenario_kit import ScenarioKitEvent
from app.routers.depends import CurrentUser
from app.routers.resources import (
    ResourceParams,
    _can_read_resource,
    _resource,
    create_resource,
)
from app.services import scenario_kits as kits
from app.services.record_imports import import_fields
from app.services.scenario_catalog import analysis_recipe, availability

router = APIRouter(prefix="/labs/{lab_id}", tags=["scenario-kits"])


@router.get("/scenario-kits")
async def lab_catalog(
    lab_id: UUID, db_session: DBSession, current_user: CurrentUser, response: Response
):
    response.headers["Cache-Control"] = "private, no-store"
    return await kits.directory(db_session, current_user, lab_id)


@router.post("/scenario-kits/preview")
async def lab_preview(
    lab_id: UUID,
    params: kits.KitRequest,
    db_session: DBSession,
    current_user: CurrentUser,
):
    return await kits.preview(db_session, current_user, lab_id, None, params)


@router.post("/scenario-kits/confirm")
async def lab_confirm(
    lab_id: UUID,
    params: kits.KitConfirm,
    db_session: DBSession,
    current_user: CurrentUser,
):
    return await kits.confirm(db_session, current_user, lab_id, None, params)


@router.get("/projects/{project_id}/scenario-kits")
async def project_catalog(
    lab_id: UUID,
    project_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    return await kits.directory(db_session, current_user, lab_id, project_id)


@router.post("/projects/{project_id}/scenario-kits/preview")
async def project_preview(
    lab_id: UUID,
    project_id: UUID,
    params: kits.KitRequest,
    db_session: DBSession,
    current_user: CurrentUser,
):
    return await kits.preview(db_session, current_user, lab_id, project_id, params)


@router.post("/projects/{project_id}/scenario-kits/confirm")
async def project_confirm(
    lab_id: UUID,
    project_id: UUID,
    params: kits.KitConfirm,
    db_session: DBSession,
    current_user: CurrentUser,
):
    return await kits.confirm(db_session, current_user, lab_id, project_id, params)


async def active_application(db, user, lab_id, project_id, kit_id, *, lock=False):
    await kits.context(db, user, lab_id, project_id, lock=lock)
    app = await kits.application(db, project_id, kit_id)
    installed = await kits.installation(db, lab_id, kit_id)
    if not app or not app.enabled or not installed or not installed.enabled:
        raise HTTPException(409, "Scenario kit is not active")
    if availability(
        app.manifest,
        enabled_modules=kits.enabled_modules(),
        platform_version=kits.resolve_build_info().version,
    ):
        raise HTTPException(409, "Required scenario modules are unavailable")
    return app


class SampleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kit_id: str = Field(max_length=128)
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=128)
    source: str | None = Field(default=None, max_length=1000)
    storage: str | None = Field(default=None, max_length=1000)


@router.post("/projects/{project_id}/scenario-kits/samples")
async def register_sample(
    lab_id: UUID,
    project_id: UUID,
    params: SampleCreate,
    db_session: DBSession,
    current_user: CurrentUser,
):
    await active_application(
        db_session, current_user, lab_id, project_id, params.kit_id, lock=True
    )
    shared = await kits.shared_component(db_session, lab_id)
    if not shared:
        raise HTTPException(409, "Shared sample definition is unavailable")
    return await create_resource(
        lab_id,
        ResourceParams(
            resource_type_id=shared.resource_type_id,
            name=params.name,
            code=params.code,
            data={
                "category": params.category,
                "source": params.source,
                "storage": params.storage,
            },
            reason="Registered through the sample scenario kit",
        ),
        current_user,
        db_session,
    )


class SampleTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kit_id: str = Field(max_length=128)
    protocol_id: UUID
    sample_ids: list[UUID] = Field(min_length=1, max_length=200)


@router.post("/projects/{project_id}/scenario-kits/sample-template")
async def sample_template(
    lab_id: UUID,
    project_id: UUID,
    params: SampleTemplate,
    db_session: DBSession,
    current_user: CurrentUser,
):
    from app.routers.records import _import_context

    app = await active_application(
        db_session, current_user, lab_id, project_id, params.kit_id
    )
    if not any(asset["protocol_id"] == str(params.protocol_id) for asset in app.assets):
        raise HTTPException(404, "Kit Protocol not found")
    _, _, version = await _import_context(params.protocol_id, db_session, current_user)
    fields = import_fields(version.json_schema)
    references = (version.fields or {}).get("vars") or []
    if not any(
        field.get("name") == "sample"
        and "ResourceRef" in field.get("type_annotation", "")
        for field in references
    ):
        raise HTTPException(
            409, "The customized Protocol no longer has a ResourceRef sample field"
        )
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([f"var.{field['id']}" for field in fields])
    for sample_id in dict.fromkeys(params.sample_ids):
        sample = await _resource(db_session, lab_id, sample_id)
        if not await _can_read_resource(db_session, current_user.id, sample):
            raise HTTPException(404, "Sample not found")
        shared = await kits.shared_component(db_session, lab_id)
        if (
            not shared
            or sample.resource_type_id != shared.resource_type_id
            or sample.status != "active"
        ):
            raise HTTPException(
                422, "Select active samples belonging to this kit's shared type"
            )
        reference = json.dumps(
            {"id": str(sample.id), "entity": "sample"}, ensure_ascii=False
        )
        writer.writerow(
            [reference if field["id"] == "sample" else "" for field in fields]
        )
    return {
        "csv": output.getvalue(),
        "protocol_version": version.version,
        "row_count": len(set(params.sample_ids)),
    }


@router.get("/projects/{project_id}/scenario-kits/analysis-recipe")
async def suggested_analysis_recipe(
    lab_id: UUID, project_id: UUID, db_session: DBSession, current_user: CurrentUser
):
    await kits.context(db_session, current_user, lab_id, project_id)
    return {"recipe": analysis_recipe()}


async def history(db, user, lab_id, project_id=None):
    await kits.context(db, user, lab_id, project_id, manage=True)
    stmt = select(ScenarioKitEvent).where(ScenarioKitEvent.lab_id == lab_id)
    stmt = (
        stmt.where(ScenarioKitEvent.project_id == project_id)
        if project_id
        else stmt.where(ScenarioKitEvent.project_id.is_(None))
    )
    rows = (
        await db.scalars(stmt.order_by(ScenarioKitEvent.created_at.desc()).limit(200))
    ).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "operation": row.operation,
                "kit_id": row.snapshot["preview"]["request"]["kit_id"],
                "version": row.snapshot["preview"]["request"]["version"],
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.get("/scenario-kits/history")
async def lab_history(
    lab_id: UUID, db_session: DBSession, current_user: CurrentUser, response: Response
):
    response.headers["Cache-Control"] = "private, no-store"
    return await history(db_session, current_user, lab_id)


@router.get("/projects/{project_id}/scenario-kits/history")
async def project_history(
    lab_id: UUID,
    project_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    return await history(db_session, current_user, lab_id, project_id)
