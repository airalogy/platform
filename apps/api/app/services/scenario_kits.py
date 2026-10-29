"""Deterministic, permission-bound application of release-bundled kits."""

from __future__ import annotations

import logging
import tempfile
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.build_info import resolve_build_info
from app.config import config
from app.libs.file_storage import delete_file
from app.libs.protocol_agent import protocol_exec
from app.libs.text_splitter import text_to_chunks, text_to_words
from app.models.analysis import AnalysisRun
from app.models.embedding import Embedding, EmbeddingResourceType
from app.models.lab import Lab, LabRole, LabUser
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.research import ResearchRun, ResearchTask
from app.models.resource import ResourceType, ResourceTypeRevision
from app.models.scenario_kit import (
    LabScenarioKit,
    ScenarioKitApplication,
    ScenarioKitEvent,
    ScenarioSharedComponent,
)
from app.services.access_control import (
    resolve_resource_access,
    resolve_structured_access,
)
from app.services.scenario_catalog import (
    availability,
    catalog,
    digest,
    manifest,
    template_files,
)

AUDIENCE = "airalogy.scenario-kit.preview.v1"
logger = logging.getLogger(__name__)


class KitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kit_id: str = Field(min_length=1, max_length=128)
    version: str = Field(default="1.1.0", pattern=r"^\d+\.\d+\.\d+$")
    action: Literal["enable", "disable", "apply", "deactivate"]
    strategy: Literal["keep", "new_copy"] = "keep"


class KitConfirm(KitRequest):
    preview_token: str = Field(min_length=1, max_length=8000)
    request_id: UUID


def enabled_modules():
    return set(
        filter(None, (part.strip() for part in config.SCENARIO_KIT_MODULES.split(",")))
    )


async def context(db, user, lab_id, project_id=None, *, manage=False, lock=False):
    stmt = select(Lab).where(Lab.id == lab_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    lab = await db.scalar(stmt)
    membership = await db.scalar(
        select(LabUser)
        .where(LabUser.lab_id == lab_id, LabUser.user_id == user.id)
        .execution_options(populate_existing=True)
    )
    if lab is None or membership is None:
        raise HTTPException(404, "Lab not found")
    project = None
    if project_id:
        project = await db.get(Project, project_id, populate_existing=True)
        if (
            project is None
            or project.lab_id != lab_id
            or project.deleted_at is not None
        ):
            raise HTTPException(404, "Project not found")
        access = await resolve_structured_access(db, user.id, lab_id, project)
        required = (
            {"project.manage", "protocol.create"} if manage else {"protocol.read"}
        )
        if not required.issubset(access.capabilities):
            raise HTTPException(403, "Project access is required")
    elif manage and membership.role not in (LabRole.OWNER, LabRole.MANAGER):
        raise HTTPException(403, "Lab Owner or Manager is required")
    return lab, project


async def installation(db, lab_id, kit_id):
    return await db.scalar(
        select(LabScenarioKit)
        .where(LabScenarioKit.lab_id == lab_id, LabScenarioKit.kit_id == kit_id)
        .execution_options(populate_existing=True)
    )


async def application(db, project_id, kit_id):
    return await db.scalar(
        select(ScenarioKitApplication)
        .where(
            ScenarioKitApplication.project_id == project_id,
            ScenarioKitApplication.kit_id == kit_id,
        )
        .execution_options(populate_existing=True)
    )


async def shared_component(db, lab_id):
    return await db.scalar(
        select(ScenarioSharedComponent).where(
            ScenarioSharedComponent.lab_id == lab_id,
            ScenarioSharedComponent.component_id == "airalogy.sample.v1",
        )
    )


async def describe_assets(db, user, project, app):
    if app is None:
        return []
    result = []
    for asset in app.assets:
        protocol = await db.get(
            Protocol, UUID(asset["protocol_id"]), populate_existing=True
        )
        if protocol is None or protocol.project_id != project.id:
            continue
        access = await resolve_structured_access(
            db, user.id, project.lab_id, project, protocol
        )
        if "protocol.read" not in access.capabilities:
            # Application metadata must not disclose a restricted template copy.
            continue
        version = await db.scalar(
            select(ProtocolVersion).where(
                ProtocolVersion.protocol_id == protocol.id,
                ProtocolVersion.version == protocol.latest_version,
            )
        )
        result.append(
            {
                **asset,
                "available": version is not None and protocol.deleted_at is None,
                "can_record": "record.create" in access.capabilities,
                "can_read_records": "record.read" in access.capabilities,
                "name": protocol.name,
                "uid": protocol.uid,
                "latest_version": protocol.latest_version,
                "current_snapshot_digest": version_digest(version) if version else None,
                "changed": version is None
                or version_digest(version) != asset["snapshot_digest"],
            }
        )
    return result


def version_digest(version):
    return digest(
        {
            "version": version.version,
            "schema": version.json_schema,
            "aimd": version.aimd,
            "fields": version.fields,
            "metadata": version.meta_data,
        }
    )


async def directory(db, user, lab_id, project_id=None):
    lab, project = await context(db, user, lab_id, project_id)
    try:
        await context(db, user, lab_id, project_id, manage=True)
        can_manage = True
    except HTTPException:
        can_manage = False
    values = []
    for value in catalog():
        installed = await installation(db, lab_id, value["id"])
        applied = await application(db, project_id, value["id"]) if project_id else None
        assets = await describe_assets(db, user, project, applied) if project else []
        values.append(
            {
                **value,
                "unavailable_reasons": availability(
                    value,
                    enabled_modules=enabled_modules(),
                    platform_version=resolve_build_info().version,
                ),
                "installation": {
                    "version": installed.version,
                    "enabled": installed.enabled,
                    "revision": installed.revision,
                }
                if installed
                else None,
                "application": {
                    "id": str(applied.id),
                    "version": applied.version,
                    "enabled": applied.enabled,
                    "revision": applied.revision,
                    "assets": assets,
                }
                if applied
                else None,
            }
        )
    shared = await shared_component(db, lab_id)
    sample_access = await resolve_resource_access(
        db,
        user.id,
        lab_id,
        resource_type_id=shared.resource_type_id if shared else None,
    )
    return {
        "kits": values,
        "can_manage": can_manage,
        "can_register_samples": "resource.operate" in sample_access.capabilities,
        "lab_id": str(lab.id),
        "lab_name": lab.name,
        "project_id": str(project.id) if project else None,
        "project_name": project.name if project else None,
    }


async def active_work(db, project_id):
    # Conservative project-level guard: never discard a dependency mid-run.
    research = await db.scalar(
        select(ResearchRun.id)
        .join(ResearchTask, ResearchTask.id == ResearchRun.task_id)
        .where(
            ResearchTask.project_id == project_id,
            ResearchRun.status.notin_(["completed", "failed", "cancelled"]),
        )
        .limit(1)
    )
    analysis = await db.scalar(
        select(AnalysisRun.id)
        .where(
            AnalysisRun.project_id == project_id,
            AnalysisRun.status.in_(["pending", "running"]),
        )
        .limit(1)
    )
    return bool(research or analysis)


async def plan(db, user, lab_id, project_id, request):
    lab, project = await context(db, user, lab_id, project_id, manage=True)
    if bool(project_id) != (request.action in {"apply", "deactivate"}):
        raise HTTPException(422, "Operation does not match the target scope")
    try:
        value = manifest(request.kit_id, request.version)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    installed = await installation(db, lab_id, request.kit_id)
    app = await application(db, project_id, request.kit_id) if project_id else None
    if request.action == "deactivate" and app is None:
        raise HTTPException(409, "Scenario kit has not been applied to this project")
    blockers = []
    if request.action in {"enable", "apply"}:
        blockers += availability(
            value,
            enabled_modules=enabled_modules(),
            platform_version=resolve_build_info().version,
        )
    if request.action == "apply" and (
        not installed or not installed.enabled or installed.version != request.version
    ):
        blockers.append("lab_kit_not_enabled_at_version")
    if request.action == "disable" and installed:
        dependents = await db.scalar(
            select(ScenarioKitApplication.id)
            .where(
                ScenarioKitApplication.installation_id == installed.id,
                ScenarioKitApplication.enabled.is_(True),
            )
            .limit(1)
        )
        if dependents:
            blockers.append("active_project_applications")
    if request.action == "deactivate" and app and await active_work(db, project_id):
        blockers.append("active_project_work")
    shared = await shared_component(db, lab_id)
    if request.action == "apply" and not shared:
        collision = await db.scalar(
            select(ResourceType.id).where(
                ResourceType.lab_id == lab_id, ResourceType.code == "airalogy_sample_v1"
            )
        )
        if collision:
            blockers.append("sample_code_conflict")
        access = await resolve_resource_access(db, user.id, lab_id)
        if "resource.manage" not in access.capabilities:
            blockers.append("sample_setup_requires_lab_resource_manager")
    shared_revision = None
    if shared:
        resource_type = await db.get(
            ResourceType, shared.resource_type_id, populate_existing=True
        )
        shared_revision = (
            await db.get(ResourceTypeRevision, resource_type.current_revision_id)
            if resource_type
            else None
        )
        if request.action == "apply" and (
            not resource_type
            or resource_type.archived_at
            or not shared_revision
            or shared_revision.schema_hash != shared.schema_digest
        ):
            blockers.append("shared_sample_schema_changed")
    assets = await describe_assets(db, user, project, app) if project else []
    if app and len(assets) != len(app.assets):
        blockers.append("source_protocol_access_required")
    create_measurement = request.action == "apply" and (
        app is None or request.strategy == "new_copy"
    )
    if (
        request.action == "apply"
        and app
        and any(not asset["available"] for asset in assets)
        and not create_measurement
    ):
        blockers.append("source_protocol_unavailable_choose_new_copy")
    payload = {
        "request": request.model_dump(mode="json"),
        "lab_id": str(lab_id),
        "project_id": str(project_id) if project_id else None,
        "destination": {"lab": lab.name, "project": project.name if project else None},
        "manifest": value,
        "installation_revision": installed.revision if installed else 0,
        "application_revision": app.revision if app else 0,
        "shared_type_revision": str(shared_revision.id) if shared_revision else None,
        "assets": assets,
        "create_components": (
            ["sample"] if request.action == "apply" and not shared else []
        )
        + (["measurement"] if create_measurement else []),
        "blockers": blockers,
    }
    payload["digest"] = digest(payload)
    return payload


async def preview(db, user, lab_id, project_id, request):
    payload = await plan(db, user, lab_id, project_id, request)
    expires = datetime.now(UTC) + timedelta(minutes=15)
    payload["preview_token"] = jwt.encode(
        {
            "aud": AUDIENCE,
            "sub": str(user.id),
            "digest": payload["digest"],
            "exp": expires,
        },
        config.SECRET_KEY,
        algorithm="HS256",
    )
    payload["expires_at"] = expires.isoformat()
    return payload


async def materialize_protocol(db, user, project, component, version, uploaded):
    uid = f"kit_{component}_{uuid4().hex[:12]}"
    files = template_files(component, uid, version)
    Path(config.PROTOCOL_DIR).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="kit_", dir=config.PROTOCOL_DIR
    ) as directory_name:
        directory_path = Path(directory_name)
        for name, content in files.items():
            (directory_path / name).write_text(content)
        response = await protocol_exec(
            "get_protocol_info", directory_path.name, {"env_vars": {}}
        )
    if not response.get("success"):
        raise HTTPException(
            503, "Bundled Protocol compilation failed; no kit assets were saved"
        )
    info = response["data"]
    metadata = info["meta_data"]
    protocol = Protocol(
        project_id=project.id,
        user_id=user.id,
        uid=uid,
        name=metadata["name"],
        kind=metadata["kind"],
        latest_version=version,
    )
    db.add(protocol)
    await db.flush()
    stored = ProtocolVersion(
        protocol_id=protocol.id,
        version=version,
        meta_data=metadata,
        aimd=info["aimd"],
        fields=info["fields"],
        json_schema=info["json_schema"],
        assigners=info["assigners"],
        assigner_graph=info["assigner_graph"],
    )
    db.add(stored)
    await db.flush()
    stream = BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    stream.seek(0)
    uploaded.append(stored.package_object_key)
    await stored.upload_package(stream, length=len(stream.getvalue()))
    # Local keyword indexing participates in the asset transaction and never
    # depends on a model service. Optional vectors may be rebuilt normally.
    for chunk in text_to_chunks(stored.aimd):
        db.add(
            Embedding(
                protocol_id=protocol.id,
                resource_id=protocol.id,
                resource_type=EmbeddingResourceType.PROTOCOL,
                text=chunk,
                tsv=func.to_tsvector("english", " ".join(text_to_words(chunk))),
                embedding=None,
            )
        )
    return protocol, stored


async def confirm(db, user, lab_id, project_id, params):
    request = KitRequest.model_validate(
        params.model_dump(exclude={"preview_token", "request_id"})
    )
    await context(db, user, lab_id, project_id, manage=True, lock=True)
    request_digest = digest(
        {
            "request": request.model_dump(mode="json"),
            "lab": str(lab_id),
            "project": str(project_id) if project_id else None,
        }
    )
    prior = await db.scalar(
        select(ScenarioKitEvent).where(
            ScenarioKitEvent.actor_user_id == user.id,
            ScenarioKitEvent.request_id == params.request_id,
        )
    )
    if prior:
        if prior.request_digest != request_digest:
            raise HTTPException(409, "Request ID belongs to another operation")
        # Reauthorize the same scope, then return the non-sensitive receipt.
        return {"event_id": str(prior.id), "replayed": True}
    current = await plan(db, user, lab_id, project_id, request)
    try:
        claims = jwt.decode(
            params.preview_token,
            config.SECRET_KEY,
            algorithms=["HS256"],
            audience=AUDIENCE,
        )
        if (
            claims.get("sub") != str(user.id)
            or claims.get("digest") != current["digest"]
        ):
            raise ValueError("Stale preview")
    except (JWTError, ValueError) as exc:
        raise HTTPException(409, "Preview changed or expired; preview again") from exc
    if current["blockers"]:
        raise HTTPException(
            409,
            {"message": "Kit operation is blocked", "blockers": current["blockers"]},
        )
    installed = await installation(db, lab_id, request.kit_id)
    app = await application(db, project_id, request.kit_id) if project_id else None
    uploaded = []
    try:
        if request.action in {"enable", "disable"}:
            if installed is None:
                installed = LabScenarioKit(
                    lab_id=lab_id, kit_id=request.kit_id, revision=0
                )
                db.add(installed)
            installed.version = request.version
            installed.manifest = current["manifest"]
            installed.enabled = request.action == "enable"
            installed.revision += 1
            installed.updated_at = datetime.now(UTC)
        elif request.action == "deactivate":
            if app:
                app.enabled = False
                app.revision += 1
                app.updated_at = datetime.now(UTC)
        else:
            project = await db.get(Project, project_id)
            shared = await shared_component(db, lab_id)
            if "sample" in current["create_components"]:
                definition, version = await materialize_protocol(
                    db, user, project, "sample", "1.0.0", uploaded
                )
                resource_type = ResourceType(
                    lab_id=lab_id,
                    code="airalogy_sample_v1",
                    name="Sample / 样品",
                    created_by_user_id=user.id,
                )
                db.add(resource_type)
                await db.flush()
                type_revision = ResourceTypeRevision(
                    resource_type_id=resource_type.id,
                    protocol_id=definition.id,
                    protocol_version_id=version.id,
                    protocol_version="1.0.0",
                    revision=1,
                    capabilities={
                        "sample": True,
                        "inventory": True,
                        "lots": True,
                        "containers": True,
                    },
                    booking_policy="none",
                    schema_hash=digest(version.json_schema),
                    created_by_user_id=user.id,
                )
                db.add(type_revision)
                await db.flush()
                resource_type.current_revision_id = type_revision.id
                shared = ScenarioSharedComponent(
                    lab_id=lab_id,
                    component_id="airalogy.sample.v1",
                    resource_type_id=resource_type.id,
                    schema_digest=type_revision.schema_hash,
                )
                db.add(shared)
            assets = list(app.assets) if app else []
            if "measurement" in current["create_components"]:
                protocol, version = await materialize_protocol(
                    db, user, project, "measurement", request.version, uploaded
                )
                assets.append(
                    {
                        "component_id": "measurement",
                        "protocol_id": str(protocol.id),
                        "protocol_version_id": str(version.id),
                        "version": version.version,
                        "snapshot_digest": version_digest(version),
                        "source_kit_version": request.version,
                        "resource_type_id": str(shared.resource_type_id),
                    }
                )
            if app is None:
                app = ScenarioKitApplication(
                    project_id=project_id,
                    kit_id=request.kit_id,
                    installation_id=installed.id,
                    created_by_user_id=user.id,
                    revision=0,
                )
                db.add(app)
            app.version = request.version
            app.manifest = current["manifest"]
            app.enabled = True
            app.assets = assets
            app.revision += 1
            app.updated_at = datetime.now(UTC)
        # Compilation/storage may take time. Reauthorize with a fresh identity
        # map so revoked legacy roles and scoped grants cannot survive in cache.
        async with AsyncSession(bind=db.bind) as authorization:
            await context(authorization, user, lab_id, project_id, manage=True)
            if "sample" in current["create_components"]:
                access = await resolve_resource_access(authorization, user.id, lab_id)
                if "resource.manage" not in access.capabilities:
                    raise HTTPException(403, "Sample setup permission was revoked")
        await db.flush()
        event = ScenarioKitEvent(
            lab_id=lab_id,
            project_id=project_id,
            actor_user_id=user.id,
            request_id=params.request_id,
            operation=request.action,
            request_digest=request_digest,
            snapshot={
                "preview": current,
                "assets": app.assets if app else [],
                "revision": app.revision if app else installed.revision,
            },
        )
        db.add(event)
        await db.commit()
    except BaseException as exc:
        await db.rollback()
        for key in uploaded:
            try:
                await delete_file(key)
            except Exception:  # noqa: BLE001 - cleanup must not mask the original failure
                logger.warning("Unable to remove an uncommitted scenario package")
        if isinstance(exc, IntegrityError):
            raise HTTPException(
                409, "A kit asset or request changed concurrently; preview again"
            ) from exc
        raise
    return {"event_id": str(event.id), "replayed": False}
