"""Real database, authorization and worker acceptance for Record analysis.

Run against the dedicated e2e database through research-integration.sh. All
identities/data are synthetic; no provider, permission, SQL or compute is mocked.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import config
from app.models.analysis import AnalysisPipelineRevision, AnalysisPreview, AnalysisRun
from app.models.lab import Lab, LabRole, LabUser
from app.models.project import (
    PermissionType,
    Project,
    ProjectRole,
    ProjectType,
    ProjectUser,
)
from app.models.project_group import ProtocolUser
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.resource import PersistentJob
from app.models.user import User
from app.routers import analyses as api
from app.services import record_analyses
from app.services.analysis_engine import AnalysisRecipe, canonical_digest
from app.services.persistent_jobs import claim_job, complete_job
from app.services.record_analyses import AnalysisPreviewRequest, AnalysisSelection
from app.services.resource_job_worker import process_persistent_job

DATABASE_URL = os.environ.get("RESOURCE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="RESOURCE_TEST_DATABASE_URL is required for real analysis guarantees",
)


@pytest.fixture(autouse=True)
def legacy_role_mode(monkeypatch):
    # Exercise the shipped legacy role matrix, not a substitute permission stub.
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")


@asynccontextmanager
async def database():
    engine = create_async_engine(DATABASE_URL)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def recipe(**changes):
    return AnalysisRecipe(numeric_fields=["value"], group_by=["group"], **changes)


async def seed_analysis(sessions, *, public=False, protocol_level=False):
    users = {}
    async with sessions() as db:
        for name in ("owner", "analyst", "recorder", "outsider"):
            identity = uuid4()
            users[name] = User(
                id=identity,
                username=f"analysis_{identity.hex}",
                email=f"{identity.hex}@example.test",
                password_hash="synthetic-unused-hash",
                api_key_iv="synthetic-unused-iv",
                name=f"Synthetic {name}",
            )
            db.add(users[name])
        await db.flush()
        owner = users["owner"]
        lab = Lab(
            id=uuid4(),
            uid=f"analysis_{uuid4().hex}",
            name="Synthetic analysis Lab",
            create_user_id=owner.id,
        )
        db.add(lab)
        await db.flush()
        project = Project(
            id=uuid4(),
            lab_id=lab.id,
            uid=f"analysis_{uuid4().hex}",
            name="Synthetic analysis Project",
            create_user_id=owner.id,
            type=ProjectType.PUBLIC if public else ProjectType.PRIVATE,
            permission_type=PermissionType.PROTOCOL_LEVEL
            if protocol_level
            else PermissionType.INHERIT,
        )
        db.add(project)
        await db.flush()
        protocol = Protocol(
            id=uuid4(),
            project_id=project.id,
            user_id=owner.id,
            uid=f"analysis_{uuid4().hex}",
            name="Synthetic measurement Protocol",
            latest_version="1.0.0",
        )
        db.add(protocol)
        await db.flush()
        schema = {
            "vars": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "number",
                        "title": "Measured value",
                        "unit": "mg/L",
                    },
                    "group": {"type": "string", "title": "Experimental group"},
                },
            }
        }
        version = ProtocolVersion(
            id=uuid4(),
            protocol_id=protocol.id,
            version="1.0.0",
            json_schema=schema,
            meta_data={"id": protocol.uid, "version": "1.0.0", "name": protocol.name},
            fields={},
            assigners={},
            assigner_graph={},
            aimd="Synthetic measurement",
        )
        db.add(version)
        roles = {
            "owner": ProjectRole.OWNER,
            "analyst": ProjectRole.COLLABORATOR,
            "recorder": ProjectRole.RECORDER_SELF_ONLY
            if public
            else ProjectRole.RECORDER,
        }
        for name, role in roles.items():
            db.add(
                ProjectUser(
                    project_id=project.id,
                    user_id=users[name].id,
                    role=role,
                    create_user_id=owner.id,
                )
            )
            db.add(
                LabUser(
                    lab_id=lab.id,
                    user_id=users[name].id,
                    role=LabRole.OWNER if name == "owner" else LabRole.MEMBER,
                    create_user_id=owner.id,
                )
            )
        await db.commit()
    return SimpleNamespace(
        **users, lab=lab, project=project, protocol=protocol, version=version
    )


async def add_record(
    sessions,
    scope,
    value,
    group="A",
    *,
    author=None,
    record_id=None,
    revision=1,
    number=1,
    protocol_version="1.0.0",
):
    data = {"var": {"value": value, "group": group}}
    record = Record(
        id=record_id or uuid4(),
        version=revision,
        protocol_id=scope.protocol.id,
        protocol_version=protocol_version,
        user_id=(author or scope.owner).id,
        data=data,
        hash=canonical_digest(data),
        number=number,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    async with sessions() as db:
        db.add(record)
        await db.commit()
    return record


async def preview(
    sessions, scope, *, user=None, selection=None, selected_recipe=None, **lineage
):
    async with sessions() as db:
        return await api.preview_record_analysis(
            AnalysisPreviewRequest(
                protocol_id=scope.protocol.id,
                recipe=selected_recipe or recipe(),
                selection=selection or AnalysisSelection(),
                question="Compare synthetic groups",
                **lineage,
            ),
            db,
            user or scope.analyst,
        )


async def confirm(sessions, scope, preview_data, *, user=None, key=None):
    async with sessions() as db:
        return await api.create_record_analysis(
            api.AnalysisConfirmRequest(
                preview_id=preview_data["id"],
                preview_digest=preview_data["preview_digest"],
                client_idempotency_key=key or f"synthetic-{uuid4().hex}",
            ),
            db,
            user or scope.analyst,
        )


async def execute_job(sessions, run):
    worker_id = f"synthetic-analysis-worker-{uuid4().hex}"
    async with sessions() as db:
        job = await claim_job(
            db, worker_id=worker_id, kinds={"record_analysis"}, job_id=run["job_id"]
        )
        assert job is not None
        await db.commit()
    async with sessions() as db:
        job = await db.get(PersistentJob, run["job_id"])
        output = await process_persistent_job(db, job)
        await complete_job(db, job=job, worker_id=worker_id, result=output)
        await db.commit()
    return output


async def get_run(sessions, scope, run_id, *, user=None):
    async with sessions() as db:
        response = Response()
        result = await api.get_record_analysis(
            run_id, db, user or scope.analyst, response
        )
        assert response.headers["Cache-Control"] == "private, no-store"
        return result


def group_stats(result):
    return {
        group["key"][0]["value"]: group["fields"]["value"] for group in result["groups"]
    }


@pytest.mark.parametrize(
    "invalid_schema",
    [None, {"vars": []}, {"properties": []}, {"type": "array"}],
)
def test_analysis_context_rejects_invalid_schema_without_server_error(invalid_schema):
    async def scenario():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            async with sessions() as db:
                version = await db.get(ProtocolVersion, scope.version.id)
                version.json_schema = invalid_schema
                await db.commit()
            async with sessions() as db:
                with pytest.raises(HTTPException) as rejected:
                    await api.get_analysis_context(
                        scope.protocol.id, db, scope.analyst, Response()
                    )
                assert rejected.value.status_code == 422
                assert "Protocol Schema is not analyzable" in rejected.value.detail
                for model in (AnalysisRun, AnalysisPreview):
                    assert (
                        await db.scalar(
                            select(func.count())
                            .select_from(model)
                            .where(model.protocol_id == scope.protocol.id)
                        )
                        == 0
                    )

    asyncio.run(scenario())


def test_preview_confirm_queue_compute_report_and_idempotency():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2, "A", number=1)
            await add_record(sessions, scope, 4, "A", number=2)
            await add_record(sessions, scope, 6, "B", author=scope.recorder, number=3)
            draft = await preview(sessions, scope)
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisPreview)
                        .where(AnalysisPreview.project_id == scope.project.id)
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(PersistentJob)
                        .where(PersistentJob.lab_id == scope.lab.id)
                    )
                    == 0
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisRun)
                        .where(AnalysisRun.project_id == scope.project.id)
                    )
                    == 0
                )
            first = await confirm(sessions, scope, draft, key="first-confirmation")
            same = await confirm(sessions, scope, draft, key="first-confirmation")
            different_key = await confirm(
                sessions, scope, draft, key="second-confirmation"
            )
            assert first["id"] == same["id"] == different_key["id"]
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(PersistentJob)
                        .where(PersistentJob.lab_id == scope.lab.id)
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisRun)
                        .where(AnalysisRun.project_id == scope.project.id)
                    )
                    == 1
                )
            assert (await execute_job(sessions, first))["status"] == "succeeded"
            computed = await get_run(sessions, scope, first["id"])
            assert computed["status"] == "succeeded"
            assert computed["result_digest"] == canonical_digest(computed["result"])
            statistics = group_stats(computed["result"])
            assert statistics["A"]["mean"] == 3
            assert statistics["A"]["count"] == 2
            assert statistics["B"]["mean"] == 6
            assert computed["source_digest"] == canonical_digest(
                computed["source_snapshot"]
            )
            async with sessions() as db:
                downloaded = await api.download_record_analysis(
                    first["id"], db, scope.analyst
                )
                assert downloaded.headers["Cache-Control"] == "private, no-store"
                assert (
                    json.loads(downloaded.body)["result_digest"]
                    == computed["result_digest"]
                )
                job = await db.get(PersistentJob, first["job_id"])
                assert job.status == "succeeded"
                # A duplicate delivery does not recompute or rewrite a result.
                await process_persistent_job(db, job)
                await db.commit()
            repeated = await get_run(sessions, scope, first["id"])
            assert repeated["result"] == computed["result"]
            assert repeated["finished_at"] == computed["finished_at"]

    asyncio.run(exercise())


def test_latest_revision_is_selected_before_filters_and_exact_revision_is_replayable():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            old = await add_record(sessions, scope, 2, number=1)
            await add_record(
                sessions, scope, 20, record_id=old.id, revision=2, number=1
            )
            current = await add_record(sessions, scope, 8, number=2)
            filtered = await preview(
                sessions, scope, selection=AnalysisSelection(filters={"version": 1})
            )
            run = await confirm(sessions, scope, filtered)
            assert [row["record_id"] for row in run["source_snapshot"]["records"]] == [
                str(current.id)
            ]
            explicit = await preview(
                sessions,
                scope,
                selection=AnalysisSelection(
                    mode="selected", records=[{"id": old.id, "version": 1}]
                ),
            )
            exact_run = await confirm(sessions, scope, explicit)
            await execute_job(sessions, exact_run)
            result = await get_run(sessions, scope, exact_run["id"])
            assert result["source_snapshot"]["records"][0]["record_version"] == 1
            assert group_stats(result["result"])["A"]["mean"] == 2

    asyncio.run(exercise())


def test_new_record_stales_latest_preview_but_not_explicit_revision_selection():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            original = await add_record(sessions, scope, 2)
            latest_draft = await preview(sessions, scope)
            exact_draft = await preview(
                sessions,
                scope,
                selection=AnalysisSelection(
                    mode="selected", records=[{"id": original.id, "version": 1}]
                ),
            )
            await add_record(sessions, scope, 99, number=2)
            with pytest.raises(HTTPException) as stale:
                await confirm(sessions, scope, latest_draft)
            assert stale.value.status_code == 409
            exact_run = await confirm(sessions, scope, exact_draft)
            assert len(exact_run["source_snapshot"]["records"]) == 1
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(PersistentJob)
                        .where(PersistentJob.lab_id == scope.lab.id)
                    )
                    == 1
                )

    asyncio.run(exercise())


@pytest.mark.parametrize("public", [False, True])
def test_real_recorder_permissions_filter_sources_and_never_share_reports(public):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=public)
            foreign_record = await add_record(sessions, scope, 99)
            own_record = await add_record(
                sessions, scope, 4, author=scope.recorder, number=2
            )
            draft = await preview(sessions, scope, user=scope.recorder)
            run = await confirm(sessions, scope, draft, user=scope.recorder)
            assert [row["record_id"] for row in run["source_snapshot"]["records"]] == [
                str(own_record.id)
            ]
            with pytest.raises(HTTPException) as rejected:
                await preview(
                    sessions,
                    scope,
                    user=scope.recorder,
                    selection=AnalysisSelection(
                        mode="selected",
                        records=[{"id": foreign_record.id, "version": 1}],
                    ),
                )
            assert rejected.value.status_code == 403
            for different_user in (scope.owner, scope.outsider):
                with pytest.raises(HTTPException) as private:
                    await get_run(sessions, scope, run["id"], user=different_user)
                assert private.value.status_code == 404
            if not public:
                with pytest.raises(HTTPException) as no_membership:
                    await preview(sessions, scope, user=scope.outsider)
                assert no_membership.value.status_code == 403
            async with sessions() as db:
                results = await api.list_record_analyses(
                    scope.project.id,
                    db,
                    scope.outsider,
                    Response(),
                    limit=100,
                    offset=0,
                )
                assert results == {"items": []}
            await execute_job(sessions, run)
            result = await get_run(sessions, scope, run["id"], user=scope.recorder)
            assert group_stats(result["result"])["A"]["mean"] == 4

    asyncio.run(exercise())


@pytest.mark.parametrize("public", [False, True])
def test_protocol_level_grant_is_required_and_revocation_blocks_get_download_and_worker(
    public,
):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=public, protocol_level=True)
            await add_record(sessions, scope, 2)
            with pytest.raises(HTTPException) as public_is_not_a_grant:
                await preview(sessions, scope, user=scope.outsider)
            assert public_is_not_a_grant.value.status_code == 403
            with pytest.raises(HTTPException) as absent_grant:
                await preview(sessions, scope)
            assert absent_grant.value.status_code == 403
            async with sessions() as db:
                db.add(
                    ProtocolUser(
                        protocol_id=scope.protocol.id,
                        user_id=scope.analyst.id,
                        role=ProjectRole.COLLABORATOR,
                        create_user_id=scope.owner.id,
                    )
                )
                await db.commit()
            finished = await confirm(sessions, scope, await preview(sessions, scope))
            await execute_job(sessions, finished)
            queued = await confirm(sessions, scope, await preview(sessions, scope))
            async with sessions() as db:
                await db.execute(
                    delete(ProtocolUser).where(
                        ProtocolUser.protocol_id == scope.protocol.id,
                        ProtocolUser.user_id == scope.analyst.id,
                    )
                )
                await db.commit()
            with pytest.raises(HTTPException) as revoked:
                await get_run(sessions, scope, finished["id"])
            assert revoked.value.status_code == 403
            async with sessions() as db:
                with pytest.raises(HTTPException) as download_revoked:
                    await api.download_record_analysis(
                        finished["id"], db, scope.analyst
                    )
                assert download_revoked.value.status_code == 403
            assert (await execute_job(sessions, queued))["status"] == "failed"
            async with sessions() as db:
                run = await db.get(AnalysisRun, queued["id"])
                assert run.result is None and run.result_digest is None

    asyncio.run(exercise())


def test_saved_pipeline_revisions_rerun_new_data_without_changing_original_result():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            await add_record(sessions, scope, 4, number=2)
            initial = await confirm(sessions, scope, await preview(sessions, scope))
            await execute_job(sessions, initial)
            old = copy.deepcopy(await get_run(sessions, scope, initial["id"]))
            async with sessions() as db:
                saved = await api.create_analysis_pipeline(
                    api.PipelineCreateRequest(
                        run_id=initial["id"], title="Synthetic reusable method"
                    ),
                    db,
                    scope.analyst,
                )
                original_revision = saved["revisions"][0]
                assert original_revision["source_selection"] == old["source_selection"]
                assert {
                    key: value
                    for key, value in original_revision["provenance"].items()
                    if key != "method_digest"
                } == {
                    "engine_version": "airalogy.analysis.v1",
                    "analysis_id": str(initial["id"]),
                    "source_digest": old["source_digest"],
                    "result_digest": old["result_digest"],
                }
                method_digest = original_revision["provenance"]["method_digest"]
                assert len(method_digest) == 64
                assert all(
                    character in "0123456789abcdef" for character in method_digest
                )
                listing = await api.list_analysis_pipelines(
                    scope.project.id, db, scope.analyst, Response(), limit=100, offset=0
                )
                assert (
                    listing["items"][0]["current_revision_id"]
                    == original_revision["id"]
                )
            revised_recipe = recipe(
                filters=[{"field": "value", "op": "gt", "value": 3}]
            )
            async with sessions() as db:
                revision = await api.revise_analysis_pipeline(
                    saved["id"],
                    api.PipelineReviseRequest(
                        expected_revision=1, recipe=revised_recipe
                    ),
                    db,
                    scope.analyst,
                )
                assert revision["revision"] == 2
                assert (
                    revision["source_selection"]
                    == original_revision["source_selection"]
                )
                assert {
                    key: value
                    for key, value in revision["provenance"].items()
                    if key != "method_digest"
                } == {
                    "engine_version": "airalogy.analysis.v1",
                    "parent_revision_id": str(original_revision["id"]),
                    "parent_recipe_digest": original_revision["recipe_digest"],
                }
                assert revision["provenance"]["method_digest"] != method_digest
                assert len(revision["provenance"]["method_digest"]) == 64
                assert all(
                    character in "0123456789abcdef"
                    for character in revision["provenance"]["method_digest"]
                )
            async with sessions() as db:
                with pytest.raises(HTTPException) as stale_revision:
                    await api.revise_analysis_pipeline(
                        saved["id"],
                        api.PipelineReviseRequest(expected_revision=1, recipe=recipe()),
                        db,
                        scope.analyst,
                    )
                assert stale_revision.value.status_code == 409
            await add_record(sessions, scope, 12, number=3)
            new_draft = await preview(
                sessions,
                scope,
                pipeline_revision_id=original_revision["id"],
                rerun_of_id=initial["id"],
            )
            rerun = await confirm(sessions, scope, new_draft)
            await execute_job(sessions, rerun)
            result = await get_run(sessions, scope, rerun["id"])
            assert group_stats(result["result"])["A"]["mean"] == 6
            assert result["pipeline_revision_id"] == original_revision["id"]
            assert result["rerun_of_id"] == initial["id"]
            assert await get_run(sessions, scope, initial["id"]) == old
            async with sessions() as db:
                revisions = list(
                    (
                        await db.scalars(
                            select(AnalysisPipelineRevision)
                            .where(AnalysisPipelineRevision.pipeline_id == saved["id"])
                            .order_by(AnalysisPipelineRevision.revision)
                        )
                    ).all()
                )
                assert [entry.revision for entry in revisions] == [1, 2]
                assert revisions[0].recipe == old["recipe"]
                assert revisions[1].recipe == revised_recipe.model_dump(mode="json")
            with pytest.raises(HTTPException) as mismatched_method:
                await preview(sessions, scope, pipeline_revision_id=revision["id"])
            assert mismatched_method.value.status_code == 409

    asyncio.run(exercise())


def test_schema_change_invalidates_preview_while_confirmed_snapshot_stays_pinned():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            pending = await confirm(sessions, scope, await preview(sessions, scope))
            old_snapshot = copy.deepcopy(pending["source_snapshot"])
            draft = await preview(sessions, scope)
            async with sessions() as db:
                version = await db.get(ProtocolVersion, scope.version.id)
                changed = copy.deepcopy(version.json_schema)
                changed["vars"]["properties"]["value"]["unit"] = "g/L"
                version.json_schema = changed
                await db.commit()
            with pytest.raises(HTTPException) as stale:
                await confirm(sessions, scope, draft)
            assert stale.value.status_code == 409
            await execute_job(sessions, pending)
            report = await get_run(sessions, scope, pending["id"])
            assert report["source_snapshot"] == old_snapshot
            assert report["source_snapshot"]["fields"][0]["unit"] == "mg/L"
            assert group_stats(report["result"])["A"]["mean"] == 2

    asyncio.run(exercise())


def test_cancel_prevents_claim_and_delayed_delivery_cannot_resurrect_analysis():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            run = await confirm(sessions, scope, await preview(sessions, scope))
            async with sessions() as db:
                cancelled = await api.cancel_record_analysis(
                    run["id"], db, scope.analyst
                )
                assert cancelled["status"] == "cancelled"
            async with sessions() as db:
                assert (
                    await claim_job(
                        db,
                        worker_id="synthetic-late-worker",
                        kinds={"record_analysis"},
                        job_id=run["job_id"],
                    )
                    is None
                )
                job = await db.get(PersistentJob, run["job_id"])
                assert job.status == "cancelled"
                output = await process_persistent_job(db, job)
                await db.commit()
                assert output["status"] == "cancelled"
                second = await api.cancel_record_analysis(run["id"], db, scope.analyst)
                assert second["finished_at"] == cancelled["finished_at"]
            unchanged = await get_run(sessions, scope, run["id"])
            assert unchanged["result"] is None and unchanged["result_digest"] is None

    asyncio.run(exercise())


@pytest.mark.parametrize("tampered_part", ["schema", "source", "recipe", "result"])
def test_tampered_report_cannot_be_read_downloaded_or_saved(tampered_part):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            run = await confirm(sessions, scope, await preview(sessions, scope))
            await execute_job(sessions, run)
            async with sessions() as db:
                stored = await db.get(AnalysisRun, run["id"])
                if tampered_part in {"schema", "source"}:
                    snapshot = copy.deepcopy(stored.source_snapshot)
                    if tampered_part == "schema":
                        snapshot["schemas"][0]["json_schema"]["vars"]["properties"][
                            "value"
                        ]["unit"] = "invented-unit"
                    else:
                        snapshot["records"][0]["data"]["var"]["value"] = 999
                    stored.source_snapshot = snapshot
                elif tampered_part == "recipe":
                    stored.recipe = {**stored.recipe, "chart": "none"}
                else:
                    stored.result = {**stored.result, "tampered": True}
                await db.commit()
            with pytest.raises(HTTPException) as read:
                await get_run(sessions, scope, run["id"])
            assert read.value.status_code == 409
            async with sessions() as db:
                with pytest.raises(HTTPException) as download:
                    await api.download_record_analysis(run["id"], db, scope.analyst)
                assert download.value.status_code == 409
            async with sessions() as db:
                with pytest.raises(HTTPException) as save:
                    await api.create_analysis_pipeline(
                        api.PipelineCreateRequest(
                            run_id=run["id"], title="Must not save corrupt result"
                        ),
                        db,
                        scope.analyst,
                    )
                assert save.value.status_code == 409

    asyncio.run(exercise())


def test_concurrent_confirmations_materialize_one_run_and_one_job():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            draft = await preview(sessions, scope)
            first, second = await asyncio.wait_for(
                asyncio.gather(
                    confirm(sessions, scope, draft, key="concurrent-confirmation"),
                    confirm(sessions, scope, draft, key="concurrent-confirmation"),
                ),
                timeout=5,
            )
            assert first["id"] == second["id"]
            assert first["job_id"] == second["job_id"]
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisRun)
                        .where(AnalysisRun.project_id == scope.project.id)
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(PersistentJob)
                        .where(PersistentJob.lab_id == scope.lab.id)
                    )
                    == 1
                )

    asyncio.run(exercise())


def pause_after_real_computation(monkeypatch):
    computed = threading.Event()
    release = threading.Event()
    original = record_analyses.compute_analysis
    computations = []

    def real_compute_with_barrier(*args, **kwargs):
        result = original(*args, **kwargs)
        computations.append(canonical_digest(result))
        computed.set()
        if not release.wait(timeout=5):
            raise AssertionError("Test did not release its bounded compute barrier")
        return result

    monkeypatch.setattr(record_analyses, "compute_analysis", real_compute_with_barrier)
    return computed, release, computations


def test_running_analysis_cancel_discards_late_real_computation(monkeypatch):
    computed, release, computations = pause_after_real_computation(monkeypatch)

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            run = await confirm(sessions, scope, await preview(sessions, scope))
            task = asyncio.create_task(execute_job(sessions, run))
            try:
                assert await asyncio.to_thread(computed.wait, 5)
                async with sessions() as db:
                    stored = await db.get(AnalysisRun, run["id"])
                    assert stored.status == "running"
                async with sessions() as db:
                    cancelled = await asyncio.wait_for(
                        api.cancel_record_analysis(run["id"], db, scope.analyst),
                        timeout=5,
                    )
                    assert cancelled["status"] == "cancelled"
            finally:
                release.set()
            output = await asyncio.wait_for(task, timeout=5)
            assert output["status"] == "cancelled"
            report = await get_run(sessions, scope, run["id"])
            assert report["status"] == "cancelled"
            assert report["result"] is None and report["result_digest"] is None
            assert len(computations) == 1

    asyncio.run(exercise())


def test_expired_final_lease_cannot_seal_result_and_reclaim_recomputes_same_run(
    monkeypatch,
):
    computed, release, computations = pause_after_real_computation(monkeypatch)

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            run = await confirm(sessions, scope, await preview(sessions, scope))
            worker_id = f"synthetic-expiring-worker-{uuid4().hex}"
            async with sessions() as db:
                job = await claim_job(
                    db,
                    worker_id=worker_id,
                    kinds={"record_analysis"},
                    job_id=run["job_id"],
                )
                assert job is not None
                await db.commit()

            async def finish_expiring_attempt():
                async with sessions() as db:
                    job = await db.get(PersistentJob, run["job_id"])
                    result = await process_persistent_job(db, job)
                    try:
                        await complete_job(
                            db, job=job, worker_id=worker_id, result=result
                        )
                    except ValueError as error:
                        await db.rollback()
                        return str(error)
                    await db.commit()
                    raise AssertionError("An expired lease must not publish the result")

            task = asyncio.create_task(finish_expiring_attempt())
            try:
                assert await asyncio.to_thread(computed.wait, 5)
                async with sessions() as db:
                    await db.execute(
                        update(PersistentJob)
                        .where(PersistentJob.id == run["job_id"])
                        .values(
                            lease_expires_at=datetime.now(UTC) - timedelta(seconds=1)
                        )
                    )
                    await db.commit()
            finally:
                release.set()
            assert "lease is expired" in await asyncio.wait_for(task, timeout=5)
            async with sessions() as db:
                stored = await db.get(AnalysisRun, run["id"])
                assert stored.status == "running"
                assert stored.result is None and stored.result_digest is None
            # The second real claim uses the expired lease, not a new Run/Job.
            assert (await execute_job(sessions, run))["status"] == "succeeded"
            report = await get_run(sessions, scope, run["id"])
            assert group_stats(report["result"])["A"]["mean"] == 2
            assert len(computations) == 2
            assert computations[0] == computations[1] == report["result_digest"]
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisRun)
                        .where(AnalysisRun.project_id == scope.project.id)
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(PersistentJob)
                        .where(PersistentJob.lab_id == scope.lab.id)
                    )
                    == 1
                )
                job = await db.get(PersistentJob, run["job_id"])
                assert job.attempts == 2 and job.status == "succeeded"

    asyncio.run(exercise())


@pytest.mark.parametrize("selection_kind", ["protocol_version", "selected"])
def test_saved_old_schema_method_can_be_revised_and_rerun_after_protocol_upgrade(
    selection_kind,
):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            first = await add_record(sessions, scope, 2, number=1)
            await add_record(sessions, scope, 4, number=2)
            selection = (
                AnalysisSelection(filters={"protocol_version": "1.0.0"})
                if selection_kind == "protocol_version"
                else AnalysisSelection(
                    mode="selected", records=[{"id": first.id, "version": 1}]
                )
            )
            initial = await confirm(
                sessions, scope, await preview(sessions, scope, selection=selection)
            )
            await execute_job(sessions, initial)
            old_report = copy.deepcopy(await get_run(sessions, scope, initial["id"]))
            async with sessions() as db:
                saved = await api.create_analysis_pipeline(
                    api.PipelineCreateRequest(
                        run_id=initial["id"], title="Pinned original measurement method"
                    ),
                    db,
                    scope.analyst,
                )
            old_revision = saved["revisions"][0]
            expected_selection = selection.model_dump(mode="json", exclude_none=True)
            assert old_revision["source_selection"] == expected_selection

            # A legitimate subsequent Protocol version uses a different field.
            # The saved method's explicitly pinned sources still use version 1.
            replacement_data = {"var": {"replacement_value": 1000, "group": "A"}}
            async with sessions() as db:
                protocol = await db.get(Protocol, scope.protocol.id)
                protocol.latest_version = "2.0.0"
                db.add(
                    ProtocolVersion(
                        id=uuid4(),
                        protocol_id=protocol.id,
                        version="2.0.0",
                        json_schema={
                            "vars": {
                                "type": "object",
                                "properties": {
                                    "replacement_value": {
                                        "type": "number",
                                        "unit": "g/L",
                                    },
                                    "group": {"type": "string"},
                                },
                            }
                        },
                        meta_data={
                            "id": protocol.uid,
                            "version": "2.0.0",
                            "name": protocol.name,
                        },
                        fields={},
                        assigners={},
                        assigner_graph={},
                        aimd="Synthetic replacement measurement",
                    )
                )
                db.add(
                    Record(
                        id=uuid4(),
                        version=1,
                        protocol_id=protocol.id,
                        protocol_version="2.0.0",
                        user_id=scope.owner.id,
                        data=replacement_data,
                        hash=canonical_digest(replacement_data),
                        number=3,
                    )
                )
                await db.commit()

            revised_recipe = recipe(chart="line")
            async with sessions() as db:
                selected_context = await api.get_selected_analysis_context(
                    scope.protocol.id, selection, db, scope.analyst, Response()
                )
                assert selected_context["protocol_versions"] == ["1.0.0"]
                assert (
                    next(
                        field
                        for field in selected_context["fields"]
                        if field["key"] == "value"
                    )["type"]
                    == "number"
                )
                assert "replacement_value" not in {
                    field["key"] for field in selected_context["fields"]
                }
                revised = await api.revise_analysis_pipeline(
                    saved["id"],
                    api.PipelineReviseRequest(
                        expected_revision=1, recipe=revised_recipe
                    ),
                    db,
                    scope.analyst,
                )
            assert revised["revision"] == 2
            assert revised["source_selection"] == expected_selection
            assert revised["recipe"] == {**old_revision["recipe"], "chart": "line"}

            rerun_preview = await preview(
                sessions,
                scope,
                selection=AnalysisSelection.model_validate(revised["source_selection"]),
                selected_recipe=revised_recipe,
                pipeline_revision_id=revised["id"],
                rerun_of_id=initial["id"],
            )
            rerun = await confirm(sessions, scope, rerun_preview)
            await execute_job(sessions, rerun)
            report = await get_run(sessions, scope, rerun["id"])
            assert report["status"] == "succeeded"
            assert report["result"]["chart"]["type"] == "line"
            assert group_stats(report["result"])["A"]["mean"] == (
                3 if selection_kind == "protocol_version" else 2
            )
            assert report["source_selection"] == expected_selection
            assert {
                row["protocol_version"] for row in report["source_snapshot"]["records"]
            } == {"1.0.0"}
            assert {
                schema["version"] for schema in report["source_snapshot"]["schemas"]
            } == {"1.0.0"}
            assert await get_run(sessions, scope, initial["id"]) == old_report
            async with sessions() as db:
                preserved = await db.get(AnalysisPipelineRevision, old_revision["id"])
                assert preserved.recipe == old_revision["recipe"]
                assert preserved.source_selection == expected_selection

    asyncio.run(exercise())
