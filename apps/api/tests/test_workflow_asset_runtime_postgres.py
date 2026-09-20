"""Real DataAsset versions/managed bytes -> reviewed Workflow Record inputs.

Synthetic ResearchFile fixtures use the real managed storage upload function;
the existing Knowledge import API intentionally accepts PDFs only. DataAsset
creation, versioning, release, Workflow preview/confirm and Record submission use
normal API handlers. No new runtime, permission, Schema or byte check is mocked.
"""

import asyncio
import copy
import hashlib
import io
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.config import config
from app.libs.file_storage import (
    default_storage_backend,
    default_storage_namespace,
    upload_file,
)
from app.libs.lab_force_delete import (
    _delete_lab_workflow_asset_inputs,
    _delete_lab_workflow_file_references,
)
from app.models.airalogy_file import AiralogyFile
from app.models.knowledge import ResearchFile, ResearchFileBlob
from app.models.protocol_version import ProtocolVersion
from app.models.research import ResearchAction, ResearchRun, ResearchTask
from app.models.research_asset import DataAsset, DataAssetVersion
from app.models.workflow_asset import WorkflowRunAssetInput
from app.models.workflow_file import WorkflowFileBinding
from app.routers import airalogy_api, research_assets
from app.routers import workflow_definitions as api
from app.services.workflow_assets import authorize_asset_input
from app.services.workflow_definitions import (
    WorkflowDraft,
    WorkflowRunConfirm,
    WorkflowRunDraft,
)
from app.services.workflow_file_contracts import parse_workflow_file_id
from app.services.workflow_visibility import workflow_action_data_readable
from tests.test_record_analysis_postgres import database, seed_analysis
from tests.test_workflow_definitions_postgres import (
    actions_by_node,
    approve_action,
    create_task,
    get,
    node,
    publish,
    submit_record,
)
from tests.test_workflow_definitions_postgres import pytestmark as workflow_pytestmark
from tests.test_workflow_files_postgres import file_record, file_schema, read_response

pytestmark = workflow_pytestmark


@pytest.fixture(autouse=True)
def deterministic_no_ai(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", False)


def asset_schema():
    return {
        "type": "object",
        "properties": {
            "dose": {"type": "number", "unit": "mg/L", "minimum": 0},
            "synthetic_id": {"type": "string"},
        },
        "required": ["dose", "synthetic_id"],
        "additionalProperties": False,
    }


async def managed_json(sessions, scope, *, value=12.5, shared=None):
    body = (
        shared.body
        if shared
        else json.dumps({"dose": value, "synthetic_id": uuid4().hex}).encode()
    )
    checksum = hashlib.sha256(body).hexdigest()
    key = f"knowledge/blobs/{checksum[:2]}/{checksum}.json"
    if shared is None:
        await upload_file(
            key, io.BytesIO(body), content_type="application/json", length=len(body)
        )
    async with sessions() as db:
        if shared is not None:
            # Physical deduplication retains separate logical files and scopes.
            blob = await db.get(ResearchFileBlob, shared.blob.id)
            assert blob.checksum_sha256 == checksum and blob.size_bytes == len(body)
        else:
            blob = ResearchFileBlob(
                checksum_sha256=checksum,
                content_type="application/json",
                size_bytes=len(body),
                storage_backend=default_storage_backend(),
                storage_namespace=default_storage_namespace(),
                storage_object_key=key,
                extracted_text="",
            )
            db.add(blob)
            await db.flush()
        file = ResearchFile(
            blob_id=blob.id,
            filename=f"synthetic-calibration-{uuid4().hex}.json",
            scope_type="project",
            lab_id=scope.lab.id,
            project_id=scope.project.id,
            visibility="project",
            uploaded_by_user_id=scope.owner.id,
        )
        db.add(file)
        await db.commit()
    return SimpleNamespace(file=file, blob=blob, body=body, value=value)


async def create_asset(sessions, scope, *, value=12.5, shared=None):
    stored = await managed_json(sessions, scope, value=value, shared=shared)
    task = await create_task(sessions, scope)
    params = research_assets.DataAssetDraft(
        task_id=task["id"],
        name=f"Synthetic calibration {uuid4().hex}",
        kind="file",
        research_file_id=stored.file.id,
        media_type="application/json",
        checksum=stored.blob.checksum_sha256,
        byte_size=len(stored.body),
        data_schema=asset_schema(),
        source={"description": "Synthetic explicit source; not a Workflow Action"},
    )
    async with sessions() as db:
        preview = await research_assets.preview_data_asset(params, scope.owner, db)
        asset = await research_assets.create_data_asset(
            research_assets.DataAssetCreate(
                **params.model_dump(), preview_digest=preview["preview_digest"]
            ),
            scope.owner,
            db,
        )
        await research_assets.update_data_asset_status(
            UUID(str(asset["id"])),
            research_assets.DataAssetStatusUpdate(
                expected_status="draft", status="ready"
            ),
            scope.owner,
            db,
        )
    stored.asset_id = UUID(str(asset["id"]))
    stored.version_id = UUID(str(asset["versions"][0]["id"]))
    stored.source_task = task
    return stored


def asset_draft(scope, *, independent=False):
    return WorkflowDraft(
        project_id=scope.project.id,
        title=f"Synthetic exact DataAsset input {uuid4().hex}",
        graph={
            "schema_version": 5,
            "nodes": [
                node(scope, "measure"),
                *([node(scope, "independent")] if independent else []),
            ],
            "edges": [],
            "bindings": [],
            "asset_inputs": [{"input_id": "calibration", "label": "Calibration"}],
            "asset_bindings": [
                {
                    "binding_id": "dose",
                    "input_id": "calibration",
                    "source_path": ["json", "dose"],
                    "target_node_id": "measure",
                    "target_path": ["var", "value"],
                    "value_type": "number",
                    "unit": "mg/L",
                    "cardinality": "one",
                },
                {
                    "binding_id": "raw_file",
                    "input_id": "calibration",
                    "source_path": ["file"],
                    "target_node_id": "measure",
                    "target_path": ["var", "attachment"],
                    "value_type": "file",
                    "cardinality": "one",
                },
            ],
        },
    )


async def setup(
    sessions, *, independent=False, maximum=None, shape="root", shared=None
):
    scope = await seed_analysis(sessions)
    await file_schema(sessions, scope)
    if maximum is not None:
        async with sessions() as db:
            version = await db.get(ProtocolVersion, scope.version.id)
            schema = copy.deepcopy(version.json_schema)
            schema["vars"]["properties"]["value"]["maximum"] = maximum
            version.json_schema = schema
            await db.commit()
            scope.version = version
    stored = await create_asset(sessions, scope, shared=shared)
    params = asset_draft(scope, independent=independent).model_dump(mode="json")
    if shape == "fanout":
        params["graph"]["nodes"].append(node(scope, "replicate"))
        params["graph"]["asset_bindings"].extend(
            [
                {
                    **item,
                    "binding_id": f"replicate_{item['binding_id']}",
                    "target_node_id": "replicate",
                }
                for item in copy.deepcopy(params["graph"]["asset_bindings"])
            ]
        )
    elif shape == "chain":
        params["graph"]["nodes"].append(node(scope, "downstream"))
        params["graph"]["edges"].append(
            {
                "edge_id": "continue",
                "source_node_id": "measure",
                "target_node_id": "downstream",
            }
        )
        params["graph"]["bindings"].append(
            {
                "binding_id": "record_file",
                "source_node_id": "measure",
                "source_path": ["var", "attachment"],
                "target_node_id": "downstream",
                "target_path": ["var", "attachment"],
                "value_type": "file",
                "cardinality": "one",
            }
        )
    else:
        assert shape == "root"
    workflow, _ = await publish(sessions, scope, WorkflowDraft.model_validate(params))
    task = await create_task(sessions, scope)
    params = WorkflowRunDraft(
        workflow_revision_id=workflow["current_revision"]["id"],
        task_id=task["id"],
        expected_task_revision=task["revision"],
        asset_versions={"calibration": stored.version_id},
    )
    return SimpleNamespace(
        scope=scope, stored=stored, workflow=workflow, task=task, params=params
    )


async def run_preview(sessions, case, *, params=None, user=None):
    async with sessions() as db:
        return await api.preview_workflow_run(
            UUID(str(case.workflow["id"])),
            params or case.params,
            user or case.scope.owner,
            db,
        )


def confirmation(case, result):
    return WorkflowRunConfirm(
        **case.params.model_dump(),
        preview_digest=result["preview_digest"],
        idempotency_key=uuid4(),
    )


async def run_confirm(sessions, case, command):
    async with sessions() as db:
        return await api.confirm_workflow_run(
            UUID(str(case.workflow["id"])), command, case.scope.owner, db
        )


async def start(sessions, case):
    result = await run_preview(sessions, case)
    command = confirmation(case, result)
    started = await run_confirm(sessions, case, command)
    actions = await actions_by_node(sessions, started["run_id"])
    return started, actions, command, result


async def persisted_inputs(sessions, run_id):
    async with sessions() as db:
        return list(
            (
                await db.scalars(
                    select(WorkflowRunAssetInput).where(
                        WorkflowRunAssetInput.run_id == UUID(str(run_id))
                    )
                )
            ).all()
        )


async def assert_no_execution(sessions, case):
    async with sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(WorkflowRunAssetInput)
                .where(WorkflowRunAssetInput.task_id == UUID(str(case.task["id"])))
            )
            == 0
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ResearchAction)
                .join(ResearchRun, ResearchRun.id == ResearchAction.run_id)
                .where(ResearchRun.task_id == UUID(str(case.task["id"])))
            )
            == 0
        )


def test_exact_managed_dataasset_json_and_file_fill_a_root_without_a_fake_source_action():
    async def exercise():
        async with database() as sessions:
            sessions.configure(autoflush=False)
            case = await setup(sessions)
            preview = await run_preview(sessions, case)
            await assert_no_execution(sessions, case)
            source = preview["asset_inputs"][0]
            assert source["data_asset_version_id"] == str(case.stored.version_id)
            assert (
                source["version"] == 1
                and source["sha256"] == hashlib.sha256(case.stored.body).hexdigest()
            )
            assert (
                next(
                    item for item in source["bindings"] if item["binding_id"] == "dose"
                )["value"]
                == 12.5
            )
            assert "snapshot" not in source and "storage_object_key" not in json.dumps(
                source
            )
            definition = await get(sessions, case.scope, case.workflow["id"])
            public_graph = json.dumps(definition["current_revision"]["graph"])
            assert str(case.stored.asset_id) not in public_graph
            assert str(case.stored.version_id) not in public_graph

            command = confirmation(case, preview)
            started = await run_confirm(sessions, case, command)
            actions = await actions_by_node(sessions, started["run_id"])
            assert set(actions) == {"measure"}
            action = actions["measure"]
            assert action.status == "proposed"
            values = action.input_data["initial_values"]
            assert values["value"] == 12.5
            alias_id, extension = parse_workflow_file_id(values["attachment"])
            assert extension == "json"
            receipts = await persisted_inputs(sessions, started["run_id"])
            assert (
                len(receipts) == 1
                and receipts[0].data_asset_version_id == case.stored.version_id
            )
            assert receipts[0].snapshot["json_value"] == json.loads(case.stored.body)
            resolution = action.input_data["workflow_resolution"]["receipt"]
            assert resolution["sources"] == {} and resolution["edges"] == []
            assert resolution["asset_sources"]["calibration"][
                "data_asset_version_id"
            ] == str(case.stored.version_id)
            async with sessions() as db:
                file_binding = await db.get(WorkflowFileBinding, alias_id)
                assert file_binding.source_kind == "data_asset"
                assert (
                    file_binding.source_action_id is None
                    and file_binding.source_file_id is None
                )
                assert file_binding.asset_input_id == receipts[0].id
                assert file_binding.blob_id == case.stored.blob.id
                response = await airalogy_api.download_file(
                    values["attachment"], db, case.scope.owner
                )
                assert await read_response(response) == case.stored.body
                assert response.headers["Cache-Control"] == "private, no-store"
            record = await file_record(sessions, case.scope, values)
            await submit_record(sessions, case.scope, action.id, record)
            async with sessions() as db:
                run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                assert run.status == "completed"
                sdk_record = await airalogy_api.get_record(
                    db, case.scope.owner, f"airalogy.id.record.{record.id}.v.1"
                )
                assert sdk_record["data"]["var"]["value"] == 12.5
                assert sdk_record["data"]["var"]["attachment"] == values["attachment"]
            replay = await run_confirm(sessions, case, command)
            assert replay["run_id"] == started["run_id"]
            assert [
                row.id for row in await persisted_inputs(sessions, started["run_id"])
            ] == [receipts[0].id]

    asyncio.run(exercise())


def test_v2_draft_does_not_reinterpret_or_invalidate_the_confirmed_v1():
    async def exercise():
        async with database() as sessions:
            case = await setup(sessions)
            started, actions, command, _ = await start(sessions, case)
            before = (await persisted_inputs(sessions, started["run_id"]))[0]
            next_file = await managed_json(sessions, case.scope, value=90)
            params = research_assets.DataAssetVersionDraft(
                expected_version=1,
                research_file_id=next_file.file.id,
                media_type="application/json",
                checksum=next_file.blob.checksum_sha256,
                byte_size=len(next_file.body),
                data_schema=asset_schema(),
                change_summary="Synthetic new draft; the confirmed v1 remains exact",
            )
            async with sessions() as db:
                preview = await research_assets.preview_data_asset_version(
                    case.stored.asset_id, params, case.scope.owner, db
                )
                versioned = await research_assets.create_data_asset_version(
                    case.stored.asset_id,
                    research_assets.DataAssetVersionCreate(
                        **params.model_dump(), preview_digest=preview["preview_digest"]
                    ),
                    case.scope.owner,
                    db,
                )
                assert (
                    versioned["status"] == "draft" and versioned["current_version"] == 2
                )
            after = (await persisted_inputs(sessions, started["run_id"]))[0]
            assert (
                after.id == before.id
                and after.digest == before.digest
                and after.snapshot == before.snapshot
            )
            action = actions["measure"]
            await approve_action(sessions, case.scope, action.id)
            async with sessions() as db:
                await authorize_asset_input(db, after, case.scope.owner)
                response = await airalogy_api.download_file(
                    action.input_data["initial_values"]["attachment"],
                    db,
                    case.scope.owner,
                )
                assert await read_response(response) == case.stored.body
            replay = await run_confirm(sessions, case, command)
            assert replay["run_id"] == started["run_id"]
            record = await file_record(
                sessions, case.scope, action.input_data["initial_values"]
            )
            await submit_record(sessions, case.scope, action.id, record)
            assert record.data["var"]["value"] == 12.5

    asyncio.run(exercise())


def test_source_metadata_changes_make_preview_stale_and_leave_no_materialization():
    async def exercise():
        async with database() as sessions:
            case = await setup(sessions)
            command = confirmation(case, await run_preview(sessions, case))
            async with sessions() as db:
                version = await db.get(DataAssetVersion, case.stored.version_id)
                version.version_metadata = {"changed_after_preview": True}
                await db.commit()
            with pytest.raises(HTTPException) as stale:
                await run_confirm(sessions, case, command)
            assert stale.value.status_code == 409
            await assert_no_execution(sessions, case)

    asyncio.run(exercise())


def test_concurrent_confirmation_reuses_one_input_and_one_target_action():
    async def exercise():
        async with database() as sessions:
            case = await setup(sessions)
            command = confirmation(case, await run_preview(sessions, case))
            first, second = await asyncio.gather(
                run_confirm(sessions, case, command),
                run_confirm(sessions, case, command),
            )
            assert first["run_id"] == second["run_id"]
            assert len(await persisted_inputs(sessions, first["run_id"])) == 1
            assert len(await actions_by_node(sessions, first["run_id"])) == 1
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowFileBinding)
                        .where(WorkflowFileBinding.run_id == UUID(str(first["run_id"])))
                    )
                    == 1
                )

    asyncio.run(exercise())


def test_restricted_source_blocks_approval_and_sdk_while_independent_card_stays_readable():
    async def exercise():
        async with database() as sessions:
            case = await setup(sessions, independent=True)
            started, actions, _, _ = await start(sessions, case)
            async with sessions() as db:
                file = await db.get(ResearchFile, case.stored.file.id)
                file.visibility = "restricted"
                await db.commit()
            with pytest.raises(HTTPException):
                await approve_action(sessions, case.scope, actions["measure"].id)
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await airalogy_api.download_file(
                        actions["measure"].input_data["initial_values"]["attachment"],
                        db,
                        case.scope.owner,
                    )
                run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                assert not await workflow_action_data_readable(
                    db,
                    run=run,
                    action=actions["measure"],
                    current_user=case.scope.owner,
                    project=case.scope.project,
                )
                assert await workflow_action_data_readable(
                    db,
                    run=run,
                    action=actions["independent"],
                    current_user=case.scope.owner,
                    project=case.scope.project,
                )

    asyncio.run(exercise())


def test_archive_rechecks_exact_source_even_after_approval_and_rejects_record_submission():
    async def exercise():
        async with database() as sessions:
            case = await setup(sessions)
            _, actions, _, _ = await start(sessions, case)
            action = actions["measure"]
            await approve_action(sessions, case.scope, action.id)
            record = await file_record(
                sessions, case.scope, action.input_data["initial_values"]
            )
            async with sessions() as db:
                await research_assets.update_data_asset_status(
                    case.stored.asset_id,
                    research_assets.DataAssetStatusUpdate(
                        expected_status="ready", status="archived"
                    ),
                    case.scope.owner,
                    db,
                )
            with pytest.raises(HTTPException):
                await submit_record(sessions, case.scope, action.id, record)
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await airalogy_api.get_file_url(
                        action.input_data["initial_values"]["attachment"],
                        db,
                        case.scope.owner,
                    )

    asyncio.run(exercise())


@pytest.mark.parametrize("stage", ["after_preview", "after_confirm"])
def test_actual_managed_storage_tampering_is_detected_without_mocked_downloads(stage):
    async def exercise():
        async with database() as sessions:
            case = await setup(sessions)
            command = confirmation(case, await run_preview(sessions, case))
            if stage == "after_confirm":
                started = await run_confirm(sessions, case, command)
                actions = await actions_by_node(sessions, started["run_id"])
            tampered = json.dumps({"dose": 99, "synthetic_id": "tampered"}).encode()
            await upload_file(
                case.stored.blob.storage_object_key,
                io.BytesIO(tampered),
                content_type="application/json",
                length=len(tampered),
                backend=case.stored.blob.storage_backend,
            )
            if stage == "after_preview":
                with pytest.raises(HTTPException) as changed:
                    await run_confirm(sessions, case, command)
                assert changed.value.status_code == 409
                await assert_no_execution(sessions, case)
            else:
                async with sessions() as db:
                    with pytest.raises(HTTPException) as changed:
                        await airalogy_api.download_file(
                            actions["measure"].input_data["initial_values"][
                                "attachment"
                            ],
                            db,
                            case.scope.owner,
                        )
                    assert changed.value.status_code == 409
                with pytest.raises(HTTPException):
                    await approve_action(sessions, case.scope, actions["measure"].id)

    asyncio.run(exercise())


def test_target_schema_constraints_reject_the_run_preview_before_execution():
    async def exercise():
        async with database() as sessions:
            case = await setup(sessions, maximum=3)
            with pytest.raises(HTTPException) as invalid:
                await run_preview(sessions, case)
            assert invalid.value.status_code == 422
            await assert_no_execution(sessions, case)

    asyncio.run(exercise())


def test_input_catalog_and_preview_enforce_project_scope_and_exact_slot_sets():
    async def exercise():
        async with database() as sessions:
            case = await setup(sessions)
            async with sessions() as db:
                response = Response()
                catalog = await api.workflow_asset_versions(
                    case.scope.project.id,
                    case.scope.owner,
                    db,
                    response,
                    offset=0,
                    limit=50,
                )
                assert response.headers["Cache-Control"] == "private, no-store"
                item = next(
                    row
                    for row in catalog["items"]
                    if row["data_asset_version_id"] == str(case.stored.version_id)
                )
                assert {tuple(field["path"]) for field in item["fields"]} >= {
                    ("file",),
                    ("json", "dose"),
                }
                assert "storage_object_key" not in json.dumps(item)
            with pytest.raises(HTTPException):
                await run_preview(sessions, case, user=case.scope.outsider)
            for versions in (
                {},
                {
                    "calibration": case.stored.version_id,
                    "extra": case.stored.version_id,
                },
            ):
                params = WorkflowRunDraft(
                    **{**case.params.model_dump(), "asset_versions": versions}
                )
                with pytest.raises(HTTPException) as invalid:
                    await run_preview(sessions, case, params=params)
                assert invalid.value.status_code == 422
            foreign = await seed_analysis(sessions)
            foreign_asset = await create_asset(sessions, foreign)
            params = WorkflowRunDraft(
                **{
                    **case.params.model_dump(),
                    "asset_versions": {"calibration": foreign_asset.version_id},
                }
            )
            with pytest.raises(HTTPException) as denied:
                await run_preview(sessions, case, params=params)
            assert denied.value.status_code in {403, 404}
            await assert_no_execution(sessions, case)

    asyncio.run(exercise())


def test_bound_version_and_input_receipt_are_database_immutable_but_archival_is_live():
    async def exercise():
        async with database() as sessions:
            case = await setup(sessions)
            started, _, _, _ = await start(sessions, case)
            receipt = (await persisted_inputs(sessions, started["run_id"]))[0]
            for statement, identity in (
                (
                    "UPDATE data_asset_versions SET checksum=:value WHERE id=:id",
                    case.stored.version_id,
                ),
                (
                    "UPDATE workflow_run_asset_inputs SET digest=:value WHERE id=:id",
                    receipt.id,
                ),
                (
                    "UPDATE research_files SET filename=:value WHERE id=:id",
                    case.stored.file.id,
                ),
            ):
                async with sessions() as db:
                    with pytest.raises(DBAPIError):
                        await db.execute(
                            text(statement), {"id": identity, "value": "0" * 64}
                        )
            async with sessions() as db:
                file = await db.get(ResearchFile, case.stored.file.id)
                file.visibility = "restricted"
                await db.commit()
                assert (
                    await db.get(DataAsset, case.stored.asset_id)
                ).current_version == 1
                assert (
                    await db.get(ResearchTask, UUID(str(case.task["id"])))
                ) is not None

    asyncio.run(exercise())


def test_one_exact_asset_fans_out_to_distinct_root_aliases_and_record_occurrences():
    async def exercise():
        async with database() as sessions:
            sessions.configure(autoflush=False)
            case = await setup(sessions, shape="fanout")
            started, actions, command, _ = await start(sessions, case)
            assert set(actions) == {"measure", "replicate"}
            receipts = await persisted_inputs(sessions, started["run_id"])
            assert len(receipts) == 1
            source = receipts[0]
            references, records = [], []
            for number, key in enumerate(("measure", "replicate"), 1):
                action = actions[key]
                assert action.status == "proposed"
                values = action.input_data["initial_values"]
                assert values["value"] == 12.5
                references.append(values["attachment"])
                origin = action.input_data["workflow_resolution"]["receipt"][
                    "asset_sources"
                ]["calibration"]
                assert origin["asset_input_id"] == str(source.id)
                assert origin["data_asset_version_id"] == str(case.stored.version_id)
                assert origin["source_digest"] == source.source_digest
                record = await file_record(sessions, case.scope, values, number=number)
                records.append(record)
                await submit_record(sessions, case.scope, action.id, record)
            assert references[0] != references[1]
            assert records[0].id != records[1].id
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
                assert len(aliases) == 2
                assert {item.asset_input_id for item in aliases} == {source.id}
                assert {item.blob_id for item in aliases} == {case.stored.blob.id}
                assert {item.action_id for item in aliases} == {
                    action.id for action in actions.values()
                }
                assert all(
                    item.source_kind == "data_asset" and item.source_action_id is None
                    for item in aliases
                )
                assert (
                    await db.get(ResearchRun, UUID(str(started["run_id"])))
                ).status == "completed"
                for reference in references:
                    response = await airalogy_api.download_file(
                        reference, db, case.scope.owner
                    )
                    assert await read_response(response) == case.stored.body
            replay = await run_confirm(sessions, case, command)
            assert replay["run_id"] == started["run_id"]
            assert len(await persisted_inputs(sessions, started["run_id"])) == 1
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowFileBinding)
                        .where(
                            WorkflowFileBinding.run_id == UUID(str(started["run_id"]))
                        )
                    )
                    == 2
                )

    asyncio.run(exercise())


def test_dataasset_alias_continues_through_a_real_record_binding_without_losing_source_acl():
    async def exercise():
        async with database() as sessions:
            case = await setup(sessions, shape="chain")
            started, actions, _, _ = await start(sessions, case)
            assert actions["downstream"].status == "blocked"
            first_reference = actions["measure"].input_data["initial_values"][
                "attachment"
            ]
            record = await file_record(
                sessions, case.scope, actions["measure"].input_data["initial_values"]
            )
            await submit_record(sessions, case.scope, actions["measure"].id, record)
            actions = await actions_by_node(sessions, started["run_id"])
            assert actions["measure"].status == "completed"
            assert actions["downstream"].status == "proposed"
            second_reference = actions["downstream"].input_data["initial_values"][
                "attachment"
            ]
            first_id = parse_workflow_file_id(first_reference)[0]
            second_id = parse_workflow_file_id(second_reference)[0]
            assert first_id != second_id
            receipt = (await persisted_inputs(sessions, started["run_id"]))[0]
            async with sessions() as db:
                first = await db.get(WorkflowFileBinding, first_id)
                second = await db.get(WorkflowFileBinding, second_id)
                assert (
                    first.source_kind == "data_asset"
                    and first.asset_input_id == receipt.id
                )
                assert second.source_kind == "record" and second.asset_input_id is None
                assert second.source_action_id == actions["measure"].id
                assert second.source_file_id == first.file_id
                assert first.blob_id == second.blob_id == case.stored.blob.id
                for reference in (first_reference, second_reference):
                    response = await airalogy_api.download_file(
                        reference, db, case.scope.owner
                    )
                    assert await read_response(response) == case.stored.body
                file = await db.get(ResearchFile, case.stored.file.id)
                file.visibility = "restricted"
                await db.commit()
            async with sessions() as db:
                for reference in (first_reference, second_reference):
                    with pytest.raises(HTTPException):
                        await airalogy_api.download_file(
                            reference, db, case.scope.owner
                        )
                    with pytest.raises(HTTPException):
                        await airalogy_api.get_file_url(reference, db, case.scope.owner)
            with pytest.raises(HTTPException):
                await approve_action(sessions, case.scope, actions["downstream"].id)

    asyncio.run(exercise())


def test_precise_lab_cleanup_removes_only_its_aliases_then_input_receipts_and_rolls_back():
    async def exercise():
        async with database() as sessions:
            first = await setup(sessions)
            first_run, first_actions, _, _ = await start(sessions, first)
            second = await setup(sessions, shared=first.stored)
            second_run, second_actions, _, _ = await start(sessions, second)
            assert first.scope.lab.id != second.scope.lab.id
            assert first.stored.file.id != second.stored.file.id
            assert first.stored.blob.id == second.stored.blob.id
            first_input = (await persisted_inputs(sessions, first_run["run_id"]))[0]
            second_input = (await persisted_inputs(sessions, second_run["run_id"]))[0]
            first_reference = first_actions["measure"].input_data["initial_values"][
                "attachment"
            ]
            second_reference = second_actions["measure"].input_data["initial_values"][
                "attachment"
            ]
            first_alias = parse_workflow_file_id(first_reference)[0]
            second_alias = parse_workflow_file_id(second_reference)[0]
            async with sessions() as db:
                with pytest.raises(ValueError, match="aliases must be removed"):
                    await _delete_lab_workflow_asset_inputs(db, first.scope.lab.id)
            async with sessions() as db:
                savepoint = await db.begin_nested()
                try:
                    await _delete_lab_workflow_file_references(db, first.scope.lab.id)
                    await _delete_lab_workflow_asset_inputs(db, first.scope.lab.id)
                    assert (
                        await db.scalar(
                            select(WorkflowFileBinding.file_id).where(
                                WorkflowFileBinding.file_id == first_alias
                            )
                        )
                        is None
                    )
                    assert (
                        await db.scalar(
                            select(AiralogyFile.id).where(
                                AiralogyFile.id == first_alias
                            )
                        )
                        is None
                    )
                    assert (
                        await db.scalar(
                            select(WorkflowRunAssetInput.id).where(
                                WorkflowRunAssetInput.id == first_input.id
                            )
                        )
                        is None
                    )
                    assert await db.get(ResearchFile, first.stored.file.id) is not None
                    assert (
                        await db.get(DataAssetVersion, first.stored.version_id)
                        is not None
                    )
                    assert (
                        await db.get(ResearchFileBlob, first.stored.blob.id) is not None
                    )
                    assert await db.get(WorkflowFileBinding, second_alias) is not None
                    assert await db.get(AiralogyFile, second_alias) is not None
                    assert (
                        await db.get(WorkflowRunAssetInput, second_input.id) is not None
                    )
                    assert await db.get(ResearchFile, second.stored.file.id) is not None
                    # Download commits its audit, so it must not own the cleanup
                    # transaction whose all-or-nothing rollback is under test.
                    async with sessions() as download_db:
                        response = await airalogy_api.download_file(
                            second_reference, download_db, second.scope.owner
                        )
                        assert await read_response(response) == first.stored.body
                finally:
                    await savepoint.rollback()
                assert (
                    await db.scalar(
                        select(WorkflowFileBinding.file_id).where(
                            WorkflowFileBinding.file_id == first_alias
                        )
                    )
                    == first_alias
                )
                assert (
                    await db.scalar(
                        select(WorkflowRunAssetInput.id).where(
                            WorkflowRunAssetInput.id == first_input.id
                        )
                    )
                    == first_input.id
                )
                response = await airalogy_api.download_file(
                    first_reference, db, first.scope.owner
                )
                assert await read_response(response) == first.stored.body

    asyncio.run(exercise())
