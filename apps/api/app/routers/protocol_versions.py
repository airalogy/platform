import os
import re
import shutil
import uuid
from io import StringIO
from pathlib import Path

from dotenv import dotenv_values
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, UploadFile
from pydantic_core import ValidationError
from sqlalchemy import select

from app.config import config
from app.database import DBSession
from app.libs.file_storage import file_local_url, object_exists, upload_file
from app.libs.protocol_agent import (
    prepare_protocol_package,
    protocol_exec,
    remove_exclude_files,
    unzip_file,
    zip_dir,
)
from app.models.airalogy_file import AiralogyFile
from app.models.embedding import Embedding, EmbeddingResourceType
from app.models.knowledge import (
    KnowledgeItem,
    KnowledgeProtocolLink,
    KnowledgeState,
    OwnerScope,
)
from app.models.lab import Lab
from app.models.project import Project
from app.models.protocol import Protocol, ProtocolKind
from app.models.protocol_version import ProtocolMetadata, ProtocolVersion
from app.models.research import ResearchTask
from app.models.research_asset import (
    ProtocolImprovementProposal,
    ProtocolImprovementState,
)
from app.routers.permission import check_user_permission
from app.routers.utils import UUID
from app.services.knowledge import authorize_knowledge_item, snapshot_knowledge
from app.services.research_runtime import emit_research_event, utcnow
from app.services.schema_governance import (
    SchemaGovernanceError,
    build_compatibility_report,
    load_package_migration_manifests,
)

from .depends import CurrentUser, OptionalCurrentUser

router = APIRouter(
    prefix="/protocols",
    tags=["protocols"],
)


def clear_protocol(protocol_name: str):
    protocol_dir = config.PROTOCOL_DIR
    protocol_path = f"{protocol_dir}/{protocol_name}"
    if os.path.exists(protocol_path):
        shutil.rmtree(protocol_path)


# compare version
def is_new_version(current_version: str, new_version: str) -> bool:
    try:
        return tuple(map(int, new_version.split("."))) > tuple(
            map(int, current_version.split("."))
        )
    except ValueError:
        return False


def _validate_resource_definition(info: dict, kind: str) -> None:
    if kind != ProtocolKind.RESOURCE_DEFINITION:
        return
    fields = info.get("fields") if isinstance(info.get("fields"), dict) else {}
    forbidden = {
        "steps": fields.get("steps"),
        "checks": fields.get("checks"),
        "quizzes": fields.get("quizzes"),
        "workflow": fields.get("workflow"),
        "collectors": fields.get("collectors"),
        "client_assigner": fields.get("client_assigner"),
        "assigners": info.get("assigners"),
    }
    used = sorted(key for key, value in forbidden.items() if value)
    if used:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "resource_definition contains experimental runtime features",
                "features": used,
            },
        )


async def _validated_knowledge_source(
    db_session: DBSession,
    current_user,
    project: Project,
    item_id: UUID,
    expected_revision: int,
    *,
    lock: bool = False,
) -> KnowledgeItem:
    statement = select(KnowledgeItem).where(KnowledgeItem.id == item_id)
    if lock:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    item = await db_session.scalar(statement)
    if item is None:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    await authorize_knowledge_item(db_session, current_user, item)
    if item.revision != expected_revision:
        raise HTTPException(
            status_code=409,
            detail="Knowledge item changed; reload before saving the Protocol",
        )
    if item.state in {KnowledgeState.ARCHIVED.value, KnowledgeState.SUPERSEDED.value}:
        raise HTTPException(
            status_code=409,
            detail="Archived or superseded Knowledge cannot create a Protocol",
        )
    if item.scope_type == OwnerScope.LAB.value and item.lab_id != project.lab_id:
        raise HTTPException(
            status_code=422,
            detail="Lab Knowledge can only create a Protocol in the same Lab",
        )
    if item.scope_type == OwnerScope.PROJECT.value and item.project_id != project.id:
        raise HTTPException(
            status_code=422,
            detail="Project Knowledge can only create a Protocol in the same Project",
        )
    return item


async def _validated_protocol_improvement(
    db_session: DBSession,
    project: Project,
    protocol: Protocol,
    proposal_id: UUID,
    expected_revision: int,
) -> ProtocolImprovementProposal:
    proposal = await db_session.scalar(
        select(ProtocolImprovementProposal)
        .where(ProtocolImprovementProposal.id == proposal_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Protocol improvement not found")
    task = await db_session.get(ResearchTask, proposal.task_id)
    if task is None or task.project_id != project.id or task.lab_id != project.lab_id:
        raise HTTPException(status_code=404, detail="Protocol improvement not found")
    if proposal.protocol_id != protocol.id:
        raise HTTPException(
            status_code=422,
            detail="Protocol improvement targets a different Protocol",
        )
    if proposal.revision != expected_revision:
        raise HTTPException(
            status_code=409,
            detail="Protocol improvement changed; reload before saving",
        )
    if proposal.state != ProtocolImprovementState.REVIEWED.value:
        raise HTTPException(
            status_code=409,
            detail="Protocol improvement must be reviewed before creating a version",
        )
    if proposal.applied_protocol_version_id is not None:
        raise HTTPException(
            status_code=409,
            detail="Protocol improvement has already been applied",
        )
    if proposal.base_protocol_version != protocol.latest_version:
        raise HTTPException(
            status_code=409,
            detail=(
                "Protocol changed after this improvement was reviewed; "
                "create a new proposal against the latest version"
            ),
        )
    return proposal


def _load_migration_manifests(
    protocol_path: str,
    *,
    target_version: str,
) -> list[dict]:
    migrations_dir = Path(protocol_path) / "migrations"
    if not migrations_dir.is_dir():
        return []
    try:
        manifests = load_package_migration_manifests(Path(protocol_path))
    except SchemaGovernanceError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    # A package can carry the complete migration graph, including jumps from
    # older versions. The direct edge is not mandatory for compatible changes.
    for manifest in manifests:
        if not is_new_version(manifest["from"], manifest["to"]):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Migration edges must move forward: "
                    f"{manifest['from']} -> {manifest['to']}"
                ),
            )
        if is_new_version(target_version, manifest["to"]):
            raise HTTPException(
                status_code=400,
                detail="Migration manifest cannot target a future package version",
            )
    return manifests


@router.get("/{protocol_id}/versions")
async def get_protocol_versions(
    protocol_id: UUID,
    db_session: DBSession,
    current_user: OptionalCurrentUser,
    page: int = 1,
    page_size: int = 10,
):
    protocol = await Protocol.find(db_session, id=protocol_id)
    if protocol is None:
        raise HTTPException(status_code=404, detail="Protocol not found")
    project: Project = await Project.find(db_session, id=protocol.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    lab: Lab = await Lab.find(db_session, id=project.lab_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
        protocol=protocol,
    )
    total_count = await ProtocolVersion.count(
        db_session,
        where_conditions=[ProtocolVersion.protocol_id == protocol_id],
    )
    protocol_versions: list[ProtocolVersion] = await ProtocolVersion.all(
        db_session,
        where_conditions=[ProtocolVersion.protocol_id == protocol_id],
        page=page,
        page_size=page_size,
    )
    for version in protocol_versions:
        version.lab_uid = lab.uid
        version.project_uid = project.uid

    return {
        "versions": protocol_versions,
        "total_count": total_count,
    }


@router.post("")
async def upload_package(
    current_user: CurrentUser,
    db_session: DBSession,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    project_id: UUID = Body(embed=True),
    env_vars: str = Body(default="", embed=True),
    protocol_id: UUID | None = Body(None, embed=True),
    source_knowledge_item_id: UUID | None = Body(None, embed=True),
    source_knowledge_revision: int | None = Body(None, embed=True),
    source_protocol_improvement_id: UUID | None = Body(None, embed=True),
    source_protocol_improvement_revision: int | None = Body(None, embed=True),
):
    project: Project = await Project.find(db_session, id=project_id)
    lab: Lab = await Lab.find(db_session, id=project.lab_id)
    if protocol_id is not None:
        protocol: Protocol = await Protocol.find(
            db_session, id=protocol_id, with_for_update=True
        )
        project = await Project.find(db_session, id=protocol.project_id)
        await check_user_permission(
            db_session,
            project=project,
            user=current_user,
            action="update_protocol",
            protocol=protocol,
        )
    else:
        await check_user_permission(
            db_session,
            project=project,
            user=current_user,
            action="create_protocol",
        )
        protocol = None
    if (source_knowledge_item_id is None) != (source_knowledge_revision is None):
        raise HTTPException(
            status_code=422,
            detail="Knowledge source id and revision must be provided together",
        )
    if source_knowledge_revision is not None and source_knowledge_revision < 1:
        raise HTTPException(
            status_code=422, detail="Knowledge revision must be positive"
        )
    if protocol_id is not None and source_knowledge_item_id is not None:
        raise HTTPException(
            status_code=422,
            detail="Knowledge provenance can only be attached when creating a Protocol",
        )
    if (source_protocol_improvement_id is None) != (
        source_protocol_improvement_revision is None
    ):
        raise HTTPException(
            status_code=422,
            detail="Protocol improvement id and revision must be provided together",
        )
    if (
        source_protocol_improvement_revision is not None
        and source_protocol_improvement_revision < 1
    ):
        raise HTTPException(
            status_code=422, detail="Protocol improvement revision must be positive"
        )
    if protocol_id is None and source_protocol_improvement_id is not None:
        raise HTTPException(
            status_code=422,
            detail="Protocol improvement can only create a new version of its Protocol",
        )
    if source_knowledge_item_id is not None and source_knowledge_revision is not None:
        await _validated_knowledge_source(
            db_session,
            current_user,
            project,
            source_knowledge_item_id,
            source_knowledge_revision,
        )
    if (
        file.content_type != "application/zip"
        and file.content_type != "application/x-zip-compressed"
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type}, only zip is supported",
        )

    tmp_protocol_name = f"upload_{uuid.uuid4()}"
    protocol_dir = config.PROTOCOL_DIR
    tmp_protocol_path = f"{protocol_dir}/{tmp_protocol_name}"
    unzip_file(file.file, tmp_protocol_path)
    remove_exclude_files(tmp_protocol_path)
    background_tasks.add_task(clear_protocol, tmp_protocol_name)
    env_vars_dict = dotenv_values(stream=StringIO(env_vars))
    env_vars_dict.update(
        {
            "AIRALOGY_ENDPOINT": config.AIRALOGY_ENDPOINT,
            "AIRALOGY_API_KEY": current_user.api_key,
        }
    )
    if protocol is not None:
        protocol.project_uid = project.uid
        protocol.lab_uid = lab.uid
        env_vars_dict["AIRALOGY_PROTOCOL_ID"] = f"airalogy.id.protocol.{protocol.id}"
    else:
        env_vars_dict["AIRALOGY_PROTOCOL_ID"] = ""
    res = await protocol_exec(
        "get_protocol_info", tmp_protocol_name, {"env_vars": env_vars_dict}
    )
    if res["success"] is False:
        raise HTTPException(status_code=400, detail=res["message"])
    info = res["data"]
    try:
        meta_data = ProtocolMetadata(**info["meta_data"])
    except ValidationError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid protocol.toml, error: {e.errors()}",
        )
    _validate_resource_definition(info, meta_data.kind)

    compatibility_report = None
    migration_manifest: list[dict] | None = None
    source_knowledge = None
    source_protocol_improvement = None
    if protocol is None:
        if (
            source_knowledge_item_id is not None
            and source_knowledge_revision is not None
        ):
            source_knowledge = await _validated_knowledge_source(
                db_session,
                current_user,
                project,
                source_knowledge_item_id,
                source_knowledge_revision,
                lock=True,
            )
        uid_exists = await Protocol.find_by(
            db_session,
            [
                Protocol.uid == meta_data.id,
                Protocol.project_id == project.id,
                Protocol.deleted_at.is_(None),
            ],
        )
        if uid_exists:
            raise HTTPException(status_code=400, detail="Protocol uid already exists")
        protocol: Protocol = Protocol(
            project_id=project.id,
            user_id=current_user.id,
            uid=meta_data.id,
            name=meta_data.name,
            kind=meta_data.kind,
            latest_version=meta_data.version,
            disciplines=meta_data.disciplines,
            keywords=meta_data.keywords,
            description=meta_data.description,
            env_vars=env_vars,
        )
        db_session.add(protocol)
        await db_session.flush()
    else:
        if protocol.uid != meta_data.id:
            raise HTTPException(status_code=400, detail="Protocol id cannot be changed")
        if protocol.kind != meta_data.kind:
            raise HTTPException(
                status_code=400, detail="Protocol kind cannot be changed"
            )
        if not is_new_version(protocol.latest_version, meta_data.version):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Protocol package version must be explicitly greater than "
                    f"{protocol.latest_version}; Platform does not rewrite versions"
                ),
            )
        previous_version = await ProtocolVersion.find_by(
            db_session,
            [
                ProtocolVersion.protocol_id == protocol.id,
                ProtocolVersion.version == protocol.latest_version,
            ],
        )
        if previous_version is None:
            raise HTTPException(
                status_code=400, detail="Current Protocol version not found"
            )
        if (
            source_protocol_improvement_id is not None
            and source_protocol_improvement_revision is not None
        ):
            source_protocol_improvement = await _validated_protocol_improvement(
                db_session,
                project,
                protocol,
                source_protocol_improvement_id,
                source_protocol_improvement_revision,
            )
        try:
            compatibility_report = build_compatibility_report(
                previous_version.json_schema,
                info["json_schema"],
                previous_version=previous_version.version,
                current_version=meta_data.version,
            )
        except SchemaGovernanceError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        migration_manifest = _load_migration_manifests(
            tmp_protocol_path,
            target_version=meta_data.version,
        )
        protocol.latest_version = meta_data.version
        if len(env_vars) > 0:
            protocol.env_vars = env_vars
        protocol.disciplines = meta_data.disciplines
        protocol.keywords = meta_data.keywords

    protocol_version_exists = await ProtocolVersion.exists(
        db_session,
        [
            ProtocolVersion.protocol_id == protocol.id,
            ProtocolVersion.version == meta_data.version,
        ],
    )
    if protocol_version_exists:
        raise HTTPException(
            status_code=400,
            detail="Protocol version already exists, please increment version number",
        )
    protocol_version: ProtocolVersion = ProtocolVersion(
        protocol_id=protocol.id,
        json_schema=info["json_schema"],
        assigners=info["assigners"],
        assigner_graph=info["assigner_graph"],
        fields=info["fields"],
        aimd=info["aimd"],
        version=meta_data.version,
        meta_data=meta_data.model_dump(),
        compatibility_report=compatibility_report,
        migration_manifest=migration_manifest,
    )
    db_session.add(protocol_version)
    await db_session.flush()
    knowledge_source_payload = None
    if source_knowledge is not None:
        db_session.add(
            KnowledgeProtocolLink(
                knowledge_item_id=source_knowledge.id,
                knowledge_revision=source_knowledge.revision,
                protocol_id=protocol.id,
                protocol_version=protocol_version.version,
                relation_type="derived_from",
                source_snapshot=snapshot_knowledge(source_knowledge),
                created_by_user_id=current_user.id,
            )
        )
        knowledge_source_payload = {
            "item_id": source_knowledge.id,
            "revision": source_knowledge.revision,
            "protocol_version": protocol_version.version,
            "title": source_knowledge.title,
            "kind": source_knowledge.kind,
            "scope_type": source_knowledge.scope_type,
            "relation_type": "derived_from",
        }
    if source_protocol_improvement is not None:
        source_protocol_improvement.state = ProtocolImprovementState.APPLIED.value
        source_protocol_improvement.revision += 1
        source_protocol_improvement.applied_protocol_version_id = protocol_version.id
        source_protocol_improvement.applied_protocol_version = protocol_version.version
        source_protocol_improvement.applied_by_user_id = current_user.id
        source_protocol_improvement.applied_at = utcnow()
        await emit_research_event(
            db_session,
            task_id=source_protocol_improvement.task_id,
            kind="protocol_improvement.applied",
            actor_user_id=current_user.id,
            payload={
                "proposal_id": str(source_protocol_improvement.id),
                "protocol_id": str(protocol.id),
                "base_protocol_version": source_protocol_improvement.base_protocol_version,
                "applied_protocol_version": protocol_version.version,
            },
            idempotency_key=(
                f"protocol-improvement:{source_protocol_improvement.id}:"
                f"applied:{protocol_version.version}"
            ),
        )

    protocol_path = f"{protocol_dir}/{protocol_version.package_name}"
    if os.path.exists(protocol_path):
        shutil.rmtree(protocol_path)
    os.rename(tmp_protocol_path, protocol_path)
    if not os.path.exists(f"{protocol_dir}/tmp"):
        os.makedirs(f"{protocol_dir}/tmp")
    package_zip_file = f"{protocol_dir}/tmp/{protocol_version.package_name}.zip"
    remove_exclude_files(protocol_path)
    zip_dir(protocol_path, package_zip_file)
    await protocol_version.upload_package(package_file=package_zip_file)
    background_tasks.add_task(os.remove, package_zip_file)

    # 如果存在旧的 protocol，从 Embedding 中删除
    if protocol_id is not None:
        background_tasks.add_task(
            Embedding.remove_resource,
            protocol_id,
            EmbeddingResourceType.PROTOCOL,
        )

    # 添加新的 protocol 的 aimd 到 Embedding
    background_tasks.add_task(
        Embedding.add_resource,
        protocol.id,
        protocol.id,
        EmbeddingResourceType.PROTOCOL,
        protocol_version.aimd,
    )

    await db_session.commit()
    return {
        "data": protocol.as_dict(
            lab_uid=lab.uid,
            project_uid=project.uid,
            knowledge_sources=[knowledge_source_payload]
            if knowledge_source_payload is not None
            else [],
        )
    }


@router.get("/{id}/download_package")
async def download_package(
    id: UUID,
    version: str,
    current_user: OptionalCurrentUser,
    db_session: DBSession,
):
    protocol = await Protocol.find(db_session, id)
    if protocol is None:
        raise HTTPException(status_code=404, detail="Protocol not found")
    project = await Project.find(db_session, id=protocol.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
        protocol=protocol,
    )
    protocol_version = await ProtocolVersion.find_by(
        db_session,
        [
            ProtocolVersion.protocol_id == id,
            ProtocolVersion.version == version,
        ],
    )
    if protocol_version is None:
        raise HTTPException(status_code=404, detail="Protocol version not found")

    url = await protocol_version.download_url()
    return {"url": url}


@router.get("/{id}/package_files")
async def get_package_files(
    id: UUID,
    filename: str,
    current_user: OptionalCurrentUser,
    db_session: DBSession,
    version: str | None = None,
):
    protocol = await Protocol.find(db_session, id=id)
    if protocol is None:
        raise HTTPException(status_code=404, detail="Protocol not found")
    project = await Project.find(db_session, id=protocol.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
        protocol=protocol,
    )
    if version is None:
        version = protocol.latest_version
    protocol_version = await ProtocolVersion.find_by(
        db_session,
        [
            ProtocolVersion.protocol_id == id,
            ProtocolVersion.version == version,
        ],
    )
    if protocol_version is None:
        raise HTTPException(
            status_code=404, detail=f"Protocol version: #{version} not found"
        )
    filename = re.sub(r"^(\/|\.\/)", "", filename)
    object_key = f"{protocol_version.package_dir_object_key}/{filename}"
    obj_exists = await object_exists(object_key)
    if obj_exists:
        url = await file_local_url(object_key)
        return {"url": url, "filename": filename}

    await prepare_protocol_package(protocol_version)
    protocol_dir = config.PROTOCOL_DIR
    file_path = f"{protocol_dir}/{protocol_version.package_name}/{filename}"
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="static file not found")

    content_type, type = AiralogyFile.guess_type(filename)
    await upload_file(object_key, file=file_path, content_type=content_type)
    url = await file_local_url(object_key)
    return {"url": url, "filename": filename}
