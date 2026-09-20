"""Real Project worker methods become schema-only immutable Workflow assets."""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError

from app.config import config
from app.models.analysis import AnalysisRun
from app.models.project import PermissionType, Project, ProjectRole, ProjectUser
from app.models.project_group import ProtocolUser
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.workflow_analysis import (
    WorkflowAnalysisMethod,
    WorkflowAnalysisMethodProjectVersion,
)
from app.routers import analyses
from app.routers import workflow_analysis_methods as api
from app.services import workflow_analysis_methods as service
from tests import test_project_analyses_postgres as project_tests
from tests.test_project_analyses_postgres import (
    computed_project,
    project_scope,
)
from tests.test_record_analysis_postgres import database

pytestmark = project_tests.pytestmark


@pytest.fixture(autouse=True)
def flat_permissions(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")


async def saved_project_method(sessions, fixture, **changes):
    run = await computed_project(sessions, fixture, **changes)
    async with sessions() as db:
        saved = jsonable_encoder(
            await analyses.create_analysis_pipeline(
                analyses.PipelineCreateRequest(
                    run_id=run["id"], title="Private Project method"
                ),
                db,
                fixture.scope.analyst,
            )
        )
    return saved, run


def project_method_draft(fixture, saved, **changes):
    return service.MethodPublicationDraft.model_validate(
        {
            "project_id": str(fixture.scope.project.id),
            "pipeline_revision_id": saved["revisions"][0]["id"],
            "title": "Shared Project method",
            "project_inputs": [
                {
                    "slot_id": slot_id,
                    "protocol_id": str(scope.protocol.id),
                    "protocol_version_ids": [str(scope.version.id)],
                }
                for slot_id, scope in (
                    ("first", fixture.scope),
                    ("second", fixture.second),
                )
            ],
            **changes,
        }
    )


async def project_method_preview(sessions, fixture, params):
    async with sessions() as db:
        return await api.preview_method(params, fixture.scope.analyst, db, Response())


def project_method_confirm(params, preview):
    return service.MethodPublicationConfirm(
        **params.model_dump(),
        preview_digest=preview["preview_digest"],
        preview_token=preview["preview_token"],
        idempotency_key=uuid4(),
    )


async def publish_project_method(sessions, fixture, saved):
    params = project_method_draft(fixture, saved)
    preview = await project_method_preview(sessions, fixture, params)
    command = project_method_confirm(params, preview)
    async with sessions() as db:
        published = await api.confirm_method(command, fixture.scope.analyst, db)
    return published, command


def test_project_method_real_worker_publication_privacy_concurrency_and_output_ports():
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions, public=True)
            saved, run = await saved_project_method(sessions, f)
            params = project_method_draft(f, saved)
            preview = await project_method_preview(sessions, f, params)
            assert preview["publication"]["protocol_id"] is None
            command = project_method_confirm(params, preview)

            async def publish():
                async with sessions() as db:
                    return await api.confirm_method(command, f.scope.analyst, db)

            first, second = await asyncio.gather(publish(), publish())
            assert first == second
            # The UI consumes a derived scalar catalog, never raw AIMD metadata.
            for slot_id in ("first", "second"):
                catalog = first["project_input_fields"][slot_id]
                assert isinstance(catalog, list)
                assert (
                    next(field for field in catalog if field["key"] == "value")["unit"]
                    == "mg/L"
                )
            assert all(
                isinstance(version["fields"], dict)
                for slot in first["project_contract"]["slots"]
                for version in slot["versions"]
            )
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowAnalysisMethodProjectVersion)
                        .where(
                            WorkflowAnalysisMethodProjectVersion.method_id
                            == UUID(first["id"])
                        )
                    )
                    == 2
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisRun)
                        .where(AnalysisRun.project_id == f.scope.project.id)
                    )
                    == 1
                )  # Publication itself never executes or creates another Run.
                listing = await api.get_methods(
                    f.scope.project.id, f.scope.recorder, db, Response()
                )
                assert listing == {"items": [first], "unavailable": []}
                encoded = json.dumps(listing)
                for identity in (
                    saved["id"],
                    saved["revisions"][0]["id"],
                    run["id"],
                    *(str(record.id) for record in f.records),
                ):
                    assert identity not in encoded
                for private_field in (
                    "source_selection",
                    "source_records",
                    "question",
                    "result",
                    "provenance",
                ):
                    assert f'"{private_field}"' not in encoded
                with pytest.raises(HTTPException) as private:
                    await analyses.get_analysis_pipeline(
                        UUID(saved["id"]), db, f.scope.recorder, Response()
                    )
                assert private.value.status_code == 404
                fields = await api.preview_outputs(
                    UUID(first["id"]),
                    api.OutputPreview(
                        outputs=[
                            {
                                "output_id": "first_mean",
                                "source": {"kind": "local", "slot_id": "first"},
                                "field": "value",
                                "statistic": "mean",
                                "group": {},
                            }
                        ]
                    ),
                    f.scope.recorder,
                    db,
                )
                assert fields["fields"][0]["path"] == ["analysis", "first_mean"]
                assert fields["fields"][0]["unit"] == "mg/L"
            async with sessions() as db:
                await db.execute(
                    update(Protocol)
                    .where(Protocol.id == f.second.protocol.id)
                    .values(inherit_permissions=False)
                )
                await db.commit()
            async with sessions() as db:
                listing = await api.get_methods(
                    f.scope.project.id, f.scope.recorder, db, Response()
                )
                # This changes Record-analysis access, not the legacy public
                # read_protocol policy. A Schema-only method stays readable.
                assert listing == {"items": [first], "unavailable": []}
                with pytest.raises(HTTPException) as private:
                    await analyses.get_analysis_pipeline(
                        UUID(saved["id"]), db, f.scope.recorder, Response()
                    )
                assert private.value.status_code == 404

    asyncio.run(scenario())


def test_private_project_method_is_hidden_after_one_explicit_protocol_grant_is_revoked():
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions)
            saved, _ = await saved_project_method(sessions, f)
            published, _command = await publish_project_method(sessions, f, saved)
            async with sessions() as db:
                await db.execute(
                    update(Project)
                    .where(Project.id == f.scope.project.id)
                    .values(permission_type=PermissionType.PROTOCOL_LEVEL)
                )
                await db.execute(
                    update(ProjectUser)
                    .where(
                        ProjectUser.project_id == f.scope.project.id,
                        ProjectUser.user_id == f.scope.recorder.id,
                    )
                    .values(role=ProjectRole.RECORDER)
                )
                for source in (f.scope, f.second):
                    db.add(
                        ProtocolUser(
                            protocol_id=source.protocol.id,
                            user_id=f.scope.recorder.id,
                            role=ProjectRole.RECORDER,
                            create_user_id=f.scope.owner.id,
                        )
                    )
                await db.commit()
            async with sessions() as db:
                listing = await api.get_methods(
                    f.scope.project.id, f.scope.recorder, db, Response()
                )
                assert listing == {"items": [published], "unavailable": []}
            async with sessions() as db:
                await db.execute(
                    delete(ProtocolUser).where(
                        ProtocolUser.protocol_id == f.second.protocol.id,
                        ProtocolUser.user_id == f.scope.recorder.id,
                    )
                )
                await db.commit()
            async with sessions() as db:
                # Project membership and the first source remain available.
                project = await service.scope(db, f.scope.recorder, f.scope.project.id)
                await service.require_protocol_read(
                    db, f.scope.recorder, project, f.scope.protocol
                )
                with pytest.raises(HTTPException) as source_denied:
                    await service.require_protocol_read(
                        db, f.scope.recorder, project, f.second.protocol
                    )
                assert source_denied.value.status_code == 403
                listing = await api.get_methods(
                    f.scope.project.id, f.scope.recorder, db, Response()
                )
                assert listing == {"items": [], "unavailable": []}
                with pytest.raises(HTTPException) as method_denied:
                    await service.get_method(
                        db, f.scope.recorder, UUID(published["id"])
                    )
                assert method_denied.value.status_code == 403

    asyncio.run(scenario())


def test_project_method_preview_expires_and_renamed_destination_requires_reconfirmation():
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions)
            saved, _ = await saved_project_method(sessions, f)
            params = project_method_draft(f, saved)
            preview = await project_method_preview(sessions, f, params)
            command = project_method_confirm(params, preview)
            expired, _ = service.sign_project_preview(
                user_id=f.scope.analyst.id,
                revision_id=params.pipeline_revision_id,
                digest=preview["preview_digest"],
                now=datetime.now(UTC) - timedelta(hours=1),
            )
            for token in (None, expired):
                async with sessions() as db:
                    with pytest.raises(HTTPException) as invalid:
                        await api.confirm_method(
                            command.model_copy(update={"preview_token": token}),
                            f.scope.analyst,
                            db,
                        )
                    assert invalid.value.status_code == 409
            async with sessions() as db:
                await db.execute(
                    update(Project)
                    .where(Project.id == f.scope.project.id)
                    .values(name="Renamed Project destination")
                )
                await db.commit()
            async with sessions() as db:
                with pytest.raises(HTTPException) as stale:
                    await api.confirm_method(command, f.scope.analyst, db)
                assert stale.value.status_code == 409
            fresh = await project_method_preview(sessions, f, params)
            assert fresh["destination"]["project_name"] == "Renamed Project destination"
            async with sessions() as db:
                published = await api.confirm_method(
                    project_method_confirm(params, fresh), f.scope.analyst, db
                )
                assert published["project_contract"]["schema_version"] == 1

    asyncio.run(scenario())


def test_project_method_explicit_compatible_version_extension_rejects_unit_redefinition():
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions)
            saved, _ = await saved_project_method(sessions, f)
            added = []
            async with sessions() as db:
                for index, unit in ((1, "mg/L"), (2, "g/L")):
                    schema = deepcopy(f.scope.version.json_schema)
                    schema["vars"]["properties"]["value"]["unit"] = unit
                    schema["vars"]["properties"]["unreferenced"] = {"type": "boolean"}
                    version = ProtocolVersion(
                        id=uuid4(),
                        protocol_id=f.scope.protocol.id,
                        version=f"1.0.{index}",
                        json_schema=schema,
                        fields={},
                        assigners={},
                        assigner_graph={},
                        meta_data={
                            "id": f.scope.protocol.uid,
                            "version": f"1.0.{index}",
                        },
                        aimd="A real compatible Schema revision with no fabricated Records",
                    )
                    db.add(version)
                    added.append(version)
                await db.commit()
            params = project_method_draft(f, saved)
            params.project_inputs[0].protocol_version_ids = [added[0].id]
            preview = await project_method_preview(sessions, f, params)
            selected = preview["publication"]["project_contract"]["slots"][0][
                "versions"
            ]
            assert [row["id"] for row in selected] == [str(added[0].id)]
            assert str(f.scope.version.id) not in json.dumps(preview["publication"])
            async with sessions() as db:
                published = await api.confirm_method(
                    project_method_confirm(params, preview), f.scope.analyst, db
                )
                assert published["id"]
            params.project_inputs[0].protocol_version_ids = [added[1].id]
            with pytest.raises(HTTPException) as incompatible:
                await project_method_preview(sessions, f, params)
            assert incompatible.value.status_code == 422

    asyncio.run(scenario())


def test_project_method_database_immutability_foreign_keys_and_downgrade_refusal():
    async def scenario():
        async with database() as sessions:
            f = await project_scope(sessions)
            saved, _ = await saved_project_method(sessions, f)
            published, _command = await publish_project_method(sessions, f, saved)
            identity = UUID(published["id"])
            async with sessions() as db:
                for statement in (
                    update(WorkflowAnalysisMethod)
                    .where(WorkflowAnalysisMethod.id == identity)
                    .values(project_contract={}),
                    update(WorkflowAnalysisMethodProjectVersion)
                    .where(WorkflowAnalysisMethodProjectVersion.method_id == identity)
                    .values(schema_digest="f" * 64),
                    delete(ProtocolVersion).where(
                        ProtocolVersion.id == f.scope.version.id
                    ),
                ):
                    with pytest.raises(DBAPIError):
                        async with db.begin_nested():
                            await db.execute(statement)
                connection = await db.connection()
                migration = import_module(
                    "migrations.versions.0073_workflow_project_analysis"
                )

                def downgrade(sync_connection):
                    with Operations.context(
                        MigrationContext.configure(sync_connection)
                    ):
                        migration.downgrade()

                with pytest.raises(RuntimeError, match="Cannot downgrade"):
                    await connection.run_sync(downgrade)
                await db.rollback()
            async with sessions() as db:
                schema = deepcopy(f.second.version.json_schema)
                schema["vars"]["properties"]["value"]["unit"] = "changed"
                await db.execute(
                    update(ProtocolVersion)
                    .where(ProtocolVersion.id == f.second.version.id)
                    .values(json_schema=schema)
                )
                await db.commit()
            async with sessions() as db:
                with pytest.raises(HTTPException) as changed:
                    await service.get_method(db, f.scope.recorder, identity)
                assert changed.value.status_code == 409
                listing = await api.get_methods(
                    f.scope.project.id, f.scope.recorder, db, Response()
                )
                assert listing == {
                    "items": [],
                    "unavailable": [
                        {"id": str(identity), "code": "method_unavailable"}
                    ],
                }

    asyncio.run(scenario())
