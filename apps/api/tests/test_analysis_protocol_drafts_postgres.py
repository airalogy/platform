"""Real drafts, approvals, local Protocol executor, PostgreSQL and object storage.

Only the executor's working directory/storage root is test-local. No parser,
permission, publication result, database operation or object store is mocked.
"""

import asyncio
import json
import re
import tomllib
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile
from jose import jwt
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError
from starlette.datastructures import Headers

from app.config import config
from app.libs.protocol_uid import lock_protocol_uid
from app.models.analysis import AnalysisRun
from app.models.analysis_protocol import (
    AnalysisProtocolDraft,
    AnalysisProtocolDraftReview,
    AnalysisProtocolDraftRevision,
    AnalysisProtocolMethodLink,
)
from app.models.lab import LabRole, LabUser
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
from app.models.user import User
from app.routers import analysis_protocol_drafts as api
from app.routers import protocol_versions, protocols
from app.services import analysis_protocol_drafts as service
from app.services.analysis_protocol_packages import read_analysis_protocol_package_zip
from app.services.workflow_definitions import require_protocol_read
from tests import test_project_analyses_postgres as project_tests
from tests.test_project_analyses_postgres import project_scope
from tests.test_record_analysis_postgres import database
from tests.test_workflow_project_methods_postgres import (
    publish_project_method,
    saved_project_method,
)

pytestmark = project_tests.pytestmark
API_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def real_local_executor(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "PROTOCOL_RUN_ENV", "local")
    monkeypatch.setattr(config, "PROTOCOL_DIR", str(tmp_path / "protocols"))
    monkeypatch.chdir(API_ROOT)


async def published_fixture(sessions):
    fixture = await project_scope(sessions)
    saved, original_run = await saved_project_method(sessions, fixture)
    method, _ = await publish_project_method(sessions, fixture, saved)
    # The shared analysis fixture intentionally has unusable API-key IVs. The
    # ordinary Protocol parser obtains a real key, so persist valid test IVs.
    async with sessions() as db:
        for actor in (fixture.scope.analyst, fixture.scope.owner):
            actor.api_key_iv = uuid4().hex
            await db.execute(
                update(User)
                .where(User.id == actor.id)
                .values(api_key_iv=actor.api_key_iv)
            )
        await db.commit()
    return SimpleNamespace(
        fixture=fixture, scope=fixture.scope, method=method, original_run=original_run
    )


async def grant_version_management(sessions, fixture):
    # COLLABORATOR can create a Protocol but the shipped role matrix does not
    # grant it update_protocol. Version-management cases require a real grant.
    async with sessions() as db:
        await db.execute(
            update(ProjectUser)
            .where(
                ProjectUser.project_id == fixture.scope.project.id,
                ProjectUser.user_id == fixture.scope.analyst.id,
            )
            .values(role=ProjectRole.MANAGER)
        )
        await db.commit()


def race_diagnostics(outcomes):
    """Keep failed concurrency checks useful without dumping executor payloads."""
    return [
        {
            "type": type(item).__name__,
            "status": getattr(item, "status_code", None),
            "detail": str(getattr(item, "detail", item))[:400],
        }
        if isinstance(item, BaseException)
        else {"type": type(item).__name__, "status": "success"}
        for item in outcomes
    ]


def edit_metadata(files, **values):
    files = deepcopy(files)
    for key, value in values.items():
        files["protocol.toml"], count = re.subn(
            rf"^{key}\s*=\s*.+$",
            f"{key} = {json.dumps(value)}",
            files["protocol.toml"],
            flags=re.MULTILINE,
        )
        assert count == 1
    return files


async def draft_content(sessions, fixture, *, target=None, version="0.1.0", uid=None):
    async with sessions() as db:
        template = await api.draft_template(
            service.DraftTemplate(
                method_id=fixture.method["id"], target_protocol_id=target
            ),
            fixture.scope.analyst,
            db,
        )
    metadata = {"version": version}
    if target is None:
        metadata["id"] = uid or f"analysis_generated_{uuid4().hex}"
    return service.DraftContent(
        method_id=fixture.method["id"],
        target_protocol_id=template["target_protocol_id"],
        base_protocol_version_id=template["base_protocol_version_id"],
        files=edit_metadata(template["files"], **metadata),
        reason="Synthetic reviewed method reuse; no analysis is executed by this draft.",
    )


async def creation_command(sessions, fixture, content=None):
    content = content or await draft_content(sessions, fixture)
    async with sessions() as db:
        preview = await api.draft_preview(content, fixture.scope.analyst, db)
    return service.DraftConfirm(
        **content.model_dump(),
        preview_digest=preview["preview_digest"],
        preview_token=preview["preview_token"],
        idempotency_key=uuid4(),
    )


async def create(sessions, fixture, command=None):
    command = command or await creation_command(sessions, fixture)
    async with sessions() as db:
        return await api.draft_confirm(command, fixture.scope.analyst, db)


async def revision_command(
    sessions, fixture, draft, *, suffix="Revised human instructions"
):
    files = edit_metadata(draft["current_revision"]["files"], name=suffix)
    files["protocol.aimd"] += f"\n\n{suffix}.\n"
    content = service.RevisionContent(
        expected_revision=draft["revision"], files=files, reason=suffix
    )
    async with sessions() as db:
        preview = await api.revision_preview(
            UUID(draft["id"]), content, fixture.scope.analyst, db
        )
    return service.RevisionConfirm(
        **content.model_dump(),
        preview_digest=preview["preview_digest"],
        preview_token=preview["preview_token"],
        idempotency_key=uuid4(),
    )


async def revise(sessions, fixture, draft, command):
    async with sessions() as db:
        return await api.revision_confirm(
            UUID(draft["id"]), command, fixture.scope.analyst, db
        )


def exact(draft):
    return service.ExactRevision(
        expected_revision=draft["revision"], package_digest=draft["package_digest"]
    )


async def review(sessions, fixture, draft, *, user=None, decision="reviewed"):
    async with sessions() as db:
        return await api.review_draft(
            UUID(draft["id"]),
            service.ReviewRequest(
                **exact(draft).model_dump(),
                decision=decision,
                note="Reviewed only the deterministic method and editable Protocol package.",
            ),
            user or fixture.scope.owner,
            db,
        )


async def publish_command(sessions, fixture, draft):
    async with sessions() as db:
        preview = await api.publish_preview(
            UUID(draft["id"]), exact(draft), fixture.scope.analyst, db
        )
    return service.PublishConfirm(
        **exact(draft).model_dump(),
        preview_digest=preview["preview_digest"],
        preview_token=preview["preview_token"],
    )


async def publish(sessions, fixture, draft, command=None):
    command = command or await publish_command(sessions, fixture, draft)
    async with sessions() as db:
        return await api.publish_draft(
            UUID(draft["id"]), command, fixture.scope.analyst, db, BackgroundTasks()
        )


async def assert_normal_protocol(sessions, fixture, applied, files):
    identity = applied["applied"]
    async with sessions() as db:
        # Generated packages deliberately omit these optional collections.
        # Both first publication and subsequent versions must normalize the
        # database columns, never rewrite the reviewed source TOML to do so.
        metadata = tomllib.loads(files["protocol.toml"])["airalogy_protocol"]
        assert "disciplines" not in metadata and "keywords" not in metadata
        stored_protocol = await db.get(Protocol, UUID(identity["protocol_id"]))
        assert stored_protocol.disciplines == []
        assert stored_protocol.keywords == []
        ordinary = await protocols.get_protocol_by_id(
            UUID(identity["protocol_id"]),
            db,
            fixture.scope.analyst,
            version=identity["version"],
        )
        # The ordinary parser normalizes text newlines, but the distributable
        # reviewed ZIP below must preserve every original UTF-8 byte.
        assert ordinary["aimd"] == files["protocol.aimd"].replace("\r\n", "\n")
        assert ordinary["metadata"]["version"] == identity["version"]
        assert ordinary["fields"]["vars"]
        assert ordinary["json_schema"]["vars"]["properties"]
        assert ordinary["assigners"] == {}
        assert ordinary["records_count"] == 0
        assert ordinary["analysis_method_sources"] == [
            {
                "method_publication_id": fixture.method["id"],
                "title": fixture.method["title"],
                "draft_id": applied["id"],
                "draft_revision": applied["revision"],
                "protocol_version_id": identity["protocol_version_id"],
                "protocol_version": identity["version"],
                "package_digest": applied["package_digest"],
            }
        ]
        link = await db.get(
            AnalysisProtocolMethodLink, UUID(identity["protocol_version_id"])
        )
        assert (
            str(link.draft_id),
            link.revision,
            str(link.method_id),
            link.package_digest,
        ) == (
            applied["id"],
            applied["revision"],
            fixture.method["id"],
            applied["package_digest"],
        )
        version = await db.get(ProtocolVersion, link.protocol_version_id)
        archive = b"".join(
            [chunk async for chunk in version.download_package_with_stream()]
        )
        package = read_analysis_protocol_package_zip(archive)
        assert package.files == files
        assert package.content_digest == applied["package_digest"]
        with ZipFile(BytesIO(archive)) as zipped:
            assert zipped.read("protocol.toml") == files["protocol.toml"].encode()
            assert set(zipped.namelist()) == {
                "protocol.toml",
                "protocol.aimd",
                "analysis-method.json",
            }
        download = await protocol_versions.download_package(
            link.protocol_id, identity["version"], fixture.scope.analyst, db
        )
        assert version.package_object_key in download["url"]
        assert str(link.method_id) not in json.dumps(package.manifest)
        assert str(link.draft_id) not in json.dumps(package.manifest)
        return ordinary, archive


def test_real_project_method_draft_revision_review_protocol_and_new_version_lifecycle():
    async def scenario():
        async with database() as sessions:
            fixture = await published_fixture(sessions)
            draft = await create(sessions, fixture)
            original = deepcopy(draft["current_revision"])
            assert draft["permissions"] == {
                "can_edit": True,
                "can_review": False,
                "can_publish": False,
            }
            command = await revision_command(sessions, fixture, draft)
            revised = await revise(sessions, fixture, draft, command)
            assert revised["revision"] == 2 and revised["state"] == "draft"
            assert revised["package_digest"] != original["package_digest"]
            assert (
                revised["current_revision"]["manifest_digest"]
                == original["manifest_digest"]
            )
            assert await revise(sessions, fixture, draft, command) == revised
            reviewed = await review(sessions, fixture, revised)
            assert (
                reviewed["state"] == "reviewed"
                and reviewed["permissions"]["can_publish"]
            )
            command = await publish_command(sessions, fixture, reviewed)
            applied = await publish(sessions, fixture, reviewed, command)
            assert applied["state"] == "applied"
            assert await publish(sessions, fixture, reviewed, command) == applied
            first_protocol, first_archive = await assert_normal_protocol(
                sessions, fixture, applied, revised["current_revision"]["files"]
            )
            async with sessions() as db:
                old = await api.read_revision(
                    UUID(draft["id"]), 1, fixture.scope.analyst, db
                )
                assert old == original
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisProtocolDraftRevision)
                        .where(
                            AnalysisProtocolDraftRevision.draft_id == UUID(draft["id"])
                        )
                    )
                    == 2
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisRun)
                        .where(AnalysisRun.project_id == fixture.scope.project.id)
                    )
                    == 1
                )
            await grant_version_management(sessions, fixture)
            update_content = await draft_content(
                sessions,
                fixture,
                target=applied["applied"]["protocol_id"],
                version="0.2.0",
            )
            update_draft = await create(
                sessions,
                fixture,
                await creation_command(sessions, fixture, update_content),
            )
            update_reviewed = await review(sessions, fixture, update_draft)
            updated = await publish(sessions, fixture, update_reviewed)
            assert (
                updated["applied"]["protocol_id"] == applied["applied"]["protocol_id"]
            )
            assert (
                updated["applied"]["protocol_version_id"]
                != applied["applied"]["protocol_version_id"]
            )
            assert updated["applied"]["version"] == "0.2.0"
            await assert_normal_protocol(
                sessions, fixture, updated, update_content.files
            )
            old_protocol, old_archive = await assert_normal_protocol(
                sessions, fixture, applied, revised["current_revision"]["files"]
            )
            assert old_protocol["aimd"] == first_protocol["aimd"]
            assert old_protocol["metadata"] == first_protocol["metadata"]
            assert old_archive == first_archive
            async with sessions() as db:
                assert (
                    await db.get(Protocol, UUID(applied["applied"]["protocol_id"]))
                ).latest_version == "0.2.0"
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ProtocolVersion)
                        .where(
                            ProtocolVersion.protocol_id
                            == UUID(applied["applied"]["protocol_id"])
                        )
                    )
                    == 2
                )

    asyncio.run(scenario())


def test_creation_and_revision_idempotency_are_exact_under_concurrency():
    async def scenario():
        async with database() as sessions:
            fixture = await published_fixture(sessions)
            command = await creation_command(sessions, fixture)
            first, second = await asyncio.gather(
                create(sessions, fixture, command), create(sessions, fixture, command)
            )
            assert first == second
            changed = command.model_copy(
                update={"reason": "Different creation request"}
            )
            with pytest.raises(HTTPException) as conflict:
                await create(sessions, fixture, changed)
            assert conflict.value.status_code == 409
            left = await revision_command(
                sessions, fixture, first, suffix="First concurrent edit"
            )
            right = await revision_command(
                sessions, fixture, first, suffix="Second concurrent edit"
            )
            outcomes = await asyncio.gather(
                revise(sessions, fixture, first, left),
                revise(sessions, fixture, first, right),
                return_exceptions=True,
            )
            assert sum(isinstance(item, dict) for item in outcomes) == 1
            failed = next(item for item in outcomes if isinstance(item, HTTPException))
            assert failed.status_code == 409
            winner = left if isinstance(outcomes[0], dict) else right
            accepted = next(item for item in outcomes if isinstance(item, dict))
            retries = await asyncio.gather(
                revise(sessions, fixture, first, winner),
                revise(sessions, fixture, first, winner),
            )
            assert retries == [accepted, accepted]
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisProtocolDraft)
                        .where(
                            AnalysisProtocolDraft.project_id == fixture.scope.project.id
                        )
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisProtocolDraftRevision)
                        .where(
                            AnalysisProtocolDraftRevision.draft_id == UUID(first["id"])
                        )
                    )
                    == 2
                )

    asyncio.run(scenario())


def test_changed_manifest_content_and_expired_or_foreign_preview_cannot_create():
    async def scenario():
        async with database() as sessions:
            fixture = await published_fixture(sessions)
            content = await draft_content(sessions, fixture)
            altered = deepcopy(content.files)
            manifest = json.loads(altered["analysis-method.json"])
            manifest["inputs"][0]["label"] += " changed"
            altered["analysis-method.json"] = json.dumps(manifest)
            async with sessions() as db:
                with pytest.raises(HTTPException) as manifest_error:
                    await api.draft_preview(
                        content.model_copy(update={"files": altered}),
                        fixture.scope.analyst,
                        db,
                    )
                assert manifest_error.value.status_code == 422
            command = await creation_command(sessions, fixture, content)
            modified = deepcopy(command.files)
            modified["protocol.aimd"] += "\nChanged after preview.\n"
            with pytest.raises(HTTPException) as changed:
                await create(
                    sessions, fixture, command.model_copy(update={"files": modified})
                )
            assert changed.value.status_code == 409
            now = datetime.now(UTC)
            expired = jwt.encode(
                {
                    "aud": service.AUDIENCE,
                    "sub": str(fixture.scope.analyst.id),
                    "purpose": "create",
                    "digest": command.preview_digest,
                    "iat": now - timedelta(minutes=2),
                    "exp": now - timedelta(minutes=1),
                },
                config.SECRET_KEY,
                algorithm="HS256",
            )
            with pytest.raises(HTTPException) as stale:
                await create(
                    sessions,
                    fixture,
                    command.model_copy(update={"preview_token": expired}),
                )
            assert stale.value.status_code == 409
            async with sessions() as db:
                with pytest.raises(HTTPException) as other:
                    await api.draft_confirm(command, fixture.scope.owner, db)
                assert other.value.status_code == 409
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisProtocolDraft)
                        .where(
                            AnalysisProtocolDraft.project_id == fixture.scope.project.id
                        )
                    )
                    == 0
                )

    asyncio.run(scenario())


def test_author_cannot_self_review_without_real_approval_capability_or_edit_after_apply():
    async def scenario():
        async with database() as sessions:
            fixture = await published_fixture(sessions)
            draft = await create(sessions, fixture)
            with pytest.raises(HTTPException) as denied:
                await review(sessions, fixture, draft, user=fixture.scope.analyst)
            assert denied.value.status_code == 403
            with pytest.raises(HTTPException) as unreviewed:
                await publish_command(sessions, fixture, draft)
            assert unreviewed.value.status_code == 403
            rejected = await review(sessions, fixture, draft, decision="rejected")
            assert rejected["state"] == "rejected"
            with pytest.raises(HTTPException) as rejection:
                await publish_command(sessions, fixture, rejected)
            assert rejection.value.status_code == 403
            revised = await revise(
                sessions,
                fixture,
                rejected,
                await revision_command(sessions, fixture, rejected),
            )
            approved = await review(sessions, fixture, revised)
            command = await publish_command(sessions, fixture, approved)
            results = await asyncio.gather(
                publish(sessions, fixture, approved, command),
                publish(sessions, fixture, approved, command),
            )
            assert results[0] == results[1]
            assert results[0]["permissions"] == {
                "can_edit": False,
                "can_review": False,
                "can_publish": False,
            }
            with pytest.raises(HTTPException) as applied_edit:
                await revision_command(sessions, fixture, results[0])
            assert applied_edit.value.status_code == 403
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisProtocolMethodLink)
                        .where(AnalysisProtocolMethodLink.draft_id == UUID(draft["id"]))
                    )
                    == 1
                )

    asyncio.run(scenario())


def test_revoked_reviewer_and_single_source_permissions_block_publication():
    async def scenario():
        async with database() as sessions:
            fixture = await published_fixture(sessions)
            draft = await review(sessions, fixture, await create(sessions, fixture))
            command = await publish_command(sessions, fixture, draft)
            async with sessions() as db:
                await db.execute(
                    update(LabUser)
                    .where(
                        LabUser.lab_id == fixture.scope.lab.id,
                        LabUser.user_id == fixture.scope.owner.id,
                    )
                    .values(role=LabRole.MEMBER)
                )
                await db.execute(
                    update(ProjectUser)
                    .where(
                        ProjectUser.project_id == fixture.scope.project.id,
                        ProjectUser.user_id == fixture.scope.owner.id,
                    )
                    .values(role=ProjectRole.COLLABORATOR)
                )
                await db.commit()
            with pytest.raises(HTTPException) as reviewer:
                await publish(sessions, fixture, draft, command)
            assert reviewer.value.status_code == 403
            async with sessions() as db:
                await db.execute(
                    update(LabUser)
                    .where(
                        LabUser.lab_id == fixture.scope.lab.id,
                        LabUser.user_id == fixture.scope.owner.id,
                    )
                    .values(role=LabRole.OWNER)
                )
                await db.execute(
                    update(ProjectUser)
                    .where(
                        ProjectUser.project_id == fixture.scope.project.id,
                        ProjectUser.user_id == fixture.scope.owner.id,
                    )
                    .values(role=ProjectRole.OWNER)
                )
                await db.execute(
                    update(Project)
                    .where(Project.id == fixture.scope.project.id)
                    .values(
                        type=ProjectType.PRIVATE,
                        permission_type=PermissionType.PROTOCOL_LEVEL,
                    )
                )
                # COLLABORATOR (30) bypasses the legacy protocol-level branch
                # gated at PROTOCOL_OWNER (35). A Recorder plus explicit grants
                # exercises actual read_protocol revocation, not Record ACLs.
                await db.execute(
                    update(ProjectUser)
                    .where(
                        ProjectUser.project_id == fixture.scope.project.id,
                        ProjectUser.user_id == fixture.scope.analyst.id,
                    )
                    .values(role=ProjectRole.RECORDER)
                )
                for source in (fixture.scope, fixture.fixture.second):
                    db.add(
                        ProtocolUser(
                            protocol_id=source.protocol.id,
                            user_id=fixture.scope.analyst.id,
                            role=ProjectRole.RECORDER,
                            create_user_id=fixture.scope.owner.id,
                        )
                    )
                await db.commit()
            async with sessions() as db:
                project = await db.get(Project, fixture.scope.project.id)
                assert project.type == ProjectType.PRIVATE
                assert (
                    await db.scalar(
                        select(ProjectUser.role).where(
                            ProjectUser.project_id == project.id,
                            ProjectUser.user_id == fixture.scope.analyst.id,
                        )
                    )
                    == ProjectRole.RECORDER
                )
                for source in (fixture.scope, fixture.fixture.second):
                    await require_protocol_read(
                        db,
                        fixture.scope.analyst,
                        project,
                        await db.get(Protocol, source.protocol.id),
                    )
                assert (
                    await api.read_draft(UUID(draft["id"]), fixture.scope.analyst, db)
                )["id"] == draft["id"]
                await db.execute(
                    delete(ProtocolUser).where(
                        ProtocolUser.protocol_id == fixture.fixture.second.protocol.id,
                        ProtocolUser.user_id == fixture.scope.analyst.id,
                    )
                )
                await db.commit()
            async with sessions() as db:
                project = await db.get(Project, fixture.scope.project.id)
                await require_protocol_read(
                    db,
                    fixture.scope.analyst,
                    project,
                    await db.get(Protocol, fixture.scope.protocol.id),
                )
                with pytest.raises(HTTPException) as revoked_schema:
                    await require_protocol_read(
                        db,
                        fixture.scope.analyst,
                        project,
                        await db.get(Protocol, fixture.fixture.second.protocol.id),
                    )
                assert revoked_schema.value.status_code == 403
            for operation in (
                lambda: publish(sessions, fixture, draft, command),
                lambda: publish_command(sessions, fixture, draft),
            ):
                with pytest.raises(HTTPException) as source_access:
                    await operation()
                assert source_access.value.status_code in {403, 404}
            async with sessions() as db:
                assert (
                    await db.get(AnalysisProtocolDraft, UUID(draft["id"]))
                ).state == "reviewed"
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisProtocolMethodLink)
                        .where(AnalysisProtocolMethodLink.draft_id == UUID(draft["id"]))
                    )
                    == 0
                )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "attack", ["changed_files", "environment", "other_source", "missing_preview"]
)
def test_upload_cannot_replace_the_reviewed_package_or_smuggle_source_metadata(attack):
    async def scenario():
        async with database() as sessions:
            fixture = await published_fixture(sessions)
            draft = await review(sessions, fixture, await create(sessions, fixture))
            command = await publish_command(sessions, fixture, draft)
            modified = deepcopy(draft["current_revision"]["files"])
            if attack == "changed_files":
                modified["protocol.aimd"] += "\nUnreviewed extra instructions.\n"
            content = BytesIO()
            with ZipFile(content, "w") as archive:
                for name, value in modified.items():
                    archive.writestr(name, value)
            async with sessions() as db:
                upload = UploadFile(
                    BytesIO(content.getvalue()),
                    filename="modified.zip",
                    headers=Headers({"content-type": "application/zip"}),
                )
                try:
                    with pytest.raises(HTTPException) as changed:
                        await protocol_versions.upload_package(
                            fixture.scope.analyst,
                            db,
                            upload,
                            BackgroundTasks(),
                            project_id=fixture.scope.project.id,
                            env_vars="UNREVIEWED_VALUE=1"
                            if attack == "environment"
                            else "",
                            protocol_id=None,
                            source_knowledge_item_id=uuid4()
                            if attack == "other_source"
                            else None,
                            source_knowledge_revision=None,
                            source_protocol_improvement_id=None,
                            source_protocol_improvement_revision=None,
                            source_analysis_protocol_draft_id=UUID(draft["id"]),
                            source_analysis_protocol_revision=draft["revision"],
                            source_analysis_protocol_digest=draft["package_digest"],
                            source_analysis_protocol_preview_digest=command.preview_digest,
                            source_analysis_protocol_preview_token=None
                            if attack == "missing_preview"
                            else command.preview_token,
                        )
                    assert changed.value.status_code == (
                        409 if attack == "changed_files" else 422
                    )
                finally:
                    await upload.close()
                await db.rollback()
            async with sessions() as db:
                assert (
                    await db.get(AnalysisProtocolDraft, UUID(draft["id"]))
                ).state == "reviewed"
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisProtocolMethodLink)
                        .where(AnalysisProtocolMethodLink.draft_id == UUID(draft["id"]))
                    )
                    == 0
                )

    asyncio.run(scenario())


def test_crlf_package_bytes_survive_real_publication_and_inaccessible_lineage_is_hidden():
    async def scenario():
        async with database() as sessions:
            fixture = await published_fixture(sessions)
            content = await draft_content(sessions, fixture)
            files = {
                name: value.replace("\r\n", "\n").replace("\n", "\r\n")
                for name, value in content.files.items()
            }
            assert all("\r\n" in value for value in files.values())
            content = content.model_copy(update={"files": files})
            draft = await create(
                sessions, fixture, await creation_command(sessions, fixture, content)
            )
            applied = await publish(
                sessions, fixture, await review(sessions, fixture, draft)
            )
            _, archive = await assert_normal_protocol(sessions, fixture, applied, files)
            with ZipFile(BytesIO(archive)) as zipped:
                for name, value in files.items():
                    assert zipped.read(name) == value.encode("utf-8")
            async with sessions() as db:
                await db.execute(
                    update(Project)
                    .where(Project.id == fixture.scope.project.id)
                    .values(permission_type=PermissionType.PROTOCOL_LEVEL)
                )
                db.add(
                    ProtocolUser(
                        protocol_id=UUID(applied["applied"]["protocol_id"]),
                        user_id=fixture.scope.recorder.id,
                        role=ProjectRole.RECORDER,
                        create_user_id=fixture.scope.owner.id,
                    )
                )
                await db.commit()
            async with sessions() as db:
                ordinary = await protocols.get_protocol_by_id(
                    UUID(applied["applied"]["protocol_id"]),
                    db,
                    fixture.scope.recorder,
                    version=applied["applied"]["version"],
                )
                assert ordinary["aimd"] == files["protocol.aimd"].replace("\r\n", "\n")
                assert ordinary["analysis_method_sources"] == []
                with pytest.raises(HTTPException) as private_source:
                    await api.read_draft(UUID(draft["id"]), fixture.scope.recorder, db)
                assert private_source.value.status_code in {403, 404}

    asyncio.run(scenario())


def test_two_reviewed_updates_to_same_base_cannot_both_publish():
    async def scenario():
        async with database() as sessions:
            fixture = await published_fixture(sessions)
            original = await publish(
                sessions,
                fixture,
                await review(sessions, fixture, await create(sessions, fixture)),
            )
            await grant_version_management(sessions, fixture)
            drafts = []
            for version in ("0.2.0", "0.3.0"):
                content = await draft_content(
                    sessions,
                    fixture,
                    target=original["applied"]["protocol_id"],
                    version=version,
                )
                draft = await create(
                    sessions,
                    fixture,
                    await creation_command(sessions, fixture, content),
                )
                drafts.append(await review(sessions, fixture, draft))
            commands = [
                await publish_command(sessions, fixture, draft) for draft in drafts
            ]
            results = await asyncio.gather(
                *(
                    publish(sessions, fixture, draft, command)
                    for draft, command in zip(drafts, commands, strict=True)
                ),
                return_exceptions=True,
            )
            diagnostics = race_diagnostics(results)
            assert sum(isinstance(item, dict) for item in results) == 1, diagnostics
            assert sum(isinstance(item, HTTPException) for item in results) == 1, (
                diagnostics
            )
            failure = next(item for item in results if isinstance(item, HTTPException))
            assert failure.status_code == 409 and "advanced" in failure.detail, (
                diagnostics
            )
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ProtocolVersion)
                        .where(
                            ProtocolVersion.protocol_id
                            == UUID(original["applied"]["protocol_id"])
                        )
                    )
                    == 2
                )
                assert (
                    await api.read_draft(
                        UUID(original["id"]), fixture.scope.analyst, db
                    )
                )["applied"] == original["applied"]
            await assert_normal_protocol(
                sessions, fixture, original, original["current_revision"]["files"]
            )

    asyncio.run(scenario())


def test_ordinary_upload_and_reviewed_publication_share_the_same_uid_lock():
    async def scenario():
        async with database() as sessions:
            fixture = await published_fixture(sessions)
            uid = f"shared_publication_{uuid4().hex}"
            content = await draft_content(sessions, fixture, uid=uid)
            draft = await review(
                sessions,
                fixture,
                await create(
                    sessions,
                    fixture,
                    await creation_command(sessions, fixture, content),
                ),
            )
            command = await publish_command(sessions, fixture, draft)
            package_bytes = BytesIO()
            with ZipFile(package_bytes, "w") as archive:
                # The ordinary route receives a normal AIMD/TOML package. Its
                # matching ID must still contend with the reviewed route.
                for name in ("protocol.toml", "protocol.aimd"):
                    archive.writestr(name, content.files[name])
            backend_ids = {}

            async def governed():
                async with sessions() as db:
                    backend_ids["governed"] = await db.scalar(
                        text("SELECT pg_backend_pid()")
                    )
                    return await api.publish_draft(
                        UUID(draft["id"]),
                        command,
                        fixture.scope.analyst,
                        db,
                        BackgroundTasks(),
                    )

            async def ordinary():
                async with sessions() as db:
                    backend_ids["ordinary"] = await db.scalar(
                        text("SELECT pg_backend_pid()")
                    )
                    upload = UploadFile(
                        BytesIO(package_bytes.getvalue()),
                        filename="ordinary.zip",
                        headers=Headers({"content-type": "application/zip"}),
                    )
                    try:
                        return await protocol_versions.upload_package(
                            fixture.scope.analyst,
                            db,
                            upload,
                            BackgroundTasks(),
                            project_id=fixture.scope.project.id,
                            env_vars="",
                            protocol_id=None,
                            source_knowledge_item_id=None,
                            source_knowledge_revision=None,
                            source_protocol_improvement_id=None,
                            source_protocol_improvement_revision=None,
                        )
                    finally:
                        await upload.close()

            tasks = []
            try:
                async with sessions() as holder:
                    holder_id = await holder.scalar(text("SELECT pg_backend_pid()"))
                    await lock_protocol_uid(holder, fixture.scope.project.id, uid)
                    tasks = [
                        asyncio.create_task(governed()),
                        asyncio.create_task(ordinary()),
                    ]

                    async def wait_for_both_uid_waiters():
                        async with sessions() as observer:
                            while True:
                                # Join by the exact advisory key, not just by
                                # backend state: both real paths must use the
                                # same scope/UID serialization boundary.
                                if len(backend_ids) == 2:
                                    count = await observer.scalar(
                                        text("""
                                            SELECT count(*) FROM pg_locks waiter
                                            JOIN pg_locks held
                                              ON held.locktype = waiter.locktype
                                             AND held.database = waiter.database
                                             AND held.classid = waiter.classid
                                             AND held.objid = waiter.objid
                                             AND held.objsubid = waiter.objsubid
                                            WHERE waiter.locktype = 'advisory'
                                              AND NOT waiter.granted
                                              AND held.granted
                                              AND held.pid = :holder
                                              AND waiter.pid IN (:governed, :ordinary)
                                        """),
                                        {"holder": holder_id, **backend_ids},
                                    )
                                    if count == 2:
                                        return
                                if any(task.done() for task in tasks):
                                    pytest.fail(
                                        "A publication path finished before reaching the shared UID lock"
                                    )
                                await asyncio.sleep(0.05)

                    await asyncio.wait_for(wait_for_both_uid_waiters(), timeout=30)
                    assert all(not task.done() for task in tasks)
                    await holder.commit()
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), timeout=60
                )
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

            successes = [result for result in results if isinstance(result, dict)]
            failures = [
                result for result in results if isinstance(result, BaseException)
            ]
            diagnostics = race_diagnostics(results)
            assert len(successes) == len(failures) == 1, diagnostics
            # An integrity exception is not an acceptable race outcome: the
            # loser must observe the winner through the guarded duplicate check.
            assert isinstance(failures[0], HTTPException), diagnostics
            assert failures[0].status_code in {400, 409}, diagnostics
            assert "already exists" in str(failures[0].detail), diagnostics
            governed_won = isinstance(results[0], dict)
            async with sessions() as db:
                matching = list(
                    (
                        await db.scalars(
                            select(Protocol).where(
                                Protocol.project_id == fixture.scope.project.id,
                                Protocol.uid == uid,
                            )
                        )
                    ).all()
                )
                assert len(matching) == 1
                versions = list(
                    (
                        await db.scalars(
                            select(ProtocolVersion).where(
                                ProtocolVersion.protocol_id == matching[0].id
                            )
                        )
                    ).all()
                )
                assert len(versions) == 1
                stored_draft = await db.get(AnalysisProtocolDraft, UUID(draft["id"]))
                assert stored_draft.state == ("applied" if governed_won else "reviewed")
                links = await db.scalar(
                    select(func.count())
                    .select_from(AnalysisProtocolMethodLink)
                    .where(AnalysisProtocolMethodLink.draft_id == stored_draft.id)
                )
                assert links == int(governed_won)
                stored_package = b"".join(
                    [
                        chunk
                        async for chunk in versions[0].download_package_with_stream()
                    ]
                )
                with ZipFile(BytesIO(stored_package)) as archive:
                    assert (
                        archive.read("protocol.aimd").decode()
                        == content.files["protocol.aimd"]
                    )
                ordinary_info = await protocols.get_protocol_by_id(
                    matching[0].id,
                    db,
                    fixture.scope.analyst,
                    version=versions[0].version,
                )
                assert len(ordinary_info["analysis_method_sources"]) == int(
                    governed_won
                )
            if governed_won:
                await assert_normal_protocol(
                    sessions, fixture, results[0], content.files
                )

    asyncio.run(scenario())


def test_upload_rejects_crossed_draft_target_before_locking_another_protocol():
    async def scenario():
        async with database() as sessions:
            fixture = await published_fixture(sessions)
            await grant_version_management(sessions, fixture)
            targets = (fixture.scope.protocol.id, fixture.fixture.second.protocol.id)
            drafts = []
            for target in targets:
                content = await draft_content(
                    sessions, fixture, target=target, version="1.1.0"
                )
                draft = await create(
                    sessions,
                    fixture,
                    await creation_command(sessions, fixture, content),
                )
                drafts.append(await review(sessions, fixture, draft))
            command = await publish_command(sessions, fixture, drafts[0])
            package_bytes = BytesIO()
            with ZipFile(package_bytes, "w") as archive:
                for name, value in drafts[0]["current_revision"]["files"].items():
                    archive.writestr(name, value)

            async with sessions() as holder:
                await holder.scalar(
                    select(Protocol).where(Protocol.id == targets[1]).with_for_update()
                )
                async with sessions() as db:
                    # An accidental second-target lock must fail this test
                    # promptly; the expected path rejects IDs before that lock.
                    await db.execute(text("SET LOCAL lock_timeout = '500ms'"))
                    upload = UploadFile(
                        BytesIO(package_bytes.getvalue()),
                        filename="crossed-target.zip",
                        headers=Headers({"content-type": "application/zip"}),
                    )
                    try:
                        with pytest.raises(HTTPException) as crossed:
                            await protocol_versions.upload_package(
                                fixture.scope.analyst,
                                db,
                                upload,
                                BackgroundTasks(),
                                project_id=fixture.scope.project.id,
                                protocol_id=targets[1],
                                env_vars="",
                                source_knowledge_item_id=None,
                                source_knowledge_revision=None,
                                source_protocol_improvement_id=None,
                                source_protocol_improvement_revision=None,
                                source_analysis_protocol_draft_id=UUID(drafts[0]["id"]),
                                source_analysis_protocol_revision=drafts[0]["revision"],
                                source_analysis_protocol_digest=drafts[0][
                                    "package_digest"
                                ],
                                source_analysis_protocol_preview_digest=command.preview_digest,
                                source_analysis_protocol_preview_token=command.preview_token,
                            )
                        assert crossed.value.status_code == 422
                        assert (
                            crossed.value.detail
                            == "Analysis draft targets another Protocol or Project"
                        )
                    finally:
                        await upload.close()
                await holder.rollback()
            async with sessions() as db:
                for draft in drafts:
                    assert (
                        await db.get(AnalysisProtocolDraft, UUID(draft["id"]))
                    ).state == "reviewed"
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisProtocolMethodLink)
                        .where(
                            AnalysisProtocolMethodLink.draft_id.in_(
                                [UUID(draft["id"]) for draft in drafts]
                            )
                        )
                    )
                    == 0
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ProtocolVersion)
                        .where(ProtocolVersion.protocol_id.in_(targets))
                    )
                    == 2
                )

    asyncio.run(scenario())


def test_actual_database_rejects_history_mutations_scope_moves_and_partial_states():
    async def scenario():
        async with database() as sessions:
            fixture = await published_fixture(sessions)
            draft = await create(sessions, fixture)

            async def reject_sql(statement):
                async with sessions() as db:
                    with pytest.raises(DBAPIError):
                        await db.execute(statement)
                        await db.commit()
                    await db.rollback()

            identity = UUID(draft["id"])
            await reject_sql(
                update(AnalysisProtocolDraft)
                .where(AnalysisProtocolDraft.id == identity)
                .values(state="reviewed")
            )
            await reject_sql(
                update(AnalysisProtocolDraft)
                .where(AnalysisProtocolDraft.id == identity)
                .values(revision=2)
            )
            await reject_sql(
                update(AnalysisProtocolDraftRevision)
                .where(AnalysisProtocolDraftRevision.draft_id == identity)
                .values(reason="Changed sealed revision")
            )
            await reject_sql(
                delete(AnalysisProtocolDraftRevision).where(
                    AnalysisProtocolDraftRevision.draft_id == identity
                )
            )
            applied = await publish(
                sessions, fixture, await review(sessions, fixture, draft)
            )
            async with sessions() as db:
                other_project = Project(
                    id=uuid4(),
                    lab_id=fixture.scope.lab.id,
                    uid=f"other_{uuid4().hex}",
                    name="Other synthetic Project",
                    type=ProjectType.PRIVATE,
                    create_user_id=fixture.scope.owner.id,
                )
                db.add(other_project)
                await db.commit()
            for statement in (
                update(AnalysisProtocolDraft)
                .where(AnalysisProtocolDraft.id == identity)
                .values(state="draft"),
                delete(AnalysisProtocolDraft).where(
                    AnalysisProtocolDraft.id == identity
                ),
                update(AnalysisProtocolDraftReview)
                .where(AnalysisProtocolDraftReview.draft_id == identity)
                .values(note="Changed review"),
                delete(AnalysisProtocolDraftReview).where(
                    AnalysisProtocolDraftReview.draft_id == identity
                ),
                update(AnalysisProtocolMethodLink)
                .where(AnalysisProtocolMethodLink.draft_id == identity)
                .values(package_digest="0" * 64),
                delete(AnalysisProtocolMethodLink).where(
                    AnalysisProtocolMethodLink.draft_id == identity
                ),
                update(Protocol)
                .where(Protocol.id == UUID(applied["applied"]["protocol_id"]))
                .values(project_id=other_project.id),
                update(ProtocolVersion)
                .where(
                    ProtocolVersion.id
                    == UUID(applied["applied"]["protocol_version_id"])
                )
                .values(protocol_id=fixture.scope.protocol.id),
            ):
                await reject_sql(statement)
            async with sessions() as db:
                # Real deferred constraints, not source-code assertions.
                await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                persisted = await api.read_draft(identity, fixture.scope.analyst, db)
                assert persisted == applied

    asyncio.run(scenario())
