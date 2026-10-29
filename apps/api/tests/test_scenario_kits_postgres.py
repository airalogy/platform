"""Isolated PostgreSQL + real bundled compiler/storage acceptance, no AI needed."""

import asyncio
import csv
import io
import json
import os
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError

from app.models.lab import LabUser
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.resource import RecordResourceLink, Resource, ResourceType
from app.routers import records
from app.routers import scenario_kits as api
from app.services import scenario_kits as kits
from app.services.analysis_engine import AnalysisRecipe
from app.services.scenario_catalog import analysis_recipe
from tests.test_record_analysis_postgres import (
    confirm,
    database,
    execute_job,
    get_run,
    preview,
    seed_analysis,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"),
    reason="Isolated migrated PostgreSQL required",
)


async def operate(
    sessions,
    scope,
    *,
    project=False,
    kit="airalogy.sample-results",
    action=None,
    version="1.0.0",
    strategy="keep",
):
    request = kits.KitRequest(
        kit_id=kit,
        action=action or ("apply" if project else "enable"),
        version=version,
        strategy=strategy,
    )
    project_id = scope.project.id if project else None
    async with sessions() as db:
        preview = await kits.preview(db, scope.owner, scope.lab.id, project_id, request)
    assert not preview["blockers"], preview
    params = kits.KitConfirm(
        **request.model_dump(),
        preview_token=preview["preview_token"],
        request_id=uuid4(),
    )
    async with sessions() as db:
        result = await kits.confirm(db, scope.owner, scope.lab.id, project_id, params)
    return params, result


def test_install_compose_upgrade_and_deactivate():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            scope.owner.api_key_iv = "00" * 16
            async with sessions() as db:
                with pytest.raises(HTTPException) as missing:
                    await kits.preview(
                        db,
                        scope.owner,
                        scope.lab.id,
                        scope.project.id,
                        kits.KitRequest(
                            kit_id="airalogy.sample-results", action="deactivate"
                        ),
                    )
                assert missing.value.status_code == 409
            await operate(sessions, scope)
            params, result = await operate(sessions, scope, project=True)
            async with sessions() as db:
                replay = await kits.confirm(
                    db, scope.owner, scope.lab.id, scope.project.id, params
                )
                assert replay == {"event_id": result["event_id"], "replayed": True}
                app = await kits.application(db, scope.project.id, params.kit_id)
                original_assets = list(app.assets)
                assert len(original_assets) == 1
                sample = await api.register_sample(
                    scope.lab.id,
                    scope.project.id,
                    api.SampleCreate(
                        kit_id=params.kit_id,
                        name="Synthetic sample",
                        code="S-001",
                        category="Synthetic control",
                    ),
                    db,
                    scope.owner,
                )
                assert sample
            await operate(sessions, scope, kit="airalogy.material-results")
            await operate(
                sessions, scope, kit="airalogy.material-results", project=True
            )
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ResourceType)
                        .where(ResourceType.lab_id == scope.lab.id)
                    )
                    == 1
                )
                preview = await kits.preview(
                    db,
                    scope.owner,
                    scope.lab.id,
                    None,
                    kits.KitRequest(
                        kit_id=params.kit_id, action="disable", version="1.0.0"
                    ),
                )
                assert "active_project_applications" in preview["blockers"]
            await operate(sessions, scope, version="1.1.0")
            await operate(sessions, scope, project=True, version="1.1.0")
            async with sessions() as db:
                app = await kits.application(db, scope.project.id, params.kit_id)
                assert app.assets == original_assets  # keep means no overwrite
            await operate(
                sessions, scope, project=True, version="1.1.0", strategy="new_copy"
            )
            async with sessions() as db:
                app = await kits.application(db, scope.project.id, params.kit_id)
                assert len(app.assets) == 2
                assert app.assets[0] == original_assets[0]
            await operate(
                sessions, scope, project=True, action="deactivate", version="1.1.0"
            )
            await operate(sessions, scope, action="disable", version="1.1.0")
            async with sessions() as db:
                assert await db.get(Protocol, UUID(original_assets[0]["protocol_id"]))
                with pytest.raises(DBAPIError):
                    await db.execute(
                        text(
                            "UPDATE scenario_kit_events SET operation = 'tampered' WHERE id = :id"
                        ),
                        {"id": UUID(result["event_id"])},
                    )
                await db.rollback()

    asyncio.run(exercise())


def test_scope_stale_preview_failure_atomicity():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            request = kits.KitRequest(
                kit_id="airalogy.sample-results", version="1.0.0", action="enable"
            )
            async with sessions() as db:
                with pytest.raises(HTTPException) as denied:
                    await kits.directory(
                        db, scope.outsider, scope.lab.id, scope.project.id
                    )
                assert denied.value.status_code == 404
                with pytest.raises(HTTPException) as denied:
                    await kits.preview(db, scope.recorder, scope.lab.id, None, request)
                assert denied.value.status_code == 403
                preview = await kits.preview(
                    db, scope.owner, scope.lab.id, None, request
                )
            await operate(sessions, scope)
            async with sessions() as db:
                with pytest.raises(HTTPException) as stale:
                    await kits.confirm(
                        db,
                        scope.owner,
                        scope.lab.id,
                        None,
                        kits.KitConfirm(
                            **request.model_dump(),
                            preview_token=preview["preview_token"],
                            request_id=uuid4(),
                        ),
                    )
                assert stale.value.status_code == 409

    asyncio.run(exercise())


async def import_csv(db, user, protocol_id, content, *, preview=True, token=""):
    return await records.import_protocol_records(
        protocol_id,
        db,
        user,
        BackgroundTasks(),
        file=UploadFile(filename="synthetic.csv", file=io.BytesIO(content.encode())),
        input_format="csv",
        allow_extra_var_fields=False,
        require_complete_quiz=False,
        include_template_defaults=True,
        preview=preview,
        preview_token=token,
    )


def test_sample_template_strict_import_sources_and_analysis(monkeypatch):
    monkeypatch.setattr(kits.config, "AI_ENABLED", False)

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            scope.owner.api_key_iv = "00" * 16
            await operate(sessions, scope)
            params, _ = await operate(sessions, scope, project=True)
            async with sessions() as db:
                app = await kits.application(db, scope.project.id, params.kit_id)
                protocol_id = UUID(app.assets[0]["protocol_id"])
                sample = await api.register_sample(
                    scope.lab.id,
                    scope.project.id,
                    api.SampleCreate(
                        kit_id=params.kit_id,
                        name="Synthetic control",
                        code="CONTROL-1",
                        category="synthetic",
                    ),
                    db,
                    scope.owner,
                )
                sample_id = UUID(str(sample["id"]))
                template = await api.sample_template(
                    scope.lab.id,
                    scope.project.id,
                    api.SampleTemplate(
                        kit_id=params.kit_id,
                        protocol_id=protocol_id,
                        sample_ids=[sample_id],
                    ),
                    db,
                    scope.owner,
                )
                table = list(csv.reader(io.StringIO(template["csv"])))
                assert json.loads(table[1][0])["id"] == str(sample_id)
                assert table[1][1:] == [""] * 5
                rejected = await import_csv(
                    db, scope.owner, protocol_id, template["csv"]
                )
                assert rejected["errors"] and rejected["preview_token"] is None
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(Record)
                        .where(Record.protocol_id == protocol_id)
                    )
                    == 0
                )
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(table[0])
                for value, unit in [(2, "mg/L"), (4, "mg/L"), (100, "g/L")]:
                    writer.writerow(
                        [
                            table[1][0],
                            "synthetic-method",
                            "concentration",
                            value,
                            unit,
                            "2026-01-01T12:00:00Z",
                        ]
                    )
                content = output.getvalue()
                inspected = await import_csv(db, scope.owner, protocol_id, content)
                assert not inspected["errors"], inspected
                assert inspected["valid_count"] == 3
                imported = await import_csv(
                    db,
                    scope.owner,
                    protocol_id,
                    content,
                    preview=False,
                    token=inspected["preview_token"],
                )
                assert imported["imported_count"] == 3
                links = (
                    await db.scalars(
                        select(RecordResourceLink).where(
                            RecordResourceLink.resource_id == sample_id
                        )
                    )
                ).all()
                assert len(links) == 3
                assert all(link.resource_revision_id for link in links)
                protocol = await db.get(Protocol, protocol_id)
            analysis_scope = SimpleNamespace(**{**vars(scope), "protocol": protocol})
            draft = await preview(
                sessions,
                analysis_scope,
                user=scope.owner,
                selected_recipe=AnalysisRecipe(**analysis_recipe()),
            )
            run = await confirm(sessions, analysis_scope, draft, user=scope.owner)
            async with sessions() as db:
                blocked = await kits.preview(
                    db,
                    scope.owner,
                    scope.lab.id,
                    scope.project.id,
                    kits.KitRequest(
                        kit_id="airalogy.sample-results", action="deactivate"
                    ),
                )
                assert "active_project_work" in blocked["blockers"]
            assert (await execute_job(sessions, run))["status"] == "succeeded"
            report = await get_run(
                sessions, analysis_scope, run["id"], user=scope.owner
            )
            means = sorted(
                group["fields"]["value"]["mean"] for group in report["result"]["groups"]
            )
            assert means == [3, 100]  # never combine different units
            # Ordinary manual Record entry uses exactly the same resource model.
            from app.routers.resources import resolver_search

            async with sessions() as db:
                found = await resolver_search(
                    scope.lab.id,
                    scope.owner,
                    db,
                    q="CONTROL-1",
                    resource_type="airalogy_sample_v1",
                    limit=20,
                )
                assert str(found["items"][0]["id"]) == str(sample_id)
                manual = await records.create_protocol_record(
                    protocol_id,
                    records.RecordCreateParams(
                        var={
                            "sample": {"id": str(sample_id), "entity": "sample"},
                            "method": "manual-method",
                            "metric": "concentration",
                            "value": 8,
                            "unit": "mg/L",
                            "measured_at": "2026-01-02T12:00:00Z",
                        },
                        step={},
                        check={},
                        report="Synthetic manual measurement",
                    ),
                    scope.owner,
                    db,
                )
                assert manual.protocol_version == "1.0.0"
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(RecordResourceLink)
                        .where(RecordResourceLink.record_id == manual.id)
                    )
                    == 1
                )

    asyncio.run(exercise())


def test_compilation_failure_rolls_back_all_assets(monkeypatch):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            scope.owner.api_key_iv = "00" * 16
            await operate(sessions, scope)
            real = kits.protocol_exec
            calls = 0

            async def fail_second(*args, **kwargs):
                nonlocal calls
                calls += 1
                return {"success": False} if calls == 2 else await real(*args, **kwargs)

            monkeypatch.setattr(kits, "protocol_exec", fail_second)
            with pytest.raises(HTTPException) as failure:
                await operate(sessions, scope, project=True)
            assert failure.value.status_code == 503
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(Protocol)
                        .where(Protocol.project_id == scope.project.id)
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ResourceType)
                        .where(ResourceType.lab_id == scope.lab.id)
                    )
                    == 0
                )
                assert (
                    await kits.application(
                        db, scope.project.id, "airalogy.sample-results"
                    )
                    is None
                )

    asyncio.run(exercise())


def test_revoke_after_preview_and_disabled_modules(monkeypatch):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            scope.owner.api_key_iv = "00" * 16
            await operate(sessions, scope)
            request = kits.KitRequest(
                kit_id="airalogy.sample-results", action="apply", version="1.0.0"
            )
            async with sessions() as db:
                draft = await kits.preview(
                    db, scope.owner, scope.lab.id, scope.project.id, request
                )
                monkeypatch.setattr(
                    kits.config, "SCENARIO_KIT_MODULES", "airalogy.records"
                )
                with pytest.raises(HTTPException) as disabled:
                    await kits.confirm(
                        db,
                        scope.owner,
                        scope.lab.id,
                        scope.project.id,
                        kits.KitConfirm(
                            **request.model_dump(),
                            preview_token=draft["preview_token"],
                            request_id=uuid4(),
                        ),
                    )
                assert disabled.value.status_code == 409
                assert (
                    await kits.application(db, scope.project.id, request.kit_id) is None
                )

    asyncio.run(exercise())


def test_concurrent_retry_creates_one_application_and_stale_edits_are_rejected():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await operate(sessions, scope)
            request = kits.KitRequest(
                kit_id="airalogy.sample-results", version="1.0.0", action="apply"
            )
            async with sessions() as db:
                planned = await kits.preview(
                    db, scope.owner, scope.lab.id, scope.project.id, request
                )
            params = kits.KitConfirm(
                **request.model_dump(),
                preview_token=planned["preview_token"],
                request_id=uuid4(),
            )

            async def call():
                async with sessions() as db:
                    return await kits.confirm(
                        db, scope.owner, scope.lab.id, scope.project.id, params
                    )

            a, b = await asyncio.gather(call(), call())
            assert a["event_id"] == b["event_id"]
            assert sorted([a["replayed"], b["replayed"]]) == [False, True]
            async with sessions() as db:
                app = await kits.application(db, scope.project.id, request.kit_id)
                assert len(app.assets) == 1
                planned = await kits.preview(
                    db, scope.owner, scope.lab.id, scope.project.id, request
                )
                version = await db.get(
                    ProtocolVersion, UUID(app.assets[0]["protocol_version_id"])
                )
                version.aimd += "\nUser-authored experiment note\n"
                await db.commit()
            async with sessions() as db:
                with pytest.raises(HTTPException) as stale:
                    await kits.confirm(
                        db,
                        scope.owner,
                        scope.lab.id,
                        scope.project.id,
                        kits.KitConfirm(
                            **request.model_dump(),
                            preview_token=planned["preview_token"],
                            request_id=uuid4(),
                        ),
                    )
                assert stale.value.status_code == 409
            await operate(sessions, scope, project=True)
            async with sessions() as db:
                kept = await db.get(ProtocolVersion, version.id)
                assert "User-authored" in kept.aimd
                result = await kits.directory(
                    db, scope.owner, scope.lab.id, scope.project.id
                )
                assert result["kits"][0]["application"]["assets"][0]["changed"]
                # A second edit must also expire a preview that already showed
                # the template as customized, even if its version is unchanged.
                planned = await kits.preview(
                    db, scope.owner, scope.lab.id, scope.project.id, request
                )
                kept.aimd += "\nA second user-authored note\n"
                await db.commit()
            async with sessions() as db:
                with pytest.raises(HTTPException) as stale:
                    await kits.confirm(
                        db,
                        scope.owner,
                        scope.lab.id,
                        scope.project.id,
                        kits.KitConfirm(
                            **request.model_dump(),
                            preview_token=planned["preview_token"],
                            request_id=uuid4(),
                        ),
                    )
                assert stale.value.status_code == 409

    asyncio.run(exercise())


def test_compilation_rechecks_membership_before_commit(monkeypatch):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await operate(sessions, scope)
            real = kits.materialize_protocol
            revoked = False

            async def materialize(*args, **kwargs):
                nonlocal revoked
                result = await real(*args, **kwargs)
                if not revoked:
                    async with sessions() as other:
                        await other.execute(
                            delete(LabUser).where(
                                LabUser.lab_id == scope.lab.id,
                                LabUser.user_id == scope.owner.id,
                            )
                        )
                        await other.commit()
                    revoked = True
                return result

            monkeypatch.setattr(kits, "materialize_protocol", materialize)
            with pytest.raises(HTTPException) as denied:
                await operate(sessions, scope, project=True)
            assert denied.value.status_code == 404
            async with sessions() as db:
                assert (
                    await kits.application(
                        db, scope.project.id, "airalogy.sample-results"
                    )
                    is None
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ResourceType)
                        .where(ResourceType.lab_id == scope.lab.id)
                    )
                    == 0
                )

    asyncio.run(exercise())


def test_sample_template_rejects_restricted_and_foreign_samples():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            foreign = await seed_analysis(sessions)
            for value in (scope, foreign):
                await operate(sessions, value)
                await operate(sessions, value, project=True)
            async with sessions() as db:
                app = await kits.application(
                    db, scope.project.id, "airalogy.sample-results"
                )
                protocol_id = UUID(app.assets[0]["protocol_id"])
                sample_ids = []
                for value in (scope, foreign):
                    sample = await api.register_sample(
                        value.lab.id,
                        value.project.id,
                        api.SampleCreate(
                            kit_id="airalogy.sample-results",
                            name="Private synthetic",
                            code="PRIVATE-1",
                            category="synthetic",
                        ),
                        db,
                        value.owner,
                    )
                    sample_ids.append(UUID(str(sample["id"])))
                await db.execute(
                    update(Resource)
                    .where(Resource.id == sample_ids[0])
                    .values(visibility="restricted")
                )
                await db.commit()
                for sample_id in sample_ids:
                    with pytest.raises(HTTPException) as denied:
                        await api.sample_template(
                            scope.lab.id,
                            scope.project.id,
                            api.SampleTemplate(
                                kit_id="airalogy.sample-results",
                                protocol_id=protocol_id,
                                sample_ids=[sample_id],
                            ),
                            db,
                            scope.recorder,
                        )
                    assert denied.value.status_code == 404
                permitted = await api.sample_template(
                    scope.lab.id,
                    scope.project.id,
                    api.SampleTemplate(
                        kit_id="airalogy.sample-results",
                        protocol_id=protocol_id,
                        sample_ids=[sample_ids[0]],
                    ),
                    db,
                    scope.owner,
                )
                assert str(sample_ids[0]) in permitted["csv"]

    asyncio.run(exercise())
