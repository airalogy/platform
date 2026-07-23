import os
import re
import shutil
import uuid
from io import StringIO
from pathlib import Path

from dotenv import dotenv_values
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, UploadFile
from pydantic_core import ValidationError

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
from app.models.lab import Lab
from app.models.project import Project
from app.models.protocol import Protocol, ProtocolKind
from app.models.protocol_version import ProtocolMetadata, ProtocolVersion
from app.routers.permission import check_user_permission
from app.routers.utils import UUID
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
    if protocol is None:
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
            raise HTTPException(status_code=400, detail="Protocol kind cannot be changed")
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
            raise HTTPException(status_code=400, detail="Current Protocol version not found")
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
    return {"data": protocol}


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
