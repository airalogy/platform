"""Real private Project analyses: exact sources, persistent worker and revisions."""

import asyncio
import json
import os
import threading
from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, func, select
from sqlalchemy.exc import DBAPIError

from app.config import config
from app.models.analysis import (
    AnalysisInterpretationRevision,
    AnalysisProjectInput,
    AnalysisRun,
)
from app.models.project import ProjectUser
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.resource import PersistentJob
from app.routers import analyses as legacy
from app.routers import project_analyses as api
from app.services import project_analysis_engine
from app.services.analysis_engine import AnalysisRecipe, canonical_digest
from app.services.project_analyses import (
    ProjectInterpretationRequest,
    ProjectPreviewRequest,
)
from app.services.project_analysis_engine import ProjectAnalysisRecipe
from app.services.record_analyses import AnalysisSelection
from tests.test_record_analysis_postgres import (
    add_record,
    database,
    execute_job,
    seed_analysis,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Dedicated PostgreSQL is required for Project analysis acceptance",
)


@pytest.fixture(autouse=True)
def flat_permissions(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")


async def project_scope(sessions, *, public=False):
    scope = await seed_analysis(sessions, public=public)
    async with sessions() as db:
        second = Protocol(
            id=uuid4(),
            project_id=scope.project.id,
            user_id=scope.owner.id,
            uid=f"project_analysis_{uuid4().hex}",
            name="Synthetic second measurement",
            latest_version="1.0.0",
        )
        db.add(second)
        await db.flush()
        version = ProtocolVersion(
            id=uuid4(),
            protocol_id=second.id,
            version="1.0.0",
            json_schema=deepcopy(scope.version.json_schema),
            meta_data={"id": second.uid, "version": "1.0.0", "name": second.name},
            fields={},
            assigners={},
            assigner_graph={},
            aimd="Synthetic independent measurement",
        )
        db.add(version)
        await db.commit()
    second_scope = SimpleNamespace(
        **{**vars(scope), "protocol": second, "version": version}
    )
    records = [
        await add_record(sessions, scope, 2, "S1"),
        await add_record(sessions, scope, 4, "S2", number=2),
        await add_record(sessions, second_scope, 10, "S1"),
        await add_record(sessions, second_scope, 20, "S2", number=2),
    ]
    return SimpleNamespace(scope=scope, second=second_scope, records=records)


def project_recipe(*, relational=False):
    local = AnalysisRecipe(numeric_fields=["value"], group_by=[]).model_dump(
        mode="json"
    )
    value = {
        "mode": "relational" if relational else "evidence_synthesis",
        "slots": [
            {"slot_id": "first", "label": "First measurement", "recipe": local},
            {"slot_id": "second", "label": "Second measurement", "recipe": local},
        ],
    }
    if relational:
        value["join"] = {
            "left_slot_id": "first",
            "right_slot_id": "second",
            "kind": "inner",
            "keys": [{"left_field": "group", "right_field": "group"}],
            "semantic_alignment_confirmed": True,
            "outputs": [
                {
                    "output_id": "left_value",
                    "slot_id": "first",
                    "field": "value",
                    "semantic_label": "First measurement",
                    "unit": "mg/L",
                },
                {
                    "output_id": "right_value",
                    "slot_id": "second",
                    "field": "value",
                    "semantic_label": "Second measurement",
                    "unit": "mg/L",
                },
            ],
            "recipe": AnalysisRecipe(
                numeric_fields=["left_value", "right_value"], group_by=[]
            ).model_dump(mode="json"),
        }
    return ProjectAnalysisRecipe.model_validate(value)


def project_selection(fixture, *, exact=False):
    inputs = []
    for slot, scope, records in (
        ("first", fixture.scope, fixture.records[:2]),
        ("second", fixture.second, fixture.records[2:]),
    ):
        selected = (
            {
                "mode": "selected",
                "records": [{"id": row.id, "version": row.version} for row in records],
            }
            if exact
            else {"mode": "latest"}
        )
        inputs.append(
            {"slot_id": slot, "protocol_id": scope.protocol.id, "selection": selected}
        )
    return {"inputs": inputs}


async def preview_project(sessions, fixture, *, user=None, **changes):
    params = ProjectPreviewRequest(
        **{
            "project_id": fixture.scope.project.id,
            "selection": project_selection(fixture),
            "recipe": project_recipe(),
            "question": "Do these two measurements agree?",
            **changes,
        }
    )
    async with sessions() as db:
        return jsonable_encoder(
            await api.preview_project_record_analysis(
                params, db, user or fixture.scope.analyst, Response()
            )
        )


async def confirm_project(sessions, fixture, preview, *, key=None, user=None):
    async with sessions() as db:
        return jsonable_encoder(
            await api.create_project_record_analysis(
                legacy.AnalysisConfirmRequest(
                    preview_id=preview["id"],
                    preview_digest=preview["preview_digest"],
                    client_idempotency_key=key or f"project-analysis-{uuid4().hex}",
                ),
                db,
                user or fixture.scope.analyst,
                Response(),
            )
        )


async def computed_project(sessions, fixture, **changes):
    run = await confirm_project(
        sessions, fixture, await preview_project(sessions, fixture, **changes)
    )
    await execute_job(sessions, {**run, "job_id": UUID(run["job_id"])})
    async with sessions() as db:
        return jsonable_encoder(
            await legacy.get_record_analysis(
                UUID(run["id"]), db, fixture.scope.analyst, Response()
            )
        )


def human_interpretation(
    result_digest,
    *,
    expected=0,
    summary="The two independent sources are not sufficient for a causal conclusion.",
):
    return ProjectInterpretationRequest(
        expected_revision=expected,
        result_digest=result_digest,
        content={
            "judgement": "inconclusive",
            "summary": summary,
            "findings": [
                {
                    "slot_id": slot,
                    "field": "value",
                    "relation": "inconclusive",
                    "note": "Observed numeric evidence.",
                }
                for slot in ("first", "second")
            ],
            "limitations": ["Synthetic data is not scientific validation."],
            "unanswered_questions": ["Is the association causal?"],
        },
    )


def test_project_analysis_real_worker_saved_method_rerun_interpretation_and_export():
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions)
            run = await computed_project(sessions, f)
            assert run["source_scope"] == "project" and run["protocol_id"] is None
            assert run["status"] == "succeeded"
            by_slot = {row["slot_id"]: row for row in run["result"]["local_results"]}
            assert (
                by_slot["first"]["report"]["groups"][0]["fields"]["value"]["mean"] == 3
            )
            assert (
                by_slot["second"]["report"]["groups"][0]["fields"]["value"]["mean"]
                == 15
            )
            async with sessions() as db:
                refs = list(
                    (
                        await db.scalars(
                            select(AnalysisProjectInput).where(
                                AnalysisProjectInput.run_id == UUID(run["id"])
                            )
                        )
                    ).all()
                )
                assert {row.slot_id for row in refs} == {"first", "second"}
                method = jsonable_encoder(
                    await legacy.create_analysis_pipeline(
                        legacy.PipelineCreateRequest(
                            run_id=run["id"], title="Synthetic Project method"
                        ),
                        db,
                        f.scope.analyst,
                    )
                )
            assert method["source_scope"] == "project" and method["protocol_id"] is None
            revision = method["revisions"][0]
            assert len(revision["provenance"]["input_contracts"]["inputs"]) == 2
            async with sessions() as db:
                narrative = jsonable_encoder(
                    await api.append_project_analysis_interpretation(
                        UUID(run["id"]),
                        human_interpretation(run["result_digest"]),
                        db,
                        f.scope.analyst,
                        Response(),
                    )
                )
            assert narrative["revision"] == 1
            assert (
                narrative["resolved_evidence"][0]["groups"][0]["statistics"]["mean"]
                == 3
            )
            async with sessions() as db:
                revised = await api.append_project_analysis_interpretation(
                    UUID(run["id"]),
                    human_interpretation(
                        run["result_digest"],
                        expected=1,
                        summary="Additional review still leaves the question open.",
                    ),
                    db,
                    f.scope.analyst,
                    Response(),
                )
                assert revised["revision"] == 2
            async with sessions() as db:
                with pytest.raises(HTTPException) as stale:
                    await api.append_project_analysis_interpretation(
                        UUID(run["id"]),
                        human_interpretation(run["result_digest"]),
                        db,
                        f.scope.analyst,
                        Response(),
                    )
                assert stale.value.status_code == 409
            async with sessions() as db:
                exported = await legacy.download_record_analysis(
                    UUID(run["id"]), db, f.scope.analyst
                )
                export = json.loads(exported.body)
                assert export["interpretations"]["current_revision"] == 2
                assert (
                    export["result"] == run["result"]
                    and export["result_digest"] == run["result_digest"]
                )
                old_list = await legacy.list_record_analyses(
                    f.scope.project.id,
                    db,
                    f.scope.analyst,
                    Response(),
                    limit=100,
                    offset=0,
                )
                project_list = await legacy.list_record_analyses(
                    f.scope.project.id,
                    db,
                    f.scope.analyst,
                    Response(),
                    limit=100,
                    offset=0,
                    source_scope="project",
                )
                assert old_list["items"] == [] and len(project_list["items"]) == 1
                old_methods = await legacy.list_analysis_pipelines(
                    f.scope.project.id,
                    db,
                    f.scope.analyst,
                    Response(),
                    limit=100,
                    offset=0,
                )
                new_methods = await legacy.list_analysis_pipelines(
                    f.scope.project.id,
                    db,
                    f.scope.analyst,
                    Response(),
                    limit=100,
                    offset=0,
                    source_scope="project",
                )
                assert old_methods["items"] == [] and len(new_methods["items"]) == 1
            new_record = await add_record(sessions, f.scope, 6, "S3", number=3)
            rerun = await computed_project(
                sessions, f, pipeline_revision_id=revision["id"], rerun_of_id=run["id"]
            )
            assert rerun["source_digest"] != run["source_digest"]
            async with sessions() as db:
                comparison = await api.get_project_analysis_comparison(
                    UUID(rerun["id"]), UUID(run["id"]), db, f.scope.analyst, Response()
                )
                first = next(
                    item for item in comparison["inputs"] if item["slot_id"] == "first"
                )
                assert [item["record_id"] for item in first["added"]] == [
                    str(new_record.id)
                ]
                assert next(
                    item
                    for item in comparison["local_results"]
                    if item["slot_id"] == "first"
                )["changed"]
                assert (
                    await legacy.get_record_analysis(
                        UUID(run["id"]), db, f.scope.analyst, Response()
                    )
                )["result"] == run["result"]
            async with sessions() as db:
                input_row = await db.get(
                    AnalysisProjectInput, (UUID(run["id"]), "first")
                )
                input_row.source_digest = "f" * 64
                with pytest.raises(DBAPIError, match="immutable"):
                    await db.flush()

    asyncio.run(scenario())


def test_project_analysis_sources_revoke_all_private_report_and_method_read_paths():
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions)
            run = await computed_project(sessions, f)
            async with sessions() as db:
                method = await legacy.create_analysis_pipeline(
                    legacy.PipelineCreateRequest(
                        run_id=run["id"], title="Private reviewed sources"
                    ),
                    db,
                    f.scope.analyst,
                )
            for reader in (f.scope.owner, f.scope.outsider):
                async with sessions() as db:
                    with pytest.raises(HTTPException) as private:
                        await legacy.get_record_analysis(
                            UUID(run["id"]), db, reader, Response()
                        )
                    assert private.value.status_code == 404
            async with sessions() as db:
                await db.execute(
                    delete(ProjectUser).where(
                        ProjectUser.project_id == f.scope.project.id,
                        ProjectUser.user_id == f.scope.analyst.id,
                    )
                )
                await db.commit()
            calls = [
                lambda db: legacy.get_record_analysis(
                    UUID(run["id"]), db, f.scope.analyst, Response()
                ),
                lambda db: legacy.download_record_analysis(
                    UUID(run["id"]), db, f.scope.analyst
                ),
                lambda db: legacy.get_analysis_pipeline(
                    method["id"], db, f.scope.analyst, Response()
                ),
                lambda db: api.get_project_analysis_interpretations(
                    UUID(run["id"]), db, f.scope.analyst, Response()
                ),
                lambda db: api.append_project_analysis_interpretation(
                    UUID(run["id"]),
                    human_interpretation(run["result_digest"]),
                    db,
                    f.scope.analyst,
                    Response(),
                ),
                lambda db: api.get_project_analysis_comparison(
                    UUID(run["id"]), UUID(run["id"]), db, f.scope.analyst, Response()
                ),
            ]
            for call in calls:
                async with sessions() as db:
                    with pytest.raises(HTTPException) as denied:
                        await call(db)
                    assert denied.value.status_code in {403, 404}
            async with sessions() as db:
                listed = await legacy.list_record_analyses(
                    f.scope.project.id,
                    db,
                    f.scope.analyst,
                    Response(),
                    limit=100,
                    offset=0,
                    source_scope="project",
                )
                assert listed["items"] == []

    asyncio.run(scenario())


def test_project_analysis_confirm_staleness_concurrency_and_legacy_endpoint_isolation():
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions)
            stale_preview = await preview_project(sessions, f)
            await add_record(sessions, f.second, 30, "S3", number=3)
            with pytest.raises(HTTPException) as stale:
                await confirm_project(sessions, f, stale_preview)
            assert stale.value.status_code == 409
            current = await preview_project(sessions, f)
            key = f"parallel-project-{uuid4().hex}"
            first, duplicate = await asyncio.gather(
                confirm_project(sessions, f, current, key=key),
                confirm_project(sessions, f, current, key=key),
            )
            assert (
                first["id"] == duplicate["id"]
                and first["job_id"] == duplicate["job_id"]
            )
            different = await preview_project(sessions, f, question="Another question")
            with pytest.raises(HTTPException) as conflict:
                await confirm_project(sessions, f, different, key=key)
            assert conflict.value.status_code == 409
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisRun)
                        .where(AnalysisRun.created_by_user_id == f.scope.analyst.id)
                    )
                    == 1
                )
                with pytest.raises(HTTPException) as wrong_engine:
                    await legacy.create_record_analysis(
                        legacy.AnalysisConfirmRequest(
                            preview_id=current["id"],
                            preview_digest=current["preview_digest"],
                            client_idempotency_key=f"wrong-engine-{uuid4().hex}",
                        ),
                        db,
                        f.scope.analyst,
                    )
                assert wrong_engine.value.status_code in {409, 422}

    asyncio.run(scenario())


def test_project_analysis_exact_selection_is_not_expanded_and_changed_schema_requires_revision():
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions)
            selected = project_selection(f, exact=True)
            preview = await preview_project(sessions, f, selection=selected)
            await add_record(sessions, f.scope, 999, "excluded", number=3)
            run = await confirm_project(sessions, f, preview)
            assert len(run["source_snapshot"]["inputs"][0]["snapshot"]["records"]) == 2
            await execute_job(sessions, {**run, "job_id": UUID(run["job_id"])})
            async with sessions() as db:
                method = jsonable_encoder(
                    await legacy.create_analysis_pipeline(
                        legacy.PipelineCreateRequest(
                            run_id=run["id"], title="Exact source selection"
                        ),
                        db,
                        f.scope.analyst,
                    )
                )
                version = ProtocolVersion(
                    id=uuid4(),
                    protocol_id=f.scope.protocol.id,
                    version="2.0.0",
                    json_schema=deepcopy(f.scope.version.json_schema),
                    fields={},
                    assigners={},
                    assigner_graph={},
                    aimd="Synthetic v2",
                    meta_data={
                        "id": f.scope.protocol.uid,
                        "version": "2.0.0",
                        "name": "Explicit v2",
                    },
                )
                db.add(version)
                await db.commit()
            await add_record(
                sessions, f.scope, 8, "S4", number=4, protocol_version="2.0.0"
            )
            with pytest.raises(HTTPException) as changed:
                await preview_project(
                    sessions, f, pipeline_revision_id=method["revisions"][0]["id"]
                )
            assert changed.value.status_code == 409
            async with sessions() as db:
                with pytest.raises(HTTPException) as wrong_selection_scope:
                    await legacy.revise_analysis_pipeline(
                        UUID(method["id"]),
                        legacy.PipelineReviseRequest(
                            recipe=project_recipe(),
                            expected_revision=1,
                            source_selection=AnalysisSelection(),
                        ),
                        db,
                        f.scope.analyst,
                    )
                assert wrong_selection_scope.value.status_code == 409
            async with sessions() as db:
                revised = await legacy.revise_analysis_pipeline(
                    UUID(method["id"]),
                    legacy.PipelineReviseRequest(
                        recipe=project_recipe(),
                        expected_revision=1,
                        source_selection=project_selection(f),
                    ),
                    db,
                    f.scope.analyst,
                )
                assert revised["revision"] == 2
            next_preview = await preview_project(
                sessions, f, pipeline_revision_id=revised["id"]
            )
            assert next_preview["pipeline_revision_id"] == str(revised["id"])
            async with sessions() as db:
                unchanged = await legacy.get_analysis_pipeline(
                    UUID(method["id"]), db, f.scope.analyst, Response()
                )
                first = next(
                    row for row in unchanged["revisions"] if row["revision"] == 1
                )
                assert (
                    first["source_selection"]
                    == method["revisions"][0]["source_selection"]
                )

    asyncio.run(scenario())


def test_project_analysis_explicit_join_executes_real_lineage_and_rejects_duplicate_keys():
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions)
            run = await computed_project(
                sessions, f, recipe=project_recipe(relational=True)
            )
            join = run["result"]["join"]
            assert join["audit"]["output_rows"] == 2
            assert join["report"]["groups"][0]["fields"]["left_value"]["mean"] == 3
            assert join["report"]["groups"][0]["fields"]["right_value"]["mean"] == 15
            assert all(str(row.id) in json.dumps(join["rows"]) for row in f.records)
            await add_record(sessions, f.second, 99, "S1", number=3)
            with pytest.raises(HTTPException) as duplicate:
                await preview_project(
                    sessions, f, recipe=project_recipe(relational=True)
                )
            assert duplicate.value.status_code == 422
            assert "duplicate" in str(duplicate.value.detail).lower()

    asyncio.run(scenario())


def test_project_analysis_public_sources_do_not_publish_private_results_and_cancel_reuses_job():
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions, public=True)
            run = await confirm_project(sessions, f, await preview_project(sessions, f))
            async with sessions() as db:
                context = await api.get_project_analysis_context(
                    f.scope.project.id,
                    db,
                    f.scope.outsider,
                    Response(),
                    limit=100,
                    offset=0,
                )
                assert len(context["protocols"]) == 2
                with pytest.raises(HTTPException) as private:
                    await legacy.get_record_analysis(
                        UUID(run["id"]), db, f.scope.outsider, Response()
                    )
                assert private.value.status_code == 404
            async with sessions() as db:
                cancelled = await legacy.cancel_record_analysis(
                    UUID(run["id"]), db, f.scope.analyst
                )
                assert cancelled["status"] == "cancelled"
            async with sessions() as db:
                job = await db.get(PersistentJob, UUID(run["job_id"]))
                assert job.status == "cancelled"

    asyncio.run(scenario())


def test_project_analysis_file_fields_are_unsupported_in_both_source_catalogs():
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions)
            async with sessions() as db:
                version = await db.get(ProtocolVersion, f.scope.version.id)
                schema = deepcopy(version.json_schema)
                schema["vars"]["properties"].update(
                    attachment={"type": "string", "airalogy_type": "FileId"},
                    table={"type": "array", "items": {"type": "number"}},
                )
                version.json_schema = schema
                await db.commit()
            async with sessions() as db:
                initial = await api.get_project_analysis_context(
                    f.scope.project.id,
                    db,
                    f.scope.analyst,
                    Response(),
                    limit=100,
                    offset=0,
                )
                first = next(
                    row
                    for row in initial["protocols"]
                    if row["protocol_id"] == str(f.scope.protocol.id)
                )
                exact = await api.get_project_source_context(
                    f.scope.project.id,
                    f.scope.protocol.id,
                    AnalysisSelection(
                        mode="selected", records=[{"id": f.records[0].id, "version": 1}]
                    ),
                    db,
                    f.scope.analyst,
                    Response(),
                )
                assert len(exact["sources"]) == 1 and exact["sources"][0][
                    "record_id"
                ] == str(f.records[0].id)
                for catalog in (first["fields"], exact["fields"]):
                    fields = {row["key"]: row for row in catalog}
                    assert fields["value"]["type"] == "number"
                    assert fields["group"]["type"] == "string"
                    for key in ("attachment", "table"):
                        assert (
                            fields[key]["type"] == "unsupported"
                            and fields[key]["unsupported_reason"]
                        )
            # Unrelated unsupported fields do not block an ordinary numeric analysis.
            assert (await computed_project(sessions, f))["status"] == "succeeded"

    asyncio.run(scenario())


def test_project_analysis_one_revoked_protocol_blocks_combined_report_not_readable_source():
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions)
            run = await computed_project(sessions, f)
            async with sessions() as db:
                method = await legacy.create_analysis_pipeline(
                    legacy.PipelineCreateRequest(
                        run_id=run["id"], title="Two-source private method"
                    ),
                    db,
                    f.scope.analyst,
                )
            async with sessions() as db:
                second = await db.get(Protocol, f.second.protocol.id)
                second.inherit_permissions = False
                await db.commit()
            async with sessions() as db:
                first = await api.get_project_source_context(
                    f.scope.project.id,
                    f.scope.protocol.id,
                    AnalysisSelection(),
                    db,
                    f.scope.analyst,
                    Response(),
                )
                assert len(first["sources"]) == 2
                initial = await api.get_project_analysis_context(
                    f.scope.project.id,
                    db,
                    f.scope.analyst,
                    Response(),
                    limit=100,
                    offset=0,
                )
                assert [row["protocol_id"] for row in initial["protocols"]] == [
                    str(f.scope.protocol.id)
                ]
            for call in (
                lambda db: legacy.get_record_analysis(
                    UUID(run["id"]), db, f.scope.analyst, Response()
                ),
                lambda db: legacy.get_analysis_pipeline(
                    method["id"], db, f.scope.analyst, Response()
                ),
                lambda db: legacy.download_record_analysis(
                    UUID(run["id"]), db, f.scope.analyst
                ),
            ):
                async with sessions() as db:
                    with pytest.raises(HTTPException) as denied:
                        await call(db)
                    assert denied.value.status_code == 403

    asyncio.run(scenario())


def test_project_analysis_rejects_cross_project_inputs_and_multiple_record_revisions():
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions)
            other = await seed_analysis(sessions, public=True)
            await add_record(sessions, other, 777)
            selected = project_selection(f)
            selected["inputs"][1]["protocol_id"] = other.protocol.id
            with pytest.raises(HTTPException) as wrong_project:
                await preview_project(sessions, f, selection=selected)
            assert wrong_project.value.status_code == 422
            async with sessions() as db:
                with pytest.raises(HTTPException) as wrong_context:
                    await api.get_project_source_context(
                        f.scope.project.id,
                        other.protocol.id,
                        AnalysisSelection(),
                        db,
                        f.scope.analyst,
                        Response(),
                    )
                assert wrong_context.value.status_code == 422
            # Exact source contracts never treat revisions of the same Record as two samples.
            from pydantic import ValidationError

            selected = project_selection(f, exact=True)
            selected["inputs"][0]["selection"]["records"].append(
                {"id": f.records[0].id, "version": 2}
            )
            with pytest.raises(ValidationError, match="one revision of each Record"):
                ProjectPreviewRequest(
                    project_id=f.scope.project.id,
                    selection=selected,
                    recipe=project_recipe(),
                )

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["cancel", "revoke"])
def test_project_analysis_late_real_computation_never_overrides_cancel_or_source_revocation(
    monkeypatch, operation
):
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions)
            run = await confirm_project(sessions, f, await preview_project(sessions, f))
            computed, release = threading.Event(), threading.Event()
            real_compute = project_analysis_engine.compute_project_analysis
            receipts = []

            def paused_real_compute(*args, **kwargs):
                result = real_compute(*args, **kwargs)
                receipts.append(canonical_digest(result))
                computed.set()
                if not release.wait(timeout=10):
                    raise AssertionError(
                        "Test did not release actual Project computation"
                    )
                return result

            monkeypatch.setattr(
                project_analysis_engine, "compute_project_analysis", paused_real_compute
            )
            pending = asyncio.create_task(
                execute_job(sessions, {**run, "job_id": UUID(run["job_id"])})
            )
            try:
                assert await asyncio.to_thread(computed.wait, 10)
                async with sessions() as db:
                    stored = await db.get(AnalysisRun, UUID(run["id"]))
                    assert stored.status == "running" and stored.result is None
                async with sessions() as db:
                    if operation == "cancel":
                        cancelled = await asyncio.wait_for(
                            legacy.cancel_record_analysis(
                                UUID(run["id"]), db, f.scope.analyst
                            ),
                            timeout=5,
                        )
                        assert cancelled["status"] == "cancelled"
                    else:
                        second = await db.get(Protocol, f.second.protocol.id)
                        second.inherit_permissions = False
                        await db.commit()
            finally:
                release.set()
            finished = await asyncio.wait_for(pending, timeout=10)
            expected = "cancelled" if operation == "cancel" else "failed"
            assert finished["status"] == expected and len(receipts) == 1
            async with sessions() as db:
                stored = await db.get(AnalysisRun, UUID(run["id"]))
                assert (
                    stored.status == expected
                    and stored.result is None
                    and stored.result_digest is None
                )

    asyncio.run(scenario())


def test_project_analysis_interpretation_is_immutable_in_postgresql_and_tied_to_result():
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions)
            run = await computed_project(sessions, f)
            async with sessions() as db:
                wrong_digest = human_interpretation("f" * 64)
                with pytest.raises(HTTPException) as stale:
                    await api.append_project_analysis_interpretation(
                        UUID(run["id"]), wrong_digest, db, f.scope.analyst, Response()
                    )
                assert stale.value.status_code == 409
            async with sessions() as db:
                revision = await api.append_project_analysis_interpretation(
                    UUID(run["id"]),
                    human_interpretation(run["result_digest"]),
                    db,
                    f.scope.analyst,
                    Response(),
                )
            async with sessions() as db:
                stored = await db.get(AnalysisInterpretationRevision, revision["id"])
                stored.content = {
                    **stored.content,
                    "summary": "An unapproved overwrite",
                }
                with pytest.raises(DBAPIError, match="immutable"):
                    await db.flush()
            async with sessions() as db:
                unchanged = await api.get_project_analysis_interpretations(
                    UUID(run["id"]), db, f.scope.analyst, Response()
                )
                assert (
                    unchanged["current_revision"] == 1
                    and unchanged["items"][0]["content"] == revision["content"]
                )

    asyncio.run(scenario())
