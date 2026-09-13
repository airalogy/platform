"""Real persisted Workflow file flow, source ACLs, private storage and receipts."""

import asyncio
import copy
import hashlib
import io
import json
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from starlette.datastructures import Headers

from app.config import config
from app.models.airalogy_file import AiralogyFile
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.research import ResearchTask
from app.models.research_execution import ResearchComputeJobOutput
from app.models.workflow_file import WorkflowFileBinding, WorkflowFileExportReference
from app.routers import (
    airalogy_api,
    airalogy_files,
    record_exports,
    records,
    research_tasks,
    workflow_files,
)
from app.services import workflow_files as file_service
from app.services.record_exports import _file_payload_specs, process_record_export
from app.services.research_runtime import canonical_digest
from app.services.workflow_definitions import WorkflowDraft
from tests.test_analysis_compute_runtime_postgres import (
    completion,
    download_and_start,
    execute_container,
    lease,
    submit_completion,
    upload,
)
from tests.test_record_analysis_postgres import add_record, database, seed_analysis
from tests.test_workflow_compute_methods_postgres import (
    compute_graph,
    publish_compute_method,
    saved_compute_method,
)
from tests.test_workflow_compute_runtime_postgres import queued
from tests.test_workflow_definitions_postgres import (
    actions_by_node,
    approve_action,
    create_task,
    edge,
    node,
    publish,
    start_workflow,
    submit_record,
)
from tests.test_workflow_definitions_postgres import (
    deterministic_no_ai as deterministic_no_ai,
)
from tests.test_workflow_definitions_postgres import pytestmark as pytestmark


def binding(
    source,
    target,
    *,
    source_field="attachment",
    target_field="attachment",
    kind="var",
    identity="file_input",
):
    return {
        "binding_id": identity,
        "source_node_id": source,
        "source_path": [kind, source_field],
        "target_node_id": target,
        "target_path": ["var", target_field],
        "value_type": "file",
        "cardinality": "one",
    }


async def file_schema(sessions, scope):
    async with sessions() as db:
        version = await db.get(ProtocolVersion, scope.version.id)
        schema = copy.deepcopy(version.json_schema)
        for key in ("attachment", "attachment_copy"):
            schema["vars"]["properties"][key] = {
                "type": "string",
                "airalogy_type": "FileId",
                "file_extension": "json",
            }
        version.json_schema = schema
        await db.commit()
        scope.version = version


async def source_upload(
    sessions, scope, *, filename="input.json", content=b'{"measurement":9}'
):
    async with sessions() as db:
        return await airalogy_files.upload_airalogy_file(
            db,
            scope.owner,
            UploadFile(
                file=io.BytesIO(content),
                filename=filename,
                size=len(content),
                headers=Headers({"content-type": "application/json"}),
            ),
            scope.protocol.id,
        )


async def file_record(sessions, scope, data, *, number=1):
    record = await add_record(sessions, scope, 9, author=scope.owner, number=number)
    async with sessions() as db:
        actual = await db.get(Record, (record.id, record.version))
        actual.data = {"var": {"value": 9, "group": "A", **data}}
        actual.hash = canonical_digest(actual.data)
        await db.commit()
        return actual


async def setup_files(sessions, *, double=False, chain=False, submit=True):
    scope = await seed_analysis(sessions, public=True)
    await file_schema(sessions, scope)
    nodes = [node(scope, "source"), node(scope, "next")]
    edges = [edge("source", "next")]
    bindings = [binding("source", "next")]
    if double:
        bindings.append(
            binding(
                "source", "next", target_field="attachment_copy", identity="second_file"
            )
        )
    if chain:
        nodes.append(node(scope, "final"))
        edges.append(edge("next", "final"))
        bindings.append(binding("next", "final", identity="continued_file"))
    workflow, _ = await publish(
        sessions,
        scope,
        WorkflowDraft(
            project_id=scope.project.id,
            title="Synthetic explicit file binding",
            graph={
                "schema_version": 4,
                "nodes": nodes,
                "edges": edges,
                "bindings": bindings,
            },
        ),
    )
    task = await create_task(sessions, scope)
    started, _ = await start_workflow(sessions, scope, workflow, task)
    uploaded = await source_upload(sessions, scope)
    source_record = await file_record(
        sessions, scope, {"attachment": uploaded["airalogy_file_id"]}
    )
    actions = await actions_by_node(sessions, started["run_id"])
    if submit:
        await submit_record(sessions, scope, actions["source"].id, source_record)
        actions = await actions_by_node(sessions, started["run_id"])
    return scope, started, actions, source_record, uploaded


async def read_response(response):
    return b"".join(
        [
            chunk if isinstance(chunk, bytes) else chunk.encode()
            async for chunk in response.body_iterator
        ]
    )


async def revoke_source(sessions, record):
    async with sessions() as db:
        stored = await db.get(Record, (record.id, record.version))
        stored.deleted_at = datetime.now(UTC).replace(tzinfo=None)
        await db.commit()


def test_file_bindings_fanout_chain_preserve_bytes_seals_and_source_permission():
    async def exercise():
        async with database() as sessions:
            sessions.configure(autoflush=False)
            scope, started, actions, source, uploaded = await setup_files(
                sessions, double=True, chain=True
            )
            assert actions["next"].status == "proposed"
            values = actions["next"].input_data["initial_values"]
            assert (
                values["attachment"]
                != values["attachment_copy"]
                != uploaded["airalogy_file_id"]
            )
            assert (
                actions["source"].output_data["record"]["data"]["var"]["attachment"]
                == uploaded["airalogy_file_id"]
            )
            receipt = actions["next"].input_data["workflow_resolution"]["receipt"]
            assert len(receipt["files"]) == 2
            assert {item["value"] for item in receipt["bindings"]} == set(
                values.values()
            )
            next_record = await file_record(sessions, scope, values, number=2)
            await submit_record(sessions, scope, actions["next"].id, next_record)
            actions = await actions_by_node(sessions, started["run_id"])
            final_id = file_service.parse_workflow_file_id(
                actions["final"].input_data["initial_values"]["attachment"]
            )[0]
            async with sessions() as db:
                aliases = list(
                    (
                        await db.scalars(
                            select(WorkflowFileBinding).where(
                                WorkflowFileBinding.run_id
                                == UUID(str(started["run_id"]))
                            )
                        )
                    ).all()
                )
                assert (
                    len(aliases) == 3 and len({item.blob_id for item in aliases}) == 1
                )
                payload = await airalogy_files.get_airalogy_file_url(
                    final_id, db, scope.owner
                )
                assert (
                    payload["workflow_managed"] is True
                    and "/api/workflow-files/" in payload["url"]
                )
                token = parse_qs(urlsplit(payload["url"]).query)["token"][0]
                response = await workflow_files.preview_workflow_file(
                    final_id, token, db
                )
                assert await read_response(response) == b'{"measurement":9}'
                assert response.headers["Cache-Control"] == "private, no-store"
            async with sessions() as db:
                with pytest.raises(HTTPException) as restricted:
                    await airalogy_files.get_airalogy_file_url(
                        final_id, db, scope.recorder
                    )
                assert restricted.value.status_code in {400, 403}
            async with sessions() as db:
                for file_id in (final_id, UUID(str(uploaded["id"]))):
                    with pytest.raises(HTTPException) as immutable:
                        await airalogy_files.update_airalogy_file_url(
                            file_id, "changed.json", db, scope.owner
                        )
                    assert immutable.value.status_code == 409
            async with sessions() as db:
                with pytest.raises(
                    DBAPIError, match="Workflow-bound file metadata is immutable"
                ):
                    await db.execute(
                        text(
                            "UPDATE airalogy_files SET filename='changed.json' WHERE id=:id"
                        ),
                        {"id": final_id},
                    )
            await revoke_source(sessions, source)
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await workflow_files.preview_workflow_file(final_id, token, db)
                with pytest.raises(HTTPException):
                    await airalogy_api.get_file_url(
                        f"airalogy.id.file.{final_id}.json", db, scope.owner
                    )
                with pytest.raises(HTTPException):
                    await airalogy_api.download_file(
                        f"airalogy.id.file.{final_id}.json", db, scope.owner
                    )
                detail = jsonable_encoder(
                    await research_tasks.get_research_task(
                        UUID(str(started["task_id"])), scope.owner, db
                    )
                )
                assert detail["workflow_data_restricted"] is True

    asyncio.run(exercise())


def test_unbound_airalogy_file_metadata_and_rename_remain_editable():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            uploaded = await source_upload(sessions, scope)
            file_id = UUID(str(uploaded["id"]))
            async with sessions() as db:
                file = await db.get(AiralogyFile, file_id)
                file.storage_metadata = {"description": "Synthetic editable upload"}
                await db.commit()
                file.storage_metadata = {"description": "Updated metadata"}
                await db.commit()
                renamed = await airalogy_files.update_airalogy_file_url(
                    file_id, "renamed.json", db, scope.owner
                )
                assert renamed["filename"] == "renamed.json"

    asyncio.run(exercise())


def test_file_binding_record_submission_cannot_replace_the_approved_reference():
    async def exercise():
        async with database() as sessions:
            scope, started, actions, _, uploaded = await setup_files(sessions)
            changed = await file_record(
                sessions, scope, {"attachment": uploaded["airalogy_file_id"]}, number=2
            )
            with pytest.raises(HTTPException) as rejected:
                await submit_record(sessions, scope, actions["next"].id, changed)
            assert rejected.value.status_code == 409
            accepted = await file_record(
                sessions, scope, actions["next"].input_data["initial_values"], number=3
            )
            await submit_record(sessions, scope, actions["next"].id, accepted)
            async with sessions() as db:
                assert (
                    await db.get(ResearchTask, UUID(str(started["task_id"])))
                ).status == "review_required"

    asyncio.run(exercise())


def test_file_binding_quota_stops_activation_without_losing_source_record(monkeypatch):
    async def exercise():
        async with database() as sessions:
            scope, started, actions, source, _ = await setup_files(
                sessions, submit=False
            )
            monkeypatch.setattr(config, "KNOWLEDGE_USER_FILE_COUNT_LIMIT", 0)
            await submit_record(sessions, scope, actions["source"].id, source)
            async with sessions() as db:
                assert (
                    await db.get(ResearchTask, UUID(str(started["task_id"])))
                ).status == "paused"
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowFileBinding)
                        .where(
                            WorkflowFileBinding.run_id == UUID(str(started["run_id"]))
                        )
                    )
                    == 0
                )
            actions = await actions_by_node(sessions, started["run_id"])
            assert (
                actions["source"].status == "completed"
                and actions["next"].status == "blocked"
            )

    asyncio.run(exercise())


def test_file_binding_storage_tamper_is_rejected_before_download(monkeypatch):
    async def exercise():
        async with database() as sessions:
            scope, _, actions, _, _ = await setup_files(sessions)
            identity = file_service.parse_workflow_file_id(
                actions["next"].input_data["initial_values"]["attachment"]
            )[0]

            async def changed_bytes(*args, **kwargs):
                yield b"tampered"

            monkeypatch.setattr(file_service, "get_file_with_stream", changed_bytes)
            async with sessions() as db:
                with pytest.raises(HTTPException) as rejected:
                    await airalogy_files.download_airalogy_file(
                        identity, db, scope.owner
                    )
                assert rejected.value.status_code == 409
            with pytest.raises(HTTPException):
                await approve_action(sessions, scope, actions["next"].id)

    asyncio.run(exercise())


def test_file_binding_export_metadata_archive_bytes_and_final_download_recheck_acl(
    tmp_path,
):
    async def exercise():
        async with database() as sessions:
            scope, started, actions, source, _ = await setup_files(sessions)
            values = actions["next"].input_data["initial_values"]
            destination = await file_record(sessions, scope, values, number=2)
            await submit_record(sessions, scope, actions["next"].id, destination)
            path = tmp_path / "record.json"
            path.write_text(
                json.dumps(
                    {
                        "record_id": str(destination.id),
                        "record_version": 1,
                        "data": destination.data,
                    }
                )
            )
            async with sessions() as db:
                specs, warnings = await _file_payload_specs(
                    db, [path], tmp_path, include_attachments=True, user=scope.owner
                )
                assert not warnings and len(specs) == 1
                from pathlib import Path

                assert Path(specs[0]["path"]).read_bytes() == b'{"measurement":9}'
                params = record_exports.RecordExportCreateParams(
                    scope_type="protocol",
                    lab_id=scope.lab.id,
                    project_id=scope.project.id,
                    protocol_id=scope.protocol.id,
                    export_format="jsonl",
                )
                created = await record_exports.create_export(params, db, scope.owner)
                export_id = UUID(str(created["id"]))
            async with sessions() as db:
                await process_record_export(db, export_id)
                # The production worker commits processing together with its job
                # acknowledgement; this direct-handler test owns that boundary.
                await db.commit()
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowFileExportReference)
                        .where(WorkflowFileExportReference.export_id == export_id)
                    )
                    == 1
                )
                payload = await record_exports.create_download_url(
                    export_id, db, scope.owner
                )
                assert "/workflow-files/exports/" in payload["url"]
                token = parse_qs(urlsplit(payload["url"]).query)["token"][0]
                result = await workflow_files.download_workflow_record_export(
                    export_id, token, db
                )
                assert values["attachment"].encode() in await read_response(result)
            await revoke_source(sessions, source)
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await record_exports.create_download_url(export_id, db, scope.owner)
                with pytest.raises(HTTPException):
                    await workflow_files.download_workflow_record_export(
                        export_id, token, db
                    )
                with pytest.raises(HTTPException):
                    await _file_payload_specs(
                        db, [path], tmp_path, include_attachments=True, user=scope.owner
                    )
                with pytest.raises(HTTPException):
                    await records.create_protocol_record(
                        scope.protocol.id,
                        records.RecordCreateParams(
                            var={"unrelated": [values["attachment"]]},
                            step={},
                            check={},
                            report="",
                        ),
                        scope.owner,
                        db,
                    )
                identity = str(
                    file_service.parse_workflow_file_id(values["attachment"])[0]
                )
                for spelling in (
                    f"airalogy.id.file.{identity.upper()}.JSON",
                    f"airalogy.id.file.{identity}.json.extra",
                ):
                    with pytest.raises(HTTPException):
                        await records.create_protocol_record(
                            scope.protocol.id,
                            records.RecordCreateParams(
                                var={"unrelated": [spelling]},
                                step={},
                                check={},
                                report="",
                            ),
                            scope.owner,
                            db,
                        )

    asyncio.run(exercise())


async def compute_file_workflow(sessions, *, real_engine=False):
    f, saved, _ = await saved_compute_method(sessions, real_engine=real_engine)
    method, _ = await publish_compute_method(sessions, f, saved)
    async with sessions() as db:
        target = Protocol(
            id=uuid4(),
            project_id=f.scope.project.id,
            user_id=f.scope.owner.id,
            uid=f"file_target_{uuid4().hex}",
            name="Synthetic file receiver",
            latest_version="1.0.0",
        )
        db.add(target)
        await db.flush()
        version = ProtocolVersion(
            id=uuid4(),
            protocol_id=target.id,
            version="1.0.0",
            json_schema={
                "vars": {
                    "type": "object",
                    "properties": {
                        "attachment": {
                            "type": "string",
                            "airalogy_type": "FileId",
                            "file_extension": "json",
                        }
                    },
                }
            },
            fields={},
            assigners={},
            assigner_graph={},
            aimd="Synthetic output file",
            meta_data={"id": target.uid, "version": "1.0.0", "name": target.name},
        )
        db.add(version)
        await db.commit()
    target_scope = SimpleNamespace(
        **{**vars(f.scope), "protocol": target, "version": version}
    )
    graph = compute_graph(f, method)
    graph["schema_version"] = 4
    graph["nodes"][1]["compute_file_outputs"] = [
        {"output_id": "summary_file", "mount_name": "summary.json"}
    ]
    graph["nodes"].append(node(target_scope, "next"))
    graph["edges"].append(edge("analysis", "next"))
    graph["bindings"] = [
        binding("analysis", "next", source_field="summary_file", kind="analysis")
    ]
    workflow, _ = await publish(
        sessions,
        f.scope,
        WorkflowDraft(
            project_id=f.scope.project.id,
            title="Explicit Compute file output",
            graph=graph,
        ),
    )
    draft = research_tasks.ResearchTaskDraft(
        project_id=f.scope.project.id,
        title="Synthetic files",
        goal="Execute the confirmed file-producing method",
        success_criteria=["Exact output file is handed to next Protocol"],
        protocol_ids=[f.scope.protocol.id, target.id],
        compute_environment_revision_ids=[f.compute.revision.id],
        budget_limit="1",
        budget_currency="USD",
    )
    async with sessions() as db:
        preview = await research_tasks.preview_research_task(draft, f.scope.owner, db)
        task = await research_tasks.create_research_task(
            research_tasks.ResearchTaskCreate(
                **draft.model_dump(), preview_digest=preview["preview_digest"]
            ),
            f.scope.owner,
            db,
        )
    started, _ = await start_workflow(sessions, f.scope, workflow, task)
    actions = await actions_by_node(sessions, started["run_id"])
    record = await add_record(sessions, f.scope, 9, author=f.scope.owner, number=5)
    await submit_record(sessions, f.scope, actions["source"].id, record)
    f.records = [record]
    return f, target_scope, started, await actions_by_node(sessions, started["run_id"])


@pytest.mark.parametrize(
    "real_engine",
    [
        False,
        pytest.param(
            True,
            marks=pytest.mark.skipif(
                os.environ.get("COMPUTE_ENGINE_TEST") != "1",
                reason="Requires the fixed OCI Python integration environment",
            ),
        ),
    ],
)
def test_compute_file_binding_uses_actual_private_output_without_publishing_blob(
    real_engine,
):
    async def exercise():
        async with database() as sessions:
            sessions.configure(autoflush=False)
            f, target, started, actions = await compute_file_workflow(
                sessions, real_engine=real_engine
            )
            job = await queued(sessions, f, actions)
            delivery = await lease(sessions, f)
            input_bytes = await download_and_start(sessions, f, delivery)
            if real_engine:
                result, payload = execute_container(delivery, input_bytes)
            else:
                result = {"mean": 9.0, "count": 1, "uid": 65532}
                payload = json.dumps(result).encode()
            await upload(sessions, f, delivery, payload)
            receipt = completion(delivery, result, payload)
            await submit_completion(sessions, f, delivery, receipt)
            await submit_completion(sessions, f, delivery, receipt)
            actions = await actions_by_node(sessions, started["run_id"])
            assert actions["next"].status == "proposed"
            values = actions["next"].input_data["initial_values"]
            alias_id = file_service.parse_workflow_file_id(values["attachment"])[0]
            async with sessions() as db:
                linked = await db.get(WorkflowFileBinding, alias_id)
                output = await db.scalar(
                    select(ResearchComputeJobOutput).where(
                        ResearchComputeJobOutput.compute_job_id == job.id
                    )
                )
                assert (
                    linked.source_kind == "compute" and linked.blob_id == output.blob_id
                )
                assert (
                    output.research_file_id is None
                    and output.data_asset_id is None
                    and output.data_asset_version_id is None
                )
                response = await airalogy_files.download_airalogy_file(
                    alias_id, db, f.scope.owner
                )
                assert await read_response(response) == payload
                assert (
                    linked.snapshot["blob"]["sha256"]
                    == hashlib.sha256(payload).hexdigest()
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowFileBinding)
                        .where(
                            WorkflowFileBinding.run_id == UUID(str(started["run_id"]))
                        )
                    )
                    == 1
                )
                with pytest.raises(HTTPException):
                    await airalogy_files.get_airalogy_file_url(
                        alias_id, db, f.scope.recorder
                    )
            next_record = await file_record(sessions, target, values, number=1)
            await submit_record(sessions, target, actions["next"].id, next_record)
            async with sessions() as db:
                assert (
                    await db.get(ResearchTask, UUID(str(started["task_id"])))
                ).status == "review_required"

    asyncio.run(exercise())
