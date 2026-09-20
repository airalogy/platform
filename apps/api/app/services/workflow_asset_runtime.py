"""Pinned resource inputs, separate from Workflow execution and control edges."""

from copy import deepcopy
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.user import User
from app.models.workflow_definition import WorkflowDefinition, WorkflowRevision
from app.services.research_runtime import canonical_digest


def asset_source_ref(row):
    return {
        "kind": "data_asset",
        "asset_input_id": str(row.id),
        "input_id": row.input_id,
        "data_asset_id": row.snapshot["version"]["data_asset_id"],
        "data_asset_version_id": str(row.data_asset_version_id),
        "version": row.snapshot["version"]["version"],
        "research_file_id": str(row.research_file_id),
        "source_digest": row.source_digest,
        "receipt_digest": row.digest,
    }


def asset_preview_summary(graph, previews):
    """Expose only declared values and file metadata, never the complete JSON file."""
    from app.services.workflow_asset_contracts import (
        asset_field_catalog,
        resolve_asset_value,
    )

    by_input = {item.input_id: item for item in graph.asset_inputs}
    result = []
    for item in previews:
        bindings = []
        for binding in graph.asset_bindings:
            if binding.input_id != item["input_id"]:
                continue
            entry = binding.model_dump(mode="json")
            if binding.value_type != "file":
                entry["value"] = resolve_asset_value(
                    binding,
                    item["snapshot"]["json_value"],
                    asset_field_catalog(item["snapshot"]["version"]["data_schema"]),
                )
                entry["value_digest"] = canonical_digest(entry["value"])
            bindings.append(entry)
        result.append(
            {
                **{
                    key: item[key]
                    for key in (
                        "input_id",
                        "data_asset_id",
                        "name",
                        "data_asset_version_id",
                        "version",
                        "research_file_id",
                        "filename",
                        "media_type",
                        "byte_size",
                        "sha256",
                        "source_digest",
                    )
                },
                "label": by_input[item["input_id"]].label,
                "bindings": bindings,
            }
        )
    return result


async def asset_rows_for_run(db, *, task, run, graph=None):
    from app.models.workflow_asset import WorkflowRunAssetInput
    from app.services.workflow_assets import verify_asset_input_seal
    from app.services.workflow_definitions import verify_revision

    marker = (run.environment_snapshot or {}).get("manual_workflow") or {}
    if marker.get("execution_contract_version") not in {6, 7}:
        return {}, graph
    try:
        revision = await db.get(WorkflowRevision, UUID(marker["revision_id"]))
        definition = (
            await db.get(WorkflowDefinition, revision.definition_id)
            if revision
            else None
        )
        if (
            task is None
            or definition is None
            or definition.project_id != task.project_id
        ):
            raise ValueError("Workflow asset revision is unavailable")
        pinned_graph = verify_revision(revision)
        from app.services.workflow_contracts import workflow_revision_digest

        if marker.get("revision_digest") != revision.digest or marker.get(
            "digest"
        ) != workflow_revision_digest(pinned_graph):
            raise ValueError("Workflow asset revision digest changed")
        if graph is not None and canonical_digest(
            graph.model_dump(mode="json")
        ) != canonical_digest(pinned_graph.model_dump(mode="json")):
            raise ValueError("Workflow asset graph changed")
        graph = pinned_graph
        rows = list(
            (
                await db.scalars(
                    select(WorkflowRunAssetInput)
                    .where(
                        WorkflowRunAssetInput.run_id == run.id,
                    )
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        by_input = {row.input_id: row for row in rows}
        if len(rows) != len(by_input) or set(by_input) != {
            item.input_id for item in graph.asset_inputs
        }:
            raise ValueError("Workflow asset input set changed")
        if marker.get("asset_input_digests") != {
            key: row.digest for key, row in by_input.items()
        }:
            raise ValueError("Workflow asset selection changed")
        for row in rows:
            verify_asset_input_seal(row)
            if row.task_id != task.id or row.workflow_revision_id != revision.id:
                raise ValueError("Workflow asset receipt belongs to another scope")
        return by_input, graph
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            409, "Workflow asset input receipt is unavailable or changed"
        ) from exc


async def authorize_run_asset_inputs(db, *, task, run, user, node_id=None):
    from app.services.workflow_assets import authorize_asset_input

    rows, graph = await asset_rows_for_run(db, task=task, run=run)
    selected = (
        set(rows)
        if node_id is None
        else {
            binding.input_id
            for binding in graph.asset_bindings
            if binding.target_node_id == node_id
        }
    )
    for key in selected:
        await authorize_asset_input(db, rows[key], user)


async def verify_asset_resolution(db, *, task, run, action, resolution, user=None):
    from app.services.workflow_assets import authorize_asset_input

    rows, graph = await asset_rows_for_run(db, task=task, run=run)
    refs = resolution.receipt.get("asset_sources", {})
    expected = (
        {
            binding.input_id
            for binding in graph.asset_bindings
            if binding.target_node_id == resolution.node_id
        }
        if resolution.state == "ready"
        else set()
    )
    if type(refs) is not dict or set(refs) != expected:
        raise HTTPException(409, "Workflow asset source receipt set changed")
    recipients = (
        [user]
        if user
        else [
            await db.get(User, uid)
            for uid in {
                task.owner_user_id,
                run.requested_by_user_id,
                action.assignee_user_id,
            }
        ]
    )
    for key, ref in refs.items():
        if canonical_digest(ref) != canonical_digest(asset_source_ref(rows[key])):
            raise HTTPException(409, "Workflow asset source lineage changed")
        for recipient in recipients:
            _, _, blob = await authorize_asset_input(db, rows[key], recipient)
        if user is None:
            from app.services.workflow_files import verified_blob_spool

            handle = await verified_blob_spool(blob)
            handle.close()
            for recipient in recipients:
                await authorize_asset_input(db, rows[key], recipient)


async def materialize_asset_file(
    db, *, task, run, node, action, binding, row, file, blob
):
    """Mint an ACL-preserving alias, not a copy with broader file permissions."""
    from app.models.airalogy_file import AiralogyFile
    from app.models.workflow_file import WorkflowFileBinding
    from app.services.knowledge import assert_research_file_upload_quota
    from app.services.workflow_files import (
        WORKFLOW_FILE_BACKEND,
        binding_payload,
        blob_snapshot,
        file_snapshot,
        validate_file_header,
        verified_blob_spool,
    )

    if (
        await db.scalar(
            select(WorkflowFileBinding.file_id).where(
                WorkflowFileBinding.action_id == action.id,
                WorkflowFileBinding.binding_id == binding.binding_id,
            )
        )
        is not None
    ):
        raise HTTPException(
            409, "Workflow asset file binding exists without its resolution"
        )
    spool = await verified_blob_spool(blob)
    try:
        validate_file_header(spool, file.filename)
    finally:
        spool.close()
    from app.services.workflow_assets import authorize_asset_input

    for uid in {task.owner_user_id, run.requested_by_user_id, action.assignee_user_id}:
        await authorize_asset_input(db, row, await db.get(User, uid))
    await assert_research_file_upload_quota(
        db, action.assignee_user_id, blob.size_bytes
    )
    media_type = row.snapshot["version"]["media_type"] or blob.content_type
    alias = AiralogyFile(
        id=uuid4(),
        filename=file.filename,
        content_type=media_type,
        size_bytes=blob.size_bytes,
        checksum_sha256=blob.checksum_sha256,
        protocol_id=node.protocol_id,
        project_id=task.project_id,
        user_id=action.assignee_user_id,
        storage_backend=WORKFLOW_FILE_BACKEND,
    )
    db.add(alias)
    await db.flush()
    receipt = WorkflowFileBinding(
        file_id=alias.id,
        workflow_revision_id=row.workflow_revision_id,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        binding_id=binding.binding_id,
        source_action_id=None,
        source_file_id=None,
        asset_input_id=row.id,
        blob_id=blob.id,
        source_kind="data_asset",
        source_ref={
            "origin": asset_source_ref(row),
            "source_path": list(binding.source_path),
            "target_path": list(binding.target_path),
        },
        snapshot={"file": file_snapshot(alias), "blob": blob_snapshot(blob)},
        created_by_user_id=action.assignee_user_id,
    )
    receipt.digest = canonical_digest(binding_payload(receipt))
    db.add(receipt)
    await db.flush()
    return alias.airalogy_id, {
        "binding_id": binding.binding_id,
        "file_id": alias.airalogy_id,
        "digest": receipt.digest,
        "filename": file.filename,
        "content_type": media_type,
        "size_bytes": blob.size_bytes,
        "sha256": blob.checksum_sha256,
    }


async def resolve_asset_bindings(db, *, task, run, graph, node, action):
    from app.models.protocol_version import ProtocolVersion
    from app.services.workflow_asset_contracts import (
        asset_field_catalog,
        resolve_asset_value,
    )
    from app.services.workflow_assets import authorize_asset_input
    from app.services.workflow_data import protocol_field_catalog
    from app.services.workflow_file_contracts import validate_workflow_file_value

    rows, _ = await asset_rows_for_run(db, task=task, run=run, graph=graph)
    values, refs, receipts, files = {}, {}, [], []
    recipients = [
        await db.get(User, uid)
        for uid in {
            task.owner_user_id,
            run.requested_by_user_id,
            action.assignee_user_id,
        }
    ]
    version = await db.get(ProtocolVersion, node.protocol_version_id)
    targets = protocol_field_catalog(version, for_target=True, include_files=True)
    for binding in graph.asset_bindings:
        if binding.target_node_id != node.node_id:
            continue
        row = rows[binding.input_id]
        for recipient in recipients:
            _, file, blob = await authorize_asset_input(db, row, recipient)
        refs[binding.input_id] = asset_source_ref(row)
        if binding.value_type == "file":
            value, receipt = await materialize_asset_file(
                db,
                task=task,
                run=run,
                node=node,
                action=action,
                binding=binding,
                row=row,
                file=file,
                blob=blob,
            )
            validate_workflow_file_value(value, targets[tuple(binding.target_path)])
            files.append(receipt)
        else:
            value = resolve_asset_value(
                binding,
                row.snapshot["json_value"],
                asset_field_catalog(row.snapshot["version"]["data_schema"]),
            )
        values[binding.target_path[1]] = deepcopy(value)
        receipts.append(
            {
                **binding.model_dump(mode="json"),
                "value": value,
                "value_digest": canonical_digest(value),
            }
        )
    return values, refs, receipts, files
