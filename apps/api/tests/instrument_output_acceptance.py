"""Synthetic raw files through actual scoped API, PostgreSQL and object storage."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
from sqlalchemy import func, select

from app.config import config
from app.database import sessionmanager
from app.main import app
from app.models.instrument_output import (
    InstrumentOutput,
    InstrumentOutputAssociation,
    InstrumentOutputBatch,
)
from app.models.knowledge import ResearchFile, ResearchFileAccessAudit, ResearchFileBlob
from app.models.lab import LabUser
from app.models.project import Project, ProjectRole, ProjectType, ProjectUser
from app.models.protocol import Protocol
from app.models.record import Record
from app.models.research import ResearchAction
from app.models.research_asset import DataAsset, DataAssetVersion
from app.models.user import User


async def exercise_sdk_delivery(runtime, local, root, activation, token, job):
    """Real SDK state machine + actual ASGI/PG/Minio, synthetic acquisition only."""
    from airalogy_instrument_gateway import (
        GatewayConfig,
        GatewayRuntime,
        InstrumentResult,
        StateStore,
    )
    from airalogy_instrument_gateway.client import GatewayAPIError, _file_body
    from airalogy_instrument_gateway.installation_manager import read_request
    from airalogy_instrument_gateway.managed_runtime import (
        ManagedAdapter,
        ManagedClient,
        file_contracts,
    )
    from test_output_delivery import FileAdapter

    loop = asyncio.get_running_loop()
    paths = []
    lose_upload = [True]

    async def request(method, path, payload, lease_token, binary):
        paths.append(path)
        headers = {"X-Airalogy-Gateway-Token": token}
        if lease_token:
            headers["X-Airalogy-Instrument-Lease"] = lease_token
        if binary:
            stream, size, media_type, checksum = binary
            content = b"".join(_file_body(stream, size, checksum))
            headers.update(
                {
                    "Content-Length": str(size),
                    "Content-Type": media_type,
                    "X-Airalogy-Content-SHA256": checksum,
                }
            )
        else:
            content = json.dumps(payload or {}).encode()
            headers["Content-Type"] = "application/json"
        response = await local.request(method, path, headers=headers, content=content)
        assert response.status_code == 200, response.text
        if method == "PUT" and lose_upload[0]:
            lose_upload[0] = False
            raise GatewayAPIError("Synthetic connection lost after actual asset commit")
        return response.json()

    class Client(ManagedClient):
        def _request(
            self, method, path, *, payload=None, lease_token=None, binary=None
        ):
            return asyncio.run_coroutine_threadsafe(
                request(method, path, payload, lease_token, binary), loop
            ).result(timeout=30)

    source = root / "runtime-source"
    source.mkdir(mode=0o700)
    store = StateStore(root / "state.json")
    config = GatewayConfig(
        platform_url="http://127.0.0.1",
        gateway_token=token,
        adapter_name="synthetic",
        adapter_config=None,
        state_file=store.path,
        output_root=source,
    )
    driver = FileAdapter(source)
    driver.identity = lambda: activation["target"]
    driver.transform = lambda value: InstrumentResult(
        {"value": 0.84, "unit": "synthetic_unit", "simulation_only": True},
        [{**value.files[0], "name": "synthetic.csv"}],
    )
    adapter = ManagedAdapter(
        driver,
        activation,
        lambda: None,
        file_contracts=file_contracts(read_request(root / "private.json")),
    )
    client = Client(
        {"platform_url": "http://127.0.0.1", "gateway_token": token},
        activation,
        file_delivery_enabled=True,
    )
    controller = GatewayRuntime(config, client, adapter, store)
    try:
        await asyncio.to_thread(controller.run_once)
    except GatewayAPIError as error:
        assert "actual asset commit" in str(error)
    else:
        raise AssertionError("Lost upload response was not exercised")
    assert store.load().phase == "outputs_pending"
    before = await runtime.json("GET", f"/research-instrument-jobs/{job['id']}/outputs")
    assert (
        before["state"] == "awaiting_files"
        and before["items"][0]["state"] == "registered"
    )
    (source / "export/result.csv").unlink()
    (source / "export").rmdir()
    source.rmdir()
    await asyncio.to_thread(GatewayRuntime(config, client, None, store).recover_pending)
    after = await runtime.json("GET", f"/research-instrument-jobs/{job['id']}/outputs")
    assert after["state"] == "delivered" and after["items"] == before["items"]
    assert store.load() is None and driver.executions == 1 and driver.stops == 0
    assert sum(path.endswith("/start") for path in paths) == 1
    assert sum(path.endswith("/lease") for path in paths) == 1
    async with sessionmanager.session() as db:
        asset = await db.get(DataAsset, UUID(after["items"][0]["data_asset_id"]))
        assert asset.status == "draft"


async def exercise_outputs(
    runtime, local, leased, root, monkeypatch, *, cancel_before_finalize=False
):
    from airalogy_instrument_gateway.output_capture import CaptureStore

    envelope = leased["job"]
    job_id = envelope["job_id"]
    plan = envelope["file_outputs"]["plan"]
    public = f"/research-instrument-jobs/{job_id}/outputs"
    receiving = f"/instrument-gateway/v1/jobs/{job_id}/outputs"
    assert plan["job_id"] == job_id and len(plan["outputs"]) == 1
    assert (
        envelope["file_outputs"]["destination"]["project_id"]
        == runtime.seed["project"]["id"]
    )
    raw = f"sample,signal\n{uuid4().hex},0.84\n".encode()
    source = root / "synthetic-exports"
    source.mkdir(mode=0o700)
    (source / "synthetic.csv").write_bytes(raw)
    sources = [
        {
            "name": "synthetic.csv",
            "path": "synthetic.csv",
            "write_complete_confirmed": True,
            "captured_at": "2026-09-09T15:16:17.123+08:00",
            "original_units": ["signal: synthetic_unit"],
            "conversion_rules": [],
            "completion_reference": "Synthetic closed-file fixture; not hardware evidence",
        }
    ]
    store = CaptureStore(root / "outbox", quiet_seconds=0.01)
    await asyncio.to_thread(store.prepare, plan, source, sources)
    capture = await asyncio.to_thread(store.capture, plan)
    before = await runtime.json("GET", public)
    assert before["context"]["project_id"] == runtime.seed["project"]["id"]
    assert before["permissions"]["associate"] is True
    assert before["state"] == "awaiting_files"
    assert before["items"][0]["state"] == "awaiting_capture"
    async with sessionmanager.session() as db:
        action = await db.get(ResearchAction, UUID(envelope["action_id"]))
        assert (
            action.status == "waiting"
            and action.output_data["file_delivery"] == "awaiting_files"
        )
    assert (
        await local.post(receiving + "/finalize", json={"capture": capture})
    ).status_code == 409
    bad = {**capture, "plan_digest": "0" * 64}
    assert (
        await local.post(receiving + "/capture", json={"capture": bad})
    ).status_code == 422
    reported = await local.post(receiving + "/capture", json={"capture": capture})
    assert reported.status_code == 200, reported.text
    assert (
        await local.post(receiving + "/capture", json={"capture": capture})
    ).json() == reported.json()
    changed = {**capture, "files": [{**capture["files"][0], "sha256": "0" * 64}]}
    assert (
        await local.post(receiving + "/capture", json={"capture": changed})
    ).status_code == 409
    output = reported.json()["items"][0]
    url = receiving + "/" + output["id"]
    headers = {
        "Content-Type": "text/csv",
        "X-Airalogy-Content-SHA256": hashlib.sha256(raw).hexdigest(),
    }
    assert (
        await local.put(url, content=b"x" * len(raw), headers=headers)
    ).status_code == 422
    assert (
        await local.put(url, content=raw + b"x", headers=headers)
    ).status_code == 409
    assert (
        await local.put(receiving + "/" + str(uuid4()), content=raw, headers=headers)
    ).status_code == 404
    # Quota failure creates neither a logical file nor an asset. It is retryable
    # file delivery, not a new physical execution.
    with monkeypatch.context() as patch:
        patch.setattr(config, "KNOWLEDGE_USER_STORAGE_QUOTA_BYTES", 0)
        assert (await local.put(url, content=raw, headers=headers)).status_code == 413
    # Withdraw actual membership during external object-storage latency. Bytes
    # may have reached private blob storage, but no scope-bearing asset may commit.
    import app.routers.instrument_outputs as output_routes

    original_upload = output_routes.upload_file
    withdrawn = []

    async def storage_then_revoke(*args, **kwargs):
        await original_upload(*args, **kwargs)
        async with sessionmanager.session() as db:
            batch = await db.get(InstrumentOutputBatch, UUID(job_id))
            member = await db.scalar(
                select(LabUser).where(
                    LabUser.user_id == batch.created_by_user_id,
                    LabUser.lab_id == UUID(runtime.seed["lab"]["id"]),
                )
            )
            withdrawn.append(
                {
                    column.name: getattr(member, column.name)
                    for column in LabUser.__table__.columns
                }
            )
            await db.delete(member)
            await db.commit()

    try:
        with monkeypatch.context() as patch:
            patch.setattr(output_routes, "upload_file", storage_then_revoke)
            rejected = await local.put(url, content=raw, headers=headers)
            assert rejected.status_code == 403, rejected.text
        async with sessionmanager.session() as db:
            pending_output = await db.get(InstrumentOutput, UUID(output["id"]))
            assert (
                pending_output.research_file_id is None
                and pending_output.data_asset_version_id is None
            )
    finally:
        async with sessionmanager.session() as db:
            for membership_values in withdrawn:
                db.add(LabUser(**membership_values))
            await db.commit()
    receipts = await asyncio.gather(
        *(local.put(url, content=raw, headers=headers) for _ in range(2))
    )
    assert all(item.status_code == 200 for item in receipts), [
        item.text for item in receipts
    ]
    assert receipts[0].json() == receipts[1].json()
    receipt = receipts[0].json()
    assert receipt["sha256"] == hashlib.sha256(raw).hexdigest()
    async with sessionmanager.session() as db:
        version = await db.get(DataAssetVersion, UUID(receipt["data_asset_version_id"]))
        asset = await db.get(DataAsset, version.data_asset_id)
        file = await db.get(ResearchFile, version.research_file_id)
        assert asset.status == "draft" and asset.current_version == 1
        assert (
            file.project_id == UUID(runtime.seed["project"]["id"])
            and file.visibility == "project"
        )
        assert version.source["job_id"] == job_id
        assert (
            version.source["installation"]["installation_id"]
            == envelope["activation"]["installation_id"]
        )
        assert version.version_metadata["captured_at"].endswith("+08:00")
        assert (
            version.version_metadata["original_units"] == sources[0]["original_units"]
        )
        assert "received_at" in version.version_metadata
        assert (
            await db.scalar(
                select(func.count())
                .select_from(DataAssetVersion)
                .where(DataAssetVersion.research_file_id == file.id)
            )
            == 1
        )
        # Even deduplication against a blob tagged with a browser-active type
        # must not turn this logical raw instrument file into inline content.
        blob = await db.get(ResearchFileBlob, file.blob_id)
        blob.content_type = "text/html"
        await db.commit()
    token = await runtime.json(
        "POST",
        f"/knowledge/files/{receipt['research_file_id']}/token",
        {"mode": "preview"},
    )
    downloaded = await runtime.client.get(token["url"])
    assert downloaded.status_code == 200 and downloaded.content == raw
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert downloaded.headers["content-type"] == "application/octet-stream"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as anonymous:
        assert (await anonymous.get(public)).status_code == 401
        assert (await anonymous.get(token["url"])).status_code == 401
    # A paired Gateway credential is not a general user/file-download credential.
    assert (await local.get(public)).status_code == 401
    assert (await local.get(token["url"])).status_code == 401
    # Removing the receiving user's Lab membership revokes even retries with a
    # previously valid Gateway/lease. A public Project does not reopen intake.
    async with sessionmanager.session() as db:
        file = await db.get(ResearchFile, UUID(receipt["research_file_id"]))
        author_id = file.uploaded_by_user_id
        member = await db.scalar(
            select(LabUser).where(
                LabUser.user_id == author_id, LabUser.lab_id == file.lab_id
            )
        )
        member_values = {
            column.name: getattr(member, column.name)
            for column in LabUser.__table__.columns
        }
        await db.delete(member)
        await db.commit()
    try:
        assert (
            await local.post(receiving + "/capture", json={"capture": capture})
        ).status_code == 403
        assert (await local.put(url, content=raw, headers=headers)).status_code == 403
        assert (
            await local.post(receiving + "/finalize", json={"capture": capture})
        ).status_code == 403
        assert (await runtime.client.get(public)).status_code == 403
        assert (await runtime.client.get(token["url"])).status_code == 403
    finally:
        async with sessionmanager.session() as db:
            db.add(LabUser(**member_values))
            await db.commit()
    if cancel_before_finalize:
        await runtime.transition(envelope["task_id"], "cancel")
    completed = await local.post(receiving + "/finalize", json={"capture": capture})
    assert completed.status_code == 200, completed.text
    assert completed.json()["state"] == "delivered"
    assert (
        await local.post(receiving + "/finalize", json={"capture": capture})
    ).json() == completed.json()
    async with sessionmanager.session() as db:
        action = await db.get(ResearchAction, UUID(envelope["action_id"]))
        if cancel_before_finalize:
            assert action.status == "cancelled"
        else:
            assert (
                action.status == "completed"
                and action.output_data["file_delivery"] == "delivered"
            )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ResearchFileAccessAudit)
                .where(
                    ResearchFileAccessAudit.research_file_id
                    == UUID(receipt["research_file_id"])
                )
            )
            >= 1
        )
    # Association binds a user-selected exact Record version and never changes it.
    record_fixture = runtime.seed["schema_governance"]
    record_key = (UUID(record_fixture["record_id"]), record_fixture["record_version"])
    async with sessionmanager.session() as db:
        record = await db.get(Record, record_key)
        original_data, original_hash = record.data, record.hash
        selected_protocol_id = str(record.protocol_id)
    options_url = public + f"/record-options?protocol_id={selected_protocol_id}"
    options = await runtime.json("GET", options_url + f"&q={record_key[0]}")
    assert any(
        item["record_id"] == str(record_key[0])
        and item["record_version"] == record_key[1]
        for item in options["items"]
    )
    assert all("data" not in item and "hash" not in item for item in options["items"])
    assert (await runtime.json("GET", options_url + "&q=not-a-record"))["items"] == []
    association_url = public + f"/{output['id']}/associations"
    draft = {
        "id": str(uuid4()),
        "record_id": str(record_key[0]),
        "record_version": record_key[1],
        "sample_reference": "operator-selected synthetic sample",
        "expected_association_id": None,
    }
    preview = await runtime.json("POST", association_url + "/preview", draft)
    assert preview["record"]["record_id"] == str(record_key[0])
    assert preview["output"]["sha256"] == hashlib.sha256(raw).hexdigest()
    confirm = {**draft, "preview_digest": preview["preview_digest"]}
    await runtime.json(
        "POST", association_url, {**confirm, "sample_reference": "changed"}, status=409
    )
    associations = await asyncio.gather(
        *(runtime.client.post(association_url, json=confirm) for _ in range(2))
    )
    assert all(item.status_code == 200 for item in associations), [
        item.text for item in associations
    ]
    assert associations[0].json() == associations[1].json()
    await runtime.json(
        "POST", association_url + "/preview", {**draft, "id": str(uuid4())}, status=409
    )
    await runtime.json(
        "POST",
        association_url + "/preview",
        {**draft, "record_id": str(uuid4())},
        status=404,
    )
    view = await runtime.json("GET", public)
    assert view["items"][0]["association"]["record_id"] == str(record_key[0])
    # Even an otherwise authorized operator cannot map an output across Project
    # boundaries. These rows are explicitly synthetic, not user research data.
    async with sessionmanager.session() as db:
        other_project = Project(
            lab_id=UUID(runtime.seed["lab"]["id"]),
            name="Synthetic other project",
            uid=uuid4().hex,
            type=1,
            create_user_id=author_id,
        )
        db.add(other_project)
        await db.flush()
        other_protocol = Protocol(
            project_id=other_project.id,
            user_id=author_id,
            uid=uuid4().hex,
            name="Synthetic other protocol",
            latest_version="1.0.0",
        )
        db.add(other_protocol)
        await db.flush()
        other_record = Record(
            protocol_id=other_protocol.id,
            protocol_version="1.0.0",
            user_id=author_id,
            data={},
            hash="synthetic-other-record",
        )
        db.add(other_record)
        await db.commit()
        other_id = str(other_record.id)
        other_protocol_id = str(other_protocol.id)
    await runtime.json(
        "GET", public + f"/record-options?protocol_id={other_protocol_id}", status=404
    )
    await runtime.json(
        "POST",
        association_url + "/preview",
        {
            **draft,
            "record_id": other_id,
            "record_version": 1,
            "expected_association_id": draft["id"],
        },
        status=404,
    )
    viewer = next(item for item in runtime.seed["accounts"] if item["key"] == "viewer")
    viewer_auth = await runtime.json(
        "POST",
        "/signin_by_email",
        {"email": viewer["email"], "password": viewer["password"]},
    )
    async with sessionmanager.session() as db:
        viewer_row = await db.scalar(select(User).where(User.email == viewer["email"]))
        membership = await db.scalar(
            select(ProjectUser).where(
                ProjectUser.user_id == viewer_row.id,
                ProjectUser.project_id == UUID(runtime.seed["project"]["id"]),
            )
        )
        membership_id, old_role = membership.id, membership.role
        membership.role = ProjectRole.VIEWER_SELF_ONLY
        await db.commit()
    try:
        response = await runtime.client.get(
            public, headers={"Auth-Token": viewer_auth["token"]}
        )
        assert response.status_code == 200, response.text
        assert response.json()["permissions"]["associate"] is False
        linked = response.json()["items"][0]["association"]
        assert linked == {"id": draft["id"], "state": "restricted"}
        assert "sample_reference" not in linked and "record_id" not in linked
        history = await runtime.client.get(
            association_url, headers={"Auth-Token": viewer_auth["token"]}
        )
        assert history.status_code == 200
        hidden = history.json()["items"][0]
        assert (
            hidden["state"] == "restricted"
            and "sample_reference" not in hidden
            and "record_id" not in hidden
        )
        assert (
            await runtime.client.get(
                options_url, headers={"Auth-Token": viewer_auth["token"]}
            )
        ).status_code == 403
        denied = await runtime.client.post(
            association_url + "/preview",
            json=draft,
            headers={"Auth-Token": viewer_auth["token"]},
        )
        assert denied.status_code == 403
    finally:
        async with sessionmanager.session() as db:
            membership = await db.get(ProjectUser, membership_id)
            membership.role = old_role
            await db.commit()
    # Picker filtering must happen before pagination, including own-only roles;
    # inaccessible Record existence/counts must not leak through search or pages.
    async with sessionmanager.session() as db:
        project = await db.get(Project, UUID(runtime.seed["project"]["id"]))
        old_project_type = project.type
        own_record = Record(
            protocol_id=UUID(selected_protocol_id),
            protocol_version=record_fixture["source_version"],
            user_id=viewer_row.id,
            number=9876,
            data={},
            hash="synthetic-picker-owned-record",
        )
        db.add(own_record)
        await db.commit()
        own_record_id = str(own_record.id)
    try:
        for project_type, role in (
            (ProjectType.PUBLIC, ProjectRole.RECORDER_SELF_ONLY),
            (ProjectType.PRIVATE, ProjectRole.RECORDER),
        ):
            async with sessionmanager.session() as db:
                project = await db.get(Project, UUID(runtime.seed["project"]["id"]))
                project.type = project_type
                membership = await db.get(ProjectUser, membership_id)
                membership.role = role
                await db.commit()
            response = await runtime.client.get(
                options_url + "&limit=1", headers={"Auth-Token": viewer_auth["token"]}
            )
            assert response.status_code == 200, response.text
            selected = response.json()
            assert [item["record_id"] for item in selected["items"]] == [own_record_id]
            assert selected["has_more"] is False
            hidden_search = await runtime.client.get(
                options_url + f"&q={record_key[0]}",
                headers={"Auth-Token": viewer_auth["token"]},
            )
            assert hidden_search.status_code == 200
            assert hidden_search.json()["items"] == []
    finally:
        async with sessionmanager.session() as db:
            project = await db.get(Project, UUID(runtime.seed["project"]["id"]))
            project.type = old_project_type
            membership = await db.get(ProjectUser, membership_id)
            membership.role = old_role
            own_record = await db.get(Record, (UUID(own_record_id), 1))
            await db.delete(own_record)
            await db.commit()
    async with sessionmanager.session() as db:
        record = await db.get(Record, record_key)
        assert (record.data, record.hash) == (original_data, original_hash)
        assert (
            await db.scalar(
                select(func.count())
                .select_from(InstrumentOutputAssociation)
                .where(InstrumentOutputAssociation.output_id == UUID(output["id"]))
            )
            == 1
        )
    replacement = {
        **draft,
        "id": str(uuid4()),
        "expected_association_id": draft["id"],
        "sample_reference": "corrected synthetic sample",
    }
    with monkeypatch.context() as patch:
        patch.setattr(output_routes, "utcnow", lambda: datetime(2000, 1, 1, tzinfo=UTC))
        await runtime.confirm(association_url, replacement)
    assert (await runtime.json("GET", public))["items"][0]["association"][
        "id"
    ] == replacement["id"]
    assert (await runtime.json("POST", association_url, confirm))["id"] == draft["id"]
    history = await runtime.json("GET", association_url + "?limit=1")
    assert history["has_more"] and history["items"][0]["id"] == replacement["id"]
    assert history["items"][0]["revision"] == 2
    older = await runtime.json(
        "GET", association_url + f"?limit=1&offset={history['next_offset']}"
    )
    assert older["items"][0]["id"] == draft["id"] and not older["has_more"]
    assert (await runtime.json("GET", public))["items"][0]["association"][
        "id"
    ] == replacement["id"]
    async with sessionmanager.session() as db:
        assert list(
            await db.scalars(
                select(InstrumentOutputAssociation.revision)
                .where(InstrumentOutputAssociation.output_id == UUID(output["id"]))
                .order_by(InstrumentOutputAssociation.revision)
            )
        ) == [1, 2]
