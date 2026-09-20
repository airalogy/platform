"""Source-authorized DataAsset files pinned to a fixed Workflow Run.

The graph declares input slots, not source permissions or executed Actions.
Selection verifies actual managed bytes; immutable receipts retain exact versions.
Later receipts recheck live scope/visibility and the sealed source identities.
"""

import re
from copy import deepcopy
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.knowledge import ResearchFile, ResearchFileBlob
from app.models.project import Project
from app.models.protocol_version import ProtocolVersion
from app.models.research import ResearchRun, ResearchTask
from app.models.research_asset import DataAsset, DataAssetVersion
from app.models.workflow_asset import WorkflowRunAssetInput
from app.services.analysis_engine import canonical_digest
from app.services.knowledge import authorize_research_file
from app.services.workflow_contracts import _bounded_json

MAX_JSON_BYTES = 1024 * 1024
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_SOURCE_SNAPSHOT_BYTES = 2 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _identity(value):
    return str(value) if value is not None else None


def _version_payload(version):
    payload = {
        "id": str(version.id),
        "data_asset_id": str(version.data_asset_id),
        "version": version.version,
        "research_file_id": _identity(version.research_file_id),
        "external_uri": version.external_uri,
        "media_type": version.media_type,
        "checksum": version.checksum,
        "byte_size": version.byte_size,
        "data_schema": version.data_schema,
        "metadata": version.version_metadata,
        "source": version.source,
        "change_summary": version.change_summary,
        "created_by_user_id": str(version.created_by_user_id),
        "created_at": version.created_at.isoformat(),
    }
    _snapshot_bounds(payload)
    return deepcopy(payload)


def _snapshot_bounds(payload):
    try:
        _bounded_json(payload, MAX_SOURCE_SNAPSHOT_BYTES)
    except (ValueError, TypeError, RecursionError) as exc:
        raise HTTPException(
            422, "Workflow DataAsset source metadata exceeds safe JSON or 2 MiB limits"
        ) from exc


def _file_payload(file):
    # Visibility and archived_at stay live/revocable, not locked access grants.
    return {
        "id": str(file.id),
        "blob_id": str(file.blob_id),
        "filename": file.filename,
        "scope_type": file.scope_type,
        "owner_user_id": _identity(file.owner_user_id),
        "lab_id": _identity(file.lab_id),
        "project_id": _identity(file.project_id),
        "uploaded_by_user_id": str(file.uploaded_by_user_id),
        "created_at": file.created_at.isoformat(),
    }


def _blob_payload(blob):
    return {
        "id": str(blob.id),
        "sha256": blob.checksum_sha256,
        "size_bytes": blob.size_bytes,
        "content_type": blob.content_type,
        "storage_backend": blob.storage_backend,
        "storage_namespace": blob.storage_namespace,
        "storage_object_key": blob.storage_object_key,
    }


def asset_input_payload(row):
    return {
        "schema": "airalogy.workflow-run-asset-input.v1",
        **{
            key: str(getattr(row, key))
            for key in (
                "id",
                "workflow_revision_id",
                "task_id",
                "run_id",
                "data_asset_version_id",
                "research_file_id",
                "blob_id",
                "created_by_user_id",
            )
        },
        "input_id": row.input_id,
        "source_digest": row.source_digest,
        "snapshot": row.snapshot,
    }


def verify_asset_input_seal(row):
    try:
        _bounded_json(row.snapshot, MAX_SOURCE_SNAPSHOT_BYTES)
        valid = (
            canonical_digest(row.snapshot) == row.source_digest
            and canonical_digest(asset_input_payload(row)) == row.digest
            and row.snapshot["schema"] == "airalogy.workflow-asset-source.v1"
            and row.snapshot["version"]["id"] == str(row.data_asset_version_id)
            and row.snapshot["file"]["id"] == str(row.research_file_id)
            and row.snapshot["blob"]["id"] == str(row.blob_id)
        )
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
        valid = False
    if not valid:
        raise HTTPException(409, "Workflow DataAsset input integrity check failed")


def _readiness(asset, approved_current_version=None):
    if asset.archived_at is not None or asset.status == "archived":
        raise HTTPException(403, "Workflow DataAsset source is archived")
    if approved_current_version is None:
        allowed = asset.status == "ready"
    else:
        allowed = (
            asset.current_version == approved_current_version
            and asset.status == "ready"
        ) or (
            asset.current_version > approved_current_version
            and asset.status in {"ready", "draft"}
        )
    if not allowed:
        raise HTTPException(409, "Workflow DataAsset source is not ready")


async def _source(db, *, version_id, project, user, approved_current_version=None):
    from app.services.research_runtime import require_research_capability

    if user is None:
        raise HTTPException(403, "Workflow DataAsset source permission is required")
    current_project = await db.get(Project, project.id, populate_existing=True)
    if (
        current_project is None
        or current_project.deleted_at is not None
        or current_project.lab_id != project.lab_id
    ):
        raise HTTPException(403, "Workflow DataAsset Project is unavailable")
    await require_research_capability(
        db, project=current_project, user=user, capability="research.read"
    )
    found = (
        await db.execute(
            select(DataAsset, DataAssetVersion, ResearchFile, ResearchFileBlob)
            .join(DataAssetVersion, DataAssetVersion.data_asset_id == DataAsset.id)
            .join(ResearchFile, ResearchFile.id == DataAssetVersion.research_file_id)
            .join(ResearchFileBlob, ResearchFileBlob.id == ResearchFile.blob_id)
            .where(DataAssetVersion.id == version_id)
            .execution_options(populate_existing=True)
        )
    ).first()
    if found is None:
        raise HTTPException(404, "Managed DataAsset version not found")
    asset, version, file, blob = found
    source_task = (
        await db.get(ResearchTask, asset.task_id, populate_existing=True)
        if asset.task_id
        else None
    )
    if (
        asset.project_id != project.id
        or asset.lab_id != project.lab_id
        or version.external_uri
        or type(version.version) is not int
        or version.version < 1
        or version.version > asset.current_version
        or file.scope_type not in {"lab", "project"}
        or file.lab_id != project.lab_id
        or file.project_id not in {None, project.id}
        or file.archived_at is not None
        or file.visibility in {"private", "restricted"}
        or blob.storage_backend not in {"minio", "oss"}
        or not blob.storage_object_key
        or source_task is None
        or source_task.archived_at is not None
        or source_task.project_id != project.id
        or source_task.lab_id != project.lab_id
    ):
        raise HTTPException(
            403,
            "Workflow inputs require accessible Project-local managed DataAsset files",
        )
    await authorize_research_file(db, user, file)
    _readiness(asset, approved_current_version)
    if (
        type(blob.size_bytes) is not int
        or not 0 <= blob.size_bytes <= MAX_FILE_BYTES
        or not isinstance(blob.checksum_sha256, str)
        or _SHA256.fullmatch(blob.checksum_sha256) is None
    ):
        raise HTTPException(409, "DataAsset file has no valid bounded byte receipt")
    if (version.byte_size is not None and version.byte_size != blob.size_bytes) or (
        version.checksum and version.checksum != blob.checksum_sha256
    ):
        raise HTTPException(
            409, "DataAsset declared size or checksum differs from managed bytes"
        )
    return asset, version, file, blob


def _public_fields(version, file):
    from app.services.workflow_asset_contracts import (
        asset_field_catalog,
        asset_file_catalog,
    )

    extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    catalog = asset_file_catalog(extension) if extension else {}
    if version.data_schema:
        try:
            catalog = {**catalog, **asset_field_catalog(version.data_schema)}
        except ValueError:
            # An opaque CSV/image remains usable as a whole file even when its
            # descriptive schema is not an executable JSON scalar contract.
            pass
    return [
        {
            "path": list(path),
            "title": ".".join(path),
            "value_type": spec.value_type,
            "unit": spec.unit,
            "nullable": spec.nullable,
            "file_extensions": spec.file_extensions,
        }
        for path, spec in catalog.items()
    ]


def _summary(asset, version, file, blob):
    return {
        "data_asset_id": str(asset.id),
        "name": asset.name,
        "data_asset_version_id": str(version.id),
        "version_id": str(version.id),
        "version": version.version,
        "research_file_id": str(file.id),
        "blob_id": str(blob.id),
        "filename": file.filename,
        "media_type": version.media_type or blob.content_type,
        "byte_size": blob.size_bytes,
        "sha256": blob.checksum_sha256,
    }


async def preview_asset_inputs(db, *, user, owner, project, graph, asset_versions):
    from app.services.workflow_asset_contracts import parse_asset_json
    from app.services.workflow_files import validate_file_header, verified_blob_spool

    declared = {item.input_id for item in graph.asset_inputs}
    if set(asset_versions) != declared:
        raise HTTPException(
            422, "Select one exact DataAsset version for every declared Workflow input"
        )
    json_inputs = {
        binding.input_id
        for binding in graph.asset_bindings
        if binding.source_path[0] == "json"
    }
    previews, total = [], 0
    for input_id in sorted(declared):
        try:
            version_id = UUID(str(asset_versions[input_id]))
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                422, "Workflow input requires an exact DataAsset version ID"
            ) from exc
        asset, version, file, blob = await _source(
            db, version_id=version_id, project=project, user=user
        )
        await _source(db, version_id=version_id, project=project, user=owner)
        total += blob.size_bytes
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(
                413, "Workflow DataAsset inputs exceed the 512 MiB total limit"
            )
        snapshot = {
            "schema": "airalogy.workflow-asset-source.v1",
            "asset": {
                "id": str(asset.id),
                "project_id": str(asset.project_id),
                "lab_id": str(asset.lab_id),
                "name": asset.name,
                "kind": asset.kind,
                "task_id": str(asset.task_id),
                "approved_current_version": asset.current_version,
            },
            "version": _version_payload(version),
            "file": _file_payload(file),
            "blob": _blob_payload(blob),
        }
        if input_id in json_inputs and blob.size_bytes > MAX_JSON_BYTES:
            raise HTTPException(413, "Workflow JSON DataAsset must not exceed 1 MiB")
        handle = await verified_blob_spool(blob)
        try:
            validate_file_header(handle, file.filename)
            if input_id in json_inputs:
                snapshot["json_value"] = parse_asset_json(
                    handle.read(), version.data_schema
                )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            handle.close()
        _snapshot_bounds(snapshot)
        # Slow storage IO does not preserve an earlier membership/visibility grant.
        again = await _source(db, version_id=version_id, project=project, user=user)
        await _source(db, version_id=version_id, project=project, user=owner)
        if (
            _version_payload(again[1]) != snapshot["version"]
            or _file_payload(again[2]) != snapshot["file"]
            or _blob_payload(again[3]) != snapshot["blob"]
            or again[0].current_version != snapshot["asset"]["approved_current_version"]
        ):
            raise HTTPException(409, "DataAsset source changed during Workflow preview")
        preview = {
            "input_id": input_id,
            **_summary(asset, version, file, blob),
            "source_digest": canonical_digest(snapshot),
            "snapshot": snapshot,
        }
        previews.append(preview)
    await _validate_preview_bindings(db, graph, previews)
    return previews


async def _validate_preview_bindings(db, graph, previews):
    from app.services.workflow_asset_contracts import (
        asset_field_catalog,
        asset_file_catalog,
        resolve_asset_value,
    )
    from app.services.workflow_data import (
        protocol_field_catalog,
        validate_protocol_initial_values,
    )

    nodes = {node.node_id: node for node in graph.nodes}
    sources = {preview["input_id"]: preview for preview in previews}
    targets, values = {}, {}
    for binding in graph.asset_bindings:
        preview = sources[binding.input_id]
        node = nodes[binding.target_node_id]
        if node.node_id not in targets:
            targets[node.node_id] = await db.get(
                ProtocolVersion, node.protocol_version_id, populate_existing=True
            )
            values[node.node_id] = deepcopy(node.initial_values)
        version = targets[node.node_id]
        if version is None or version.protocol_id != node.protocol_id:
            raise HTTPException(
                409, "Workflow DataAsset target Protocol version is unavailable"
            )
        try:
            target = protocol_field_catalog(version, include_files=True).get(
                tuple(binding.target_path)
            )
            if (
                target is None
                or target.value_type != binding.value_type
                or target.unit != binding.unit
            ):
                raise ValueError(
                    "DataAsset binding differs from its exact target field"
                )
            if binding.value_type == "file":
                filename = preview["filename"]
                extension = (
                    filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                )
                file_spec = asset_file_catalog(extension)[("file",)]
                if target.file_extensions is not None and not set(
                    file_spec.file_extensions
                ) <= set(target.file_extensions):
                    raise ValueError(
                        "DataAsset file extension conflicts with the target Protocol field"
                    )
            else:
                snapshot = preview["snapshot"]
                value = resolve_asset_value(
                    binding,
                    snapshot["json_value"],
                    asset_field_catalog(snapshot["version"]["data_schema"]),
                )
                values[node.node_id][binding.target_path[1]] = value
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
    # Validate the complete known prefill, not just source types. Unknown parent
    # values and not-yet-authorized file aliases remain absent until resolution.
    for node_id, version in targets.items():
        try:
            validate_protocol_initial_values(version, values[node_id])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc


async def materialize_asset_inputs(
    db, *, previews, workflow_revision_id, task, run, user
):
    if run.task_id != task.id:
        raise HTTPException(409, "Workflow DataAsset input Run scope changed")
    # The API session does not autoflush: publish the caller's pinned environment
    # before populate_existing reauthorization reloads the same Run identity.
    await db.flush()
    existing = list(
        (
            await db.scalars(
                select(WorkflowRunAssetInput).where(
                    WorkflowRunAssetInput.run_id == run.id
                )
            )
        ).all()
    )
    if existing:
        expected = {item["input_id"]: item["source_digest"] for item in previews}
        if {row.input_id: row.source_digest for row in existing} != expected or any(
            row.workflow_revision_id != workflow_revision_id for row in existing
        ):
            raise HTTPException(
                409, "Workflow DataAsset inputs already have another immutable contract"
            )
        for row in existing:
            await authorize_asset_input(db, row, user)
        return existing
    # Serialize the first receipt with concurrent source metadata edits. Source
    # UPDATE triggers become authoritative once this transaction commits; before
    # then, these shared row locks prevent an earlier UPDATE from slipping past
    # the new immutable reference. All runs use table order, then UUID order.
    for model, key in (
        (DataAssetVersion, "data_asset_version_id"),
        (ResearchFile, "research_file_id"),
        (ResearchFileBlob, "blob_id"),
    ):
        identities = sorted({UUID(str(item[key])) for item in previews})
        if not identities:
            continue
        locked = list(
            (
                await db.scalars(
                    select(model)
                    .where(model.id.in_(identities))
                    .order_by(model.id)
                    .with_for_update(read=True)
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        if {item.id for item in locked} != set(identities):
            raise HTTPException(
                409, "Workflow DataAsset source disappeared before confirmation"
            )
    rows = []
    for preview in previews:
        row = WorkflowRunAssetInput(
            id=uuid4(),
            input_id=preview["input_id"],
            workflow_revision_id=workflow_revision_id,
            task_id=task.id,
            run_id=run.id,
            data_asset_version_id=UUID(preview["data_asset_version_id"]),
            research_file_id=UUID(preview["research_file_id"]),
            blob_id=UUID(preview["blob_id"]),
            snapshot=deepcopy(preview["snapshot"]),
            source_digest=preview["source_digest"],
            created_by_user_id=user.id,
        )
        row.digest = canonical_digest(asset_input_payload(row))
        verify_asset_input_seal(row)
        await authorize_asset_input(db, row, user)
        db.add(row)
        rows.append(row)
    await db.flush()
    return rows


async def authorize_asset_input(db, row, user):
    verify_asset_input_seal(row)
    try:
        task = await db.get(ResearchTask, row.task_id, populate_existing=True)
        run = await db.get(ResearchRun, row.run_id, populate_existing=True)
        project = (
            await db.get(Project, task.project_id, populate_existing=True)
            if task
            else None
        )
        if (
            task is None
            or run is None
            or project is None
            or run.task_id != task.id
            or task.lab_id != project.lab_id
            or row.snapshot["asset"]["project_id"] != str(project.id)
            or row.snapshot["asset"]["lab_id"] != str(project.lab_id)
            or str(row.workflow_revision_id)
            != ((run.environment_snapshot or {}).get("manual_workflow") or {}).get(
                "revision_id"
            )
        ):
            raise HTTPException(409, "Workflow DataAsset input execution scope changed")
        asset, version, file, blob = await _source(
            db,
            version_id=row.data_asset_version_id,
            project=project,
            user=user,
            approved_current_version=row.snapshot["asset"]["approved_current_version"],
        )
        if (
            str(asset.id) != row.snapshot["asset"]["id"]
            or str(asset.task_id) != row.snapshot["asset"]["task_id"]
            or _version_payload(version) != row.snapshot["version"]
            or _file_payload(file) != row.snapshot["file"]
            or _blob_payload(blob) != row.snapshot["blob"]
        ):
            raise HTTPException(
                409, "Workflow DataAsset pinned source metadata changed"
            )
        return version, file, blob
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(
            409, "Workflow DataAsset input source contract is unavailable"
        ) from exc


async def list_asset_versions(db, *, user, project, offset=0, limit=50):
    if (
        type(offset) is not int
        or offset < 0
        or type(limit) is not int
        or not 1 <= limit <= 100
    ):
        raise HTTPException(422, "Invalid DataAsset source pagination")
    versions = list(
        (
            await db.scalars(
                select(DataAssetVersion.id)
                .join(DataAsset, DataAsset.id == DataAssetVersion.data_asset_id)
                .where(
                    DataAsset.project_id == project.id,
                    DataAsset.lab_id == project.lab_id,
                    DataAsset.archived_at.is_(None),
                    DataAsset.status == "ready",
                    DataAssetVersion.research_file_id.is_not(None),
                )
                .order_by(DataAsset.id, DataAssetVersion.version.desc())
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    items = []
    for version_id in versions[:limit]:
        try:
            asset, version, file, blob = await _source(
                db, version_id=version_id, project=project, user=user
            )
            fields = _public_fields(version, file)
        except HTTPException as exc:
            if exc.status_code not in {400, 403, 404, 409}:
                raise
            continue
        except ValueError:
            continue
        summary = _summary(asset, version, file, blob)
        summary.pop("blob_id")
        items.append({**summary, "fields": fields})
    return {
        "items": items,
        "next_offset": offset + limit if len(versions) > limit else None,
    }
