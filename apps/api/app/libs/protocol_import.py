import os
import shutil
import uuid
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from fastapi import BackgroundTasks, HTTPException
from pydantic_core import ValidationError

from app.config import config
from app.database import DBSession
from app.libs.protocol_agent import protocol_exec, remove_exclude_files, zip_dir
from app.libs.version import Version
from app.models.embedding import Embedding, EmbeddingResourceType
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolMetadata, ProtocolVersion
from app.models.user import User


@dataclass
class ProtocolImportResult:
    protocol: Protocol
    protocol_version: ProtocolVersion
    created_protocol: bool
    created_version: bool
    reused_version: bool


def _is_newer_version(current_version: str, new_version: str) -> bool:
    try:
        return Version(new_version) > Version(current_version)
    except Exception:
        return current_version != new_version


def _protocol_env_vars(
    *,
    env_vars: str,
    user: User,
    protocol: Protocol | None,
) -> dict[str, Any]:
    env_vars_dict = dotenv_values(stream=StringIO(env_vars))
    env_vars_dict.update(
        {
            "AIRALOGY_ENDPOINT": config.AIRALOGY_ENDPOINT,
            "AIRALOGY_API_KEY": user.api_key,
            "AIRALOGY_PROTOCOL_ID": (
                f"airalogy.id.protocol.{protocol.id}" if protocol is not None else ""
            ),
        }
    )
    return env_vars_dict


async def _load_protocol_info(
    *,
    staged_name: str,
    env_vars: str,
    user: User,
    protocol: Protocol | None,
) -> tuple[dict[str, Any], ProtocolMetadata]:
    res = await protocol_exec(
        "get_protocol_info",
        staged_name,
        {
            "env_vars": _protocol_env_vars(
                env_vars=env_vars,
                user=user,
                protocol=protocol,
            )
        },
    )
    if res["success"] is False:
        raise HTTPException(status_code=400, detail=res["message"])

    info = res["data"]
    try:
        meta_data = ProtocolMetadata(**info["meta_data"])
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid protocol.toml, error: {exc.errors()}",
        ) from exc
    return info, meta_data


async def import_protocol_directory(
    *,
    db_session: DBSession,
    project: Project,
    user: User,
    source_dir: str | Path,
    env_vars: str = "",
    background_tasks: BackgroundTasks | None = None,
) -> ProtocolImportResult:
    source_path = Path(source_dir)
    if not source_path.is_dir():
        raise HTTPException(status_code=400, detail="Protocol directory not found")

    protocol_dir = Path(config.PROTOCOL_DIR)
    protocol_dir.mkdir(parents=True, exist_ok=True)
    staged_name = f"aira_import_{uuid.uuid4()}"
    staged_path = protocol_dir / staged_name
    package_path: Path | None = None
    package_zip_file: Path | None = None
    moved_to_package_path = False

    try:
        shutil.copytree(source_path, staged_path)
        archive_metadata_path = staged_path / "_airalogy_archive"
        if archive_metadata_path.exists():
            shutil.rmtree(archive_metadata_path)
        remove_exclude_files(str(staged_path))

        info, meta_data = await _load_protocol_info(
            staged_name=staged_name,
            env_vars=env_vars,
            user=user,
            protocol=None,
        )

        protocol = await Protocol.find_by(
            db_session,
            [
                Protocol.uid == meta_data.id,
                Protocol.project_id == project.id,
                Protocol.deleted_at.is_(None),
            ],
            with_for_update=True,
        )
        created_protocol = protocol is None

        if protocol is None:
            protocol = Protocol(
                project_id=project.id,
                user_id=user.id,
                uid=meta_data.id,
                name=meta_data.name or meta_data.id,
                latest_version=meta_data.version,
                disciplines=meta_data.disciplines or [],
                keywords=meta_data.keywords or [],
                description=meta_data.description,
                env_vars=env_vars,
            )
            db_session.add(protocol)
            await db_session.flush()
        else:
            info, meta_data = await _load_protocol_info(
                staged_name=staged_name,
                env_vars=env_vars,
                user=user,
                protocol=protocol,
            )
            if protocol.uid != meta_data.id:
                raise HTTPException(status_code=400, detail="Protocol id cannot be changed")
            if len(env_vars) > 0:
                protocol.env_vars = env_vars
            protocol.name = meta_data.name or protocol.name
            protocol.disciplines = meta_data.disciplines or []
            protocol.keywords = meta_data.keywords or []
            protocol.description = meta_data.description

        existing_protocol_version = await ProtocolVersion.find_by(
            db_session,
            [
                ProtocolVersion.protocol_id == protocol.id,
                ProtocolVersion.version == meta_data.version,
            ],
        )
        if existing_protocol_version is not None:
            return ProtocolImportResult(
                protocol=protocol,
                protocol_version=existing_protocol_version,
                created_protocol=created_protocol,
                created_version=False,
                reused_version=True,
            )

        protocol_version = ProtocolVersion(
            protocol_id=protocol.id,
            json_schema=info["json_schema"],
            assigners=info["assigners"],
            assigner_graph=info["assigner_graph"],
            fields=info["fields"],
            aimd=info["aimd"],
            version=meta_data.version,
            meta_data=meta_data.model_dump(),
        )
        db_session.add(protocol_version)
        await db_session.flush()

        if _is_newer_version(protocol.latest_version, meta_data.version):
            protocol.latest_version = meta_data.version

        package_path = protocol_dir / protocol_version.package_name
        if package_path.exists():
            shutil.rmtree(package_path)
        os.rename(staged_path, package_path)
        moved_to_package_path = True

        tmp_dir = protocol_dir / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        package_zip_file = tmp_dir / f"{protocol_version.package_name}.zip"
        remove_exclude_files(str(package_path))
        zip_dir(str(package_path), str(package_zip_file))
        await protocol_version.upload_package(package_file=str(package_zip_file))

        if background_tasks is not None:
            if not created_protocol:
                background_tasks.add_task(
                    Embedding.remove_resource,
                    protocol.id,
                    EmbeddingResourceType.PROTOCOL,
                )
            background_tasks.add_task(
                Embedding.add_resource,
                protocol.id,
                protocol.id,
                EmbeddingResourceType.PROTOCOL,
                protocol_version.aimd,
            )

        return ProtocolImportResult(
            protocol=protocol,
            protocol_version=protocol_version,
            created_protocol=created_protocol,
            created_version=True,
            reused_version=False,
        )
    except Exception:
        if moved_to_package_path and package_path is not None and package_path.exists():
            shutil.rmtree(package_path)
        raise
    finally:
        if not moved_to_package_path and staged_path.exists():
            shutil.rmtree(staged_path)
        if package_zip_file is not None and package_zip_file.exists():
            package_zip_file.unlink()
