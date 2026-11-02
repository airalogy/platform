"""Delegated access against real PostgreSQL, authorization and local Protocol executor.

The independent MCP SDK drives the same ASGI transport as HTTP clients. Only
the connection factory and disposable Protocol directory are test-specific.
"""

import asyncio
import hashlib
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from importlib import import_module
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.build_info import resolve_build_info
from app.config import config
from app.database import get_db_session
from app.libs.external_request_boundary import ExternalRequestBoundary
from app.models.external_access import (
    ExternalAccessPolicy,
    ExternalAudit,
    ExternalGrant,
    ExternalOperation,
)
from app.models.lab import LabUser
from app.models.project import ProjectRole, ProjectUser
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.user import User
from app.routers import external_access as api
from app.routers.depends import create_access_token
from app.services import external_access as service
from app.services.account_security import bump_auth_version
from fastapi import FastAPI
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import delete, func, inspect, select, update

from tests.test_record_analysis_postgres import add_record, database, seed_analysis

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Dedicated PostgreSQL required",
)
CSV = "var.value,var.group\n2,A\n4,B\n"


@pytest.fixture(autouse=True)
def isolated_executor(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", False)
    monkeypatch.setattr(config, "PROTOCOL_RUN_ENV", "local")
    monkeypatch.setattr(config, "PROTOCOL_DIR", str(tmp_path))
    monkeypatch.chdir(Path(__file__).resolve().parents[1])


async def seed(sessions):
    scope = await seed_analysis(sessions)
    path = Path(config.PROTOCOL_DIR) / scope.version.package_name
    path.mkdir(parents=True)
    aimd = "{{var|value: float, ge=0, le=100}}\n{{var|group: str}}"
    (path / "protocol.aimd").write_text(aimd)
    (path / "protocol.toml").write_text(
        f'[airalogy_protocol]\nid = "{scope.protocol.uid}"\nname = "Synthetic measurement"\nversion = "1.0.0"\n'
    )
    async with sessions() as db:
        await db.execute(
            update(User).where(User.id == scope.owner.id).values(api_key_iv=uuid4().hex)
        )
        schema = {
            "vars": {
                "type": "object",
                "properties": {
                    "value": {"type": "number", "minimum": 0, "maximum": 100},
                    "group": {"type": "string"},
                },
                "required": ["value", "group"],
            }
        }
        await db.execute(
            update(ProtocolVersion)
            .where(ProtocolVersion.id == scope.version.id)
            .values(json_schema=schema, aimd=aimd)
        )
        await db.commit()
    return scope


@asynccontextmanager
async def client(sessions):
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(api.mcp_router)
    app.add_middleware(ExternalRequestBoundary)

    async def db_dependency():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db_session] = db_dependency
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as http:
        yield http


def browser(user):
    return {"Auth-Token": create_access_token(user)}


def delegated(token):
    return {"Authorization": f"Bearer {token}"}


async def grant(http, scope, *, user=None, scopes=None):
    owner = browser(scope.owner)
    response = await http.get(
        f"/external-access/labs/{scope.lab.id}/policy", headers=owner
    )
    policy = response.json()
    if not policy["enabled"]:
        response = await http.put(
            f"/external-access/labs/{scope.lab.id}/policy",
            headers=owner,
            json={
                "enabled": True,
                "blocked_fields": [],
                "expected_revision": policy["revision"],
            },
        )
        assert response.status_code == 200, response.text
    response = await http.post(
        "/external-access/grants",
        headers=browser(user or scope.owner),
        json={
            "project_id": str(scope.project.id),
            "name": "Synthetic Agent",
            "scopes": scopes or sorted(service.SCOPES),
            "expires_in_days": 1,
        },
    )
    assert response.status_code == 200, response.text
    assert "token_hash" not in response.text and "auth_version" not in response.text
    return response.json()


async def call(http, token, name, **arguments):
    return await http.post(
        f"/external-access/tools/{name}", headers=delegated(token), json=arguments
    )


async def preview(http, token, scope, **changes):
    return await call(
        http,
        token,
        "preview_import",
        **{
            "protocol_id": str(scope.protocol.id),
            "csv": CSV,
            "request_key": uuid4().hex,
            **changes,
        },
    )


async def approve(http, scope, op):
    response = await http.post(
        f"/external-access/operations/{op['id']}/decision",
        headers=browser(scope.owner),
        json={"digest": op["digest"], "approve": True},
    )
    assert response.status_code == 200, response.text


async def record_count(sessions, scope):
    async with sessions() as db:
        return await db.scalar(
            select(func.count())
            .select_from(Record)
            .where(Record.protocol_id == scope.protocol.id)
        )


def test_real_import_approval_idempotency_and_revision_history():
    async def scenario():
        async with database() as sessions, client(sessions) as http:
            scope = await seed(sessions)
            credentials = await grant(http, scope)
            token = credentials["token"]
            async with sessions() as db:
                stored = await db.get(ExternalGrant, UUID(credentials["grant"]["id"]))
                assert stored.token_hash == hashlib.sha256(token.encode()).hexdigest()
            template = await call(
                http, token, "get_protocol", protocol_id=str(scope.protocol.id)
            )
            assert template.status_code == 200
            assert template.json()["csv_template"].strip() == "var.value,var.group"
            invalid = await preview(
                http, token, scope, csv="var.value,var.group\n1000,A\n"
            )
            assert invalid.status_code == 200, invalid.text
            assert invalid.json()["state"] == "invalid"
            assert invalid.json()["errors"] and await record_count(sessions, scope) == 0
            request_key = uuid4().hex
            previews = await asyncio.gather(
                *[
                    preview(http, token, scope, request_key=request_key)
                    for _ in range(2)
                ]
            )
            assert all(p.status_code == 200 for p in previews), [
                p.text for p in previews
            ]
            op = previews[0].json()
            assert op["id"] == previews[1].json()["id"]
            assert (
                await preview(
                    http,
                    token,
                    scope,
                    request_key=request_key,
                    csv=CSV.replace("2,A", "3,A"),
                )
            ).status_code == 409
            assert (
                await call(http, token, "execute_operation", operation_id=op["id"])
            ).status_code == 409
            assert await record_count(sessions, scope) == 0
            assert (
                await http.post(
                    f"/external-access/operations/{op['id']}/decision",
                    headers=delegated(token),
                    json={"digest": op["digest"], "approve": True},
                )
            ).status_code == 401
            detail = await http.get(
                f"/external-access/operations/{op['id']}", headers=browser(scope.owner)
            )
            assert detail.json()["payload"]["csv"] == CSV
            assert "no-store" in detail.headers["cache-control"]
            await approve(http, scope, op)
            executions = await asyncio.gather(
                *[
                    call(http, token, "execute_operation", operation_id=op["id"])
                    for _ in range(2)
                ]
            )
            assert all(e.status_code == 200 for e in executions), [
                e.text for e in executions
            ]
            assert executions[0].json() == executions[1].json()
            assert await record_count(sessions, scope) == 2
            record_id = executions[0].json()["result"]["record_ids"][0]
            revision = await call(
                http,
                token,
                "preview_revision",
                protocol_id=str(scope.protocol.id),
                record_id=record_id,
                expected_version=1,
                changes={"value": 3},
                reason="Verified transcription correction",
                request_key=uuid4().hex,
            )
            assert revision.status_code == 200, revision.text
            revision = revision.json()
            assert revision["summary"]["changes"]["value"] == {"before": 2, "after": 3}
            await approve(http, scope, revision)
            result = await call(
                http, token, "execute_operation", operation_id=revision["id"]
            )
            assert result.status_code == 200, result.text
            assert result.json()["result"]["version"] == 2
            stale = await call(
                http,
                token,
                "preview_revision",
                protocol_id=str(scope.protocol.id),
                record_id=record_id,
                expected_version=1,
                changes={"value": 9},
                reason="Stale update",
                request_key=uuid4().hex,
            )
            assert stale.status_code == 409
            async with sessions() as db:
                records = (
                    await db.scalars(
                        select(Record)
                        .where(Record.id == UUID(record_id))
                        .order_by(Record.version)
                    )
                ).all()
                assert [r.data["var"]["value"] for r in records] == [2, 3]
                assert records[1].revision_reason == "Verified transcription correction"
                assert (await db.get(ExternalOperation, UUID(op["id"]))).payload == {}
                audits = (
                    await db.scalars(
                        select(ExternalAudit).where(ExternalAudit.grant_id == stored.id)
                    )
                ).all()
                assert len([a for a in audits if a.event == "operation.executed"]) == 2
                assert all(
                    "Verified transcription correction" not in str(a.detail)
                    for a in audits
                )

    asyncio.run(scenario())


def test_project_scope_current_permissions_revocation_and_secret_isolation():
    async def scenario():
        async with database() as sessions, client(sessions) as http:
            scope, other = await seed(sessions), await seed(sessions)
            disabled = await http.post(
                "/external-access/grants",
                headers=browser(scope.owner),
                json={
                    "project_id": str(scope.project.id),
                    "name": "Denied",
                    "scopes": ["protocols:read"],
                },
            )
            assert disabled.status_code == 403
            assert (
                await http.put(
                    f"/external-access/labs/{scope.lab.id}/policy",
                    headers=browser(scope.recorder),
                    json={
                        "enabled": True,
                        "blocked_fields": [],
                        "expected_revision": 0,
                    },
                )
            ).status_code == 403
            credentials = await grant(http, scope)
            token = credentials["token"]
            assert (
                await call(
                    http, token, "get_protocol", protocol_id=str(other.protocol.id)
                )
            ).status_code == 404
            assert (
                await http.get("/external-access/dashboard", headers=delegated(token))
            ).status_code == 401
            assert (
                await call(http, create_access_token(scope.owner), "access_context")
            ).status_code == 401
            readonly = await grant(http, scope, scopes=["protocols:read"])
            assert (
                await call(
                    http,
                    readonly["token"],
                    "list_records",
                    protocol_id=str(scope.protocol.id),
                )
            ).status_code == 403
            await add_record(sessions, scope, 10, "https://private.invalid/signed-file")
            rows = (
                await call(
                    http, token, "list_records", protocol_id=str(scope.protocol.id)
                )
            ).json()["items"]
            assert "group" not in rows[0]["var"] and rows[0]["withheld_fields"] == [
                "group"
            ]
            await http.put(
                f"/external-access/labs/{scope.lab.id}/policy",
                headers=browser(scope.owner),
                json={
                    "enabled": True,
                    "blocked_fields": ["value"],
                    "expected_revision": 1,
                },
            )
            response = await call(
                http, token, "list_records", protocol_id=str(scope.protocol.id)
            )
            assert response.json()["items"][0]["var"] == {}
            assert (await preview(http, token, scope)).status_code == 422
            dashboard = await http.get(
                "/external-access/dashboard", headers=browser(scope.owner)
            )
            assert token not in dashboard.text and "token_hash" not in dashboard.text
            await http.delete(
                f"/external-access/grants/{credentials['grant']['id']}",
                headers=browser(scope.owner),
            )
            assert (await call(http, token, "access_context")).status_code == 401
            async with sessions() as db:
                await db.execute(
                    delete(LabUser).where(
                        LabUser.lab_id == scope.lab.id,
                        LabUser.user_id == scope.owner.id,
                    )
                )
                await db.commit()
            assert (
                await call(http, readonly["token"], "access_context")
            ).status_code == 403

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "change",
    [
        "policy",
        "expired_operation",
        "expired_grant",
        "account",
        "project_permission",
        "protocol_version",
    ],
)
def test_approval_is_invalidated_by_current_state(change):
    async def scenario():
        async with database() as sessions, client(sessions) as http:
            scope = await seed(sessions)
            credentials = await grant(http, scope)
            token = credentials["token"]
            op_response = await preview(http, token, scope)
            assert op_response.status_code == 200, op_response.text
            op = op_response.json()
            await approve(http, scope, op)
            async with sessions() as db:
                if change == "policy":
                    await db.execute(
                        update(ExternalAccessPolicy)
                        .where(ExternalAccessPolicy.lab_id == scope.lab.id)
                        .values(enabled=False, revision=2)
                    )
                elif change == "expired_operation":
                    await db.execute(
                        update(ExternalOperation)
                        .where(ExternalOperation.id == UUID(op["id"]))
                        .values(expires_at=service.now() - timedelta(seconds=1))
                    )
                elif change == "expired_grant":
                    await db.execute(
                        update(ExternalGrant)
                        .where(ExternalGrant.id == UUID(credentials["grant"]["id"]))
                        .values(expires_at=service.now() - timedelta(seconds=1))
                    )
                elif change == "account":
                    await bump_auth_version(db, scope.owner.id)
                elif change == "project_permission":
                    await db.execute(
                        update(ProjectUser)
                        .where(
                            ProjectUser.project_id == scope.project.id,
                            ProjectUser.user_id == scope.owner.id,
                        )
                        .values(role=ProjectRole.VIEWER)
                    )
                    # A Lab Owner still has membership but its Project write role is removed.
                    from app.models.lab import LabRole

                    await db.execute(
                        update(LabUser)
                        .where(
                            LabUser.lab_id == scope.lab.id,
                            LabUser.user_id == scope.owner.id,
                        )
                        .values(role=LabRole.MEMBER)
                    )
                else:
                    from app.models.protocol import Protocol

                    await db.execute(
                        update(Protocol)
                        .where(Protocol.id == scope.protocol.id)
                        .values(latest_version="9.0.0")
                    )
                await db.commit()
            result = await call(http, token, "execute_operation", operation_id=op["id"])
            assert result.status_code in (401, 403, 404, 409), result.text
            assert await record_count(sessions, scope) == 0

    asyncio.run(scenario())


def test_independent_mcp_client_and_transport_rejections():
    async def scenario():
        async with database() as sessions, client(sessions) as http:
            scope = await seed(sessions)
            credentials = await grant(http, scope)
            http.headers.update(delegated(credentials["token"]))
            async with (
                streamable_http_client("http://test/mcp", http_client=http) as (
                    read,
                    write,
                    _,
                ),
                ClientSession(read, write) as session,
            ):
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "airalogy-platform"
                assert initialized.serverInfo.version == resolve_build_info().version
                assert len((await session.list_tools()).tools) == 8
                context = await session.call_tool("access_context", {})
                assert not context.isError and context.structuredContent["project"][
                    "id"
                ] == str(scope.project.id)
                denied = await session.call_tool(
                    "get_protocol", {"protocol_id": str(uuid4())}
                )
                assert denied.isError
                previewed = await session.call_tool(
                    "preview_import",
                    {
                        "protocol_id": str(scope.protocol.id),
                        "csv": CSV,
                        "request_key": uuid4().hex,
                    },
                )
                assert not previewed.isError, previewed
                op = previewed.structuredContent
                await approve(http, scope, op)
                done = await session.call_tool(
                    "execute_operation", {"operation_id": op["id"]}
                )
                assert (
                    not done.isError and done.structuredContent["state"] == "succeeded"
                )
            headers = {"Accept": "application/json, text/event-stream"}
            assert (
                await http.post(
                    "/mcp",
                    headers={**headers, "Origin": "https://attacker.invalid"},
                    json={},
                )
            ).status_code == 403
            assert (await http.get("/mcp")).status_code == 405
            invalid = await http.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": []},
                },
            )
            assert invalid.json()["result"]["isError"]
            assert (
                await call(
                    http, credentials["token"], "get_protocol", protocol_id="invalid"
                )
            ).status_code == 422
            oversized = await http.post(
                "/mcp", headers=headers, content=b"x" * (2 * 1024 * 1024 + 1)
            )
            assert oversized.status_code == 413

    asyncio.run(scenario())


def test_migration_roundtrip_preserves_existing_records():
    async def scenario():
        async with database() as sessions:
            scope = await seed(sessions)
            row = await add_record(sessions, scope, 3)
            async with sessions() as db:
                connection = await db.connection()

                def roundtrip(connection):
                    migration = import_module(
                        "migrations.versions.0078_external_agent_access"
                    )
                    with Operations.context(MigrationContext.configure(connection)):
                        migration.downgrade()
                        migration.upgrade()
                    for model in (
                        ExternalAccessPolicy,
                        ExternalGrant,
                        ExternalOperation,
                        ExternalAudit,
                    ):
                        columns = inspect(connection).get_columns(model.__tablename__)
                        assert {c["name"] for c in columns} == set(
                            model.__table__.c.keys()
                        )

                await connection.run_sync(roundtrip)
                assert (
                    await db.scalar(select(Record.id).where(Record.id == row.id))
                    == row.id
                )
                await (
                    db.rollback()
                )  # DDL transactional; keep earlier synthetic grants intact.

    asyncio.run(scenario())


def test_write_and_receipt_rollback_together_on_failure(monkeypatch):
    async def scenario():
        async with database() as sessions, client(sessions) as http:
            scope = await seed(sessions)
            credentials = await grant(http, scope)
            token = credentials["token"]
            op = (await preview(http, token, scope)).json()
            await approve(http, scope, op)
            original = service.audit

            def failing_audit(db, user_id, event, *args, **kwargs):
                if event == "operation.executed":
                    raise RuntimeError("Synthetic receipt persistence failure")
                return original(db, user_id, event, *args, **kwargs)

            with monkeypatch.context() as patch:
                patch.setattr(service, "audit", failing_audit)
                with pytest.raises(RuntimeError, match="Synthetic receipt"):
                    await call(http, token, "execute_operation", operation_id=op["id"])
            assert await record_count(sessions, scope) == 0
            async with sessions() as db:
                assert (
                    await db.get(ExternalOperation, UUID(op["id"]))
                ).state == "approved"
            retry = await call(http, token, "execute_operation", operation_id=op["id"])
            assert retry.status_code == 200 and await record_count(sessions, scope) == 2

    asyncio.run(scenario())


def test_two_approved_corrections_cannot_overwrite_the_same_version():
    async def scenario():
        async with database() as sessions, client(sessions) as http:
            scope = await seed(sessions)
            token = (await grant(http, scope))["token"]
            imported = (await preview(http, token, scope)).json()
            await approve(http, scope, imported)
            saved = (
                await call(
                    http, token, "execute_operation", operation_id=imported["id"]
                )
            ).json()
            record_id = saved["result"]["record_ids"][0]
            operations = []
            for value in (10, 20):
                response = await call(
                    http,
                    token,
                    "preview_revision",
                    protocol_id=str(scope.protocol.id),
                    record_id=record_id,
                    expected_version=1,
                    changes={"value": value},
                    reason="Synthetic verified correction",
                    request_key=uuid4().hex,
                )
                assert response.status_code == 200, response.text
                op = response.json()
                await approve(http, scope, op)
                operations.append(op)
            results = await asyncio.gather(
                *[
                    call(http, token, "execute_operation", operation_id=op["id"])
                    for op in operations
                ]
            )
            assert sorted(result.status_code for result in results) == [200, 409]
            async with sessions() as db:
                versions = (
                    await db.scalars(
                        select(Record)
                        .where(Record.id == UUID(record_id))
                        .order_by(Record.version)
                    )
                ).all()
                assert [row.version for row in versions] == [1, 2]
                assert versions[0].data["var"]["value"] == 2

    asyncio.run(scenario())


def test_external_validation_does_not_receive_broad_credentials():
    async def scenario():
        async with database() as sessions, client(sessions) as http:
            scope = await seed(sessions)
            from app.models.protocol import Protocol

            async with sessions() as db:
                protocol = await db.get(Protocol, scope.protocol.id)
                protocol.env_vars = "PRIVATE_PROTOCOL_TEST_SECRET=must-not-be-injected"
                await db.commit()
            path = Path(config.PROTOCOL_DIR) / scope.version.package_name
            (path / "model.py").write_text("""import os
from pydantic import BaseModel, model_validator
class VarModel(BaseModel):
    value: float
    group: str
    @model_validator(mode="after")
    def check_no_credentials(self):
        if os.environ.get("AIRALOGY_API_KEY") or os.environ.get("PRIVATE_PROTOCOL_TEST_SECRET"):
            raise ValueError("Synthetic unexpected credential injection")
        return self
""")
            token = (await grant(http, scope))["token"]
            response = await preview(http, token, scope)
            assert (
                response.status_code == 200 and response.json()["state"] == "pending"
            ), response.text

    asyncio.run(scenario())


def test_self_only_record_permissions_and_deleted_records_stay_private():
    async def scenario():
        async with database() as sessions, client(sessions) as http:
            scope = await seed(sessions)
            own = await add_record(sessions, scope, 2, author=scope.recorder)
            other = await add_record(sessions, scope, 7, author=scope.owner, number=2)
            credentials = await grant(http, scope, user=scope.recorder)
            token = credentials["token"]
            response = await call(
                http, token, "list_records", protocol_id=str(scope.protocol.id)
            )
            assert [row["id"] for row in response.json()["items"]] == [str(own.id)]
            denied = await call(
                http,
                token,
                "preview_revision",
                protocol_id=str(scope.protocol.id),
                record_id=str(other.id),
                expected_version=1,
                changes={"value": 3},
                reason="Not mine",
                request_key=uuid4().hex,
            )
            assert denied.status_code == 403
            key = uuid4().hex
            args = {
                "protocol_id": str(scope.protocol.id),
                "record_id": str(own.id),
                "expected_version": 1,
                "changes": {"value": 3},
                "reason": "Verified correction",
                "request_key": key,
            }
            previewed = await call(http, token, "preview_revision", **args)
            assert previewed.status_code == 200, previewed.text
            op = previewed.json()
            # Even the Lab owner cannot approve another user's delegated operation.
            assert (
                await http.get(
                    f"/external-access/operations/{op['id']}",
                    headers=browser(scope.owner),
                )
            ).status_code == 404
            # A retained earlier revision must not resurrect a deleted latest Record.
            await add_record(
                sessions, scope, 3, author=scope.recorder,
                record_id=own.id, revision=2, number=own.number,
            )
            async with sessions() as db:
                await db.execute(
                    update(Record)
                    .where(Record.id == own.id, Record.version == 2)
                    .values(deleted_at=service.now().replace(tzinfo=None))
                )
                await db.commit()
            rows = await call(
                http, token, "list_records", protocol_id=str(scope.protocol.id)
            )
            assert rows.json()["items"] == []
            assert (
                await call(http, token, "preview_revision", **args)
            ).status_code == 404
            assert (
                await call(http, token, "operation_status", operation_id=op["id"])
            ).status_code == 404

    asyncio.run(scenario())


def test_rate_limit_never_prevents_browser_revocation():
    async def scenario():
        async with database() as sessions, client(sessions) as http:
            scope = await seed(sessions)
            credentials = await grant(http, scope)
            async with sessions() as db:
                for _ in range(120):
                    service.audit(
                        db,
                        scope.owner.id,
                        "tool.access_context",
                        UUID(credentials["grant"]["id"]),
                    )
                await db.commit()
            response = await call(http, credentials["token"], "access_context")
            assert response.status_code == 429
            revoked = await http.delete(
                f"/external-access/grants/{credentials['grant']['id']}",
                headers=browser(scope.owner),
            )
            assert revoked.status_code == 200

    asyncio.run(scenario())


def test_dashboard_expiry_cleanup_only_touches_own_pending_operations():
    async def scenario():
        async with database() as sessions, client(sessions) as http:
            scope, other = await seed(sessions), await seed(sessions)
            first = (
                await preview(http, (await grant(http, scope))["token"], scope)
            ).json()
            second = (
                await preview(http, (await grant(http, other))["token"], other)
            ).json()
            async with sessions() as db:
                await db.execute(
                    update(ExternalOperation)
                    .where(
                        ExternalOperation.id.in_(
                            [UUID(first["id"]), UUID(second["id"])]
                        )
                    )
                    .values(expires_at=service.now() - timedelta(seconds=1))
                )
                await db.commit()
            dashboard = await http.get(
                "/external-access/dashboard", headers=browser(scope.owner)
            )
            assert dashboard.status_code == 200
            assert [entry["id"] for entry in dashboard.json()["operations"]] == [
                first["id"]
            ]
            async with sessions() as db:
                own = await db.get(ExternalOperation, UUID(first["id"]))
                foreign = await db.get(ExternalOperation, UUID(second["id"]))
                assert own.state == "expired" and own.payload == {}
                assert foreign.state == "pending" and foreign.payload["csv"] == CSV

    asyncio.run(scenario())
