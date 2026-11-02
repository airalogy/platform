"""Deterministic delegation boundary shared by HTTP and MCP transports.

Lock order: user call gate -> shared Lab policy -> grant -> operation -> Protocol -> Record. The caller
commits once, together with the mutation result and its audit receipt.
"""

import csv
import hashlib
import io
import json
import math
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

from app.config import config
from app.models.external_access import (
    ExternalAccessPolicy,
    ExternalAudit,
    ExternalGrant,
    ExternalOperation,
)
from app.models.lab import Lab, LabRole, LabUser
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.user import User
from app.routers.permission import check_user_permission as platform_permission
from app.services.account_security import get_auth_version
from app.services.record_imports import import_fields, template_csv

SCOPES = {"protocols:read", "records:read", "records:import", "records:revise"}
MAX_CSV_BYTES = 1024 * 1024
OPERATION_TTL = timedelta(minutes=15)


def now():
    return datetime.now(UTC)


def fail(code, status=403):
    raise HTTPException(status_code=status, detail={"code": code})


async def check_user_permission(*args, **kwargs):
    try:
        return await platform_permission(*args, **kwargs)
    except HTTPException as error:
        if error.status_code in (400, 403):
            fail("external_access_forbidden")
        raise


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class GrantInput(StrictModel):
    project_id: UUID
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] = Field(min_length=1, max_length=4)
    expires_in_days: int = Field(default=7, ge=1, le=90)


class PolicyInput(StrictModel):
    enabled: bool
    blocked_fields: list[str] = Field(default_factory=list, max_length=500)
    expected_revision: int = Field(ge=0)


class ToolInput(StrictModel):
    protocol_id: UUID | None = None
    record_id: UUID | None = None
    expected_version: int | None = Field(default=None, ge=1)
    changes: dict | None = None
    reason: str | None = Field(default=None, max_length=2000)
    csv: str | None = Field(default=None, max_length=MAX_CSV_BYTES)
    request_key: str | None = Field(
        default=None, min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"
    )
    operation_id: UUID | None = None
    offset: int = Field(default=0, ge=0, le=100000)


@dataclass
class Access:
    grant: ExternalGrant
    user: User
    project: Project
    policy: ExternalAccessPolicy


def audit(db, user_id, event, grant_id=None, **detail):
    # Never include payloads, credentials, or model-controlled exception text.
    db.add(
        ExternalAudit(
            user_id=user_id,
            event=event,
            grant_id=grant_id,
            detail=detail,
            created_at=now(),
        )
    )


async def expire_operations(db, grant_id=None, *, user_id=None):
    statement = update(ExternalOperation).where(
        ExternalOperation.expires_at <= now(),
        ExternalOperation.state.in_(["pending", "approved"]),
    )
    if grant_id is not None:
        statement = statement.where(ExternalOperation.grant_id == grant_id)
    elif user_id is not None:
        statement = statement.where(
            ExternalOperation.grant_id.in_(
                select(ExternalGrant.id).where(ExternalGrant.user_id == user_id)
            )
        )
    else:
        raise ValueError("Expired confirmation cleanup requires an authorized owner")
    await db.execute(statement.values(state="expired", payload={}))


async def lab_member(db, lab_id, user_id, manager=False):
    member = await db.scalar(
        select(LabUser).where(LabUser.lab_id == lab_id, LabUser.user_id == user_id)
    )
    if not member or (manager and member.role not in (LabRole.OWNER, LabRole.MANAGER)):
        fail("external_access_forbidden")
    return member


async def policy_for(db, lab_id, lock=False, shared=False):
    query = select(ExternalAccessPolicy).where(ExternalAccessPolicy.lab_id == lab_id)
    if lock:
        query = query.with_for_update(read=shared)
    return await db.scalar(query)


async def lock_user_calls(db, user_id):
    # Serialize quotas/idempotency for one actor, without blocking another Lab member.
    key = int.from_bytes(
        hashlib.sha256(f"external-access:{user_id}".encode()).digest()[:8],
        "big",
        signed=True,
    )
    await db.execute(select(func.pg_advisory_xact_lock(key)))


async def change_policy(db, user, lab_id, params):
    await lab_member(db, lab_id, user.id, manager=True)
    await db.execute(
        insert(ExternalAccessPolicy)
        .values(lab_id=lab_id, enabled=False, blocked_fields=[], revision=0)
        .on_conflict_do_nothing()
    )
    policy = await policy_for(db, lab_id, lock=True)
    if policy.revision != params.expected_revision:
        fail("policy_changed", 409)
    fields = sorted(
        {value.strip().removeprefix("var.") for value in params.blocked_fields}
    )
    if any(not field or len(field) > 200 for field in fields):
        fail("invalid_field_name", 422)
    policy.enabled, policy.blocked_fields = params.enabled, fields
    policy.revision += 1
    audit(
        db,
        user.id,
        "policy.updated",
        lab_id=str(lab_id),
        revision=policy.revision,
        enabled=policy.enabled,
    )
    return {
        "enabled": policy.enabled,
        "blocked_fields": fields,
        "revision": policy.revision,
    }


async def create_grant(db, user, params):
    if not params.name.strip():
        fail("grant_name_required", 422)
    if not set(params.scopes) <= SCOPES or "protocols:read" not in params.scopes:
        fail("invalid_scopes", 422)
    project = await db.scalar(
        select(Project).where(
            Project.id == params.project_id, Project.deleted_at.is_(None)
        )
    )
    if not project:
        fail("project_not_found", 404)
    await lock_user_calls(db, user.id)
    policy = await policy_for(db, project.lab_id, lock=True, shared=True)
    await lab_member(db, project.lab_id, user.id)
    if not policy or not policy.enabled:
        fail("lab_external_access_disabled")
    await check_user_permission(db, project, user, "read_project")
    count = await db.scalar(
        select(func.count())
        .select_from(ExternalGrant)
        .where(
            ExternalGrant.user_id == user.id,
            ExternalGrant.revoked_at.is_(None),
            ExternalGrant.expires_at > now(),
        )
    )
    if count >= 50:
        fail("grant_limit", 429)
    token = "apl_" + secrets.token_urlsafe(36)
    grant = ExternalGrant(
        user_id=user.id,
        project_id=project.id,
        name=params.name.strip(),
        scopes=sorted(set(params.scopes)),
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        token_prefix=token[:12],
        auth_version=await get_auth_version(db, user.id),
        created_at=now(),
        expires_at=now() + timedelta(days=params.expires_in_days),
    )
    db.add(grant)
    await db.flush()
    audit(
        db,
        user.id,
        "grant.created",
        grant.id,
        project_id=str(project.id),
        scopes=grant.scopes,
    )
    return {"grant": grant.as_dict(), "token": token}


async def authorize(db, token=None, *, grant_id=None, owner_id=None):
    query = select(ExternalGrant)
    if token is not None:
        if not token.startswith("apl_") or len(token) > 100:
            fail("invalid_external_token", 401)
        query = query.where(
            ExternalGrant.token_hash == hashlib.sha256(token.encode()).hexdigest()
        )
    else:
        query = query.where(
            ExternalGrant.id == grant_id, ExternalGrant.user_id == owner_id
        )
    grant = await db.scalar(query)
    if not grant:
        fail("invalid_external_token", 401)
    project = await db.scalar(
        select(Project).where(
            Project.id == grant.project_id, Project.deleted_at.is_(None)
        )
    )
    if not project:
        fail("external_access_forbidden")
    await lock_user_calls(db, grant.user_id)
    policy = await policy_for(db, project.lab_id, lock=True, shared=True)
    # Refresh after acquiring the policy lock; revocation may have occurred while waiting.
    grant = await db.scalar(
        query.with_for_update().execution_options(populate_existing=True)
    )
    if not grant or grant.revoked_at or grant.expires_at <= now():
        fail("expired_or_revoked_grant", 401)
    if not policy or not policy.enabled:
        fail("lab_external_access_disabled")
    user = await db.get(User, grant.user_id)
    if not user or grant.auth_version != await get_auth_version(db, user.id):
        fail("invalid_external_token", 401)
    await lab_member(db, project.lab_id, user.id)
    await check_user_permission(db, project, user, "read_project")
    recent = await db.scalar(
        select(func.count())
        .select_from(ExternalAudit)
        .where(
            ExternalAudit.user_id == user.id,
            ExternalAudit.created_at > now() - timedelta(minutes=1),
            ExternalAudit.event.like("tool.%"),
        )
    )
    if recent >= 120:
        fail("external_rate_limit", 429)
    return Access(grant, user, project, policy)


def scope(access, required):
    if required not in access.grant.scopes:
        fail("insufficient_scope")


async def protocol_context(
    db, access, protocol_id, action="read_protocol", version=None
):
    if not protocol_id:
        fail("protocol_id_required", 422)
    protocol = await db.scalar(
        select(Protocol)
        .where(
            Protocol.id == protocol_id,
            Protocol.project_id == access.project.id,
            Protocol.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if not protocol:
        fail("protocol_not_found", 404)
    await check_user_permission(
        db, access.project, access.user, action, protocol=protocol
    )
    pv = await db.scalar(
        select(ProtocolVersion).where(
            ProtocolVersion.protocol_id == protocol.id,
            ProtocolVersion.version == (version or protocol.latest_version),
        )
    )
    if not pv:
        fail("protocol_version_not_found", 404)
    return protocol, pv


def primitive_schema(schema):
    # Pydantic spells Optional[T] as anyOf(T, null); that is still a scalar.
    if isinstance(schema, dict) and isinstance(schema.get("anyOf"), list):
        variants = schema["anyOf"]
        if len(variants) == 2 and {"type": "null"} in variants:
            other = next((item for item in variants if item != {"type": "null"}), {})
            if isinstance(other, dict) and isinstance(other.get("type"), str):
                nullable = {**other, "type": [other["type"], "null"]}
                if "const" in nullable:
                    nullable["enum"] = [nullable.pop("const"), None]
                elif isinstance(nullable.get("enum"), list):
                    nullable["enum"] = [*nullable["enum"], None]
                return {
                    **nullable,
                    **{key: value for key, value in schema.items() if key != "anyOf"},
                }
    return schema


def scalar_field(schema):
    """Complex/file types remain on the normal Platform UI, not this data channel."""
    if not isinstance(schema, dict):
        return False
    schema = primitive_schema(schema)
    text = json.dumps(schema).lower()
    if any(
        marker in text
        for marker in ('"$ref"', "airalogy_type", "contentmedia", '"object"', '"array"')
    ):
        return False
    if schema.get("format") not in (
        None,
        "date",
        "date-time",
        "time",
        "duration",
        "uuid",
        "email",
    ):
        return False
    types = schema.get("type")
    return (
        types in ("string", "number", "integer", "boolean", "null")
        if isinstance(types, str)
        else (
            isinstance(types, list)
            and bool(types)
            and all(isinstance(item, str) for item in types)
            and set(types) <= {"string", "number", "integer", "boolean", "null"}
        )
    )


def external_fields(access, version):
    return {
        key: primitive_schema(spec)
        for key, spec in version.json_schema.get("vars", {})
        .get("properties", {})
        .items()
        if key not in access.policy.blocked_fields and scalar_field(spec)
    }


def safe_value(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str) and not any(
        marker in value.lower()
        for marker in (
            "http://",
            "https://",
            "airalogy.id.file.",
            "/attachments/",
            "/download/",
            "/airalogy_files/",
        )
    ):
        return value
    return None


def record_view(access, version, record):
    fields = external_fields(access, version)
    variables = (record.data or {}).get("var", {})
    return {
        "id": str(record.id),
        "version": record.version,
        "protocol_version": record.protocol_version,
        "var": {
            key: value
            for key, value in variables.items()
            if key in fields and safe_value(value) == value
        },
        "withheld_fields": [
            key
            for key, value in variables.items()
            if key in fields and safe_value(value) != value
        ],
    }


def validation_errors(errors, fields):
    """Custom validators may echo secrets or inputs. Expose bounded locations/codes only."""
    allowed = {
        "required",
        "missing_required",
        "unknown_field",
        "duplicate_header",
        "duplicate_target",
        "blank_header",
        "row_width",
        "invalid_csv",
        "empty_file",
        "spreadsheet_error",
        "too_many_rows",
        "invalid_encoding",
        "invalid_type",
        "out_of_range",
        "invalid_value",
        "integer",
        "boolean",
        "number",
        "string",
        "pattern",
        "range",
        "validation",
    }
    result = []
    for error in errors[:100]:
        if not isinstance(error, dict):
            continue
        loc = error.get("loc", [])
        column = error.get("column") or (
            loc[0] if isinstance(loc, (list, tuple)) and loc else None
        )
        column = column.removeprefix("var.") if isinstance(column, str) else None
        item = {
            "column": column if column in fields else None,
            "code": error.get("code")
            if error.get("code") in allowed
            else "invalid_value",
            "message": "Check this value against the Protocol field type, required status and limits; do not guess a replacement.",
        }
        for key in ("row_number", "line_number"):
            value = error.get(key)
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and 0 < value <= 1000000
            ):
                item[key] = value
        result.append(item)
    return result


def require_writable_schema(access, version):
    properties = version.json_schema.get("vars", {}).get("properties", {})
    if set(properties) != set(external_fields(access, version)):
        # No validation error, report or computed value may disclose a hidden field.
        fail("restricted_or_complex_protocol_use_platform", 422)


async def read_record(db, access, protocol, record_id):
    record = await db.scalar(
        select(Record)
        .where(Record.id == record_id, Record.protocol_id == protocol.id)
        .order_by(Record.version.desc())
        .limit(1)
    )
    if not record or record.deleted_at is not None:
        fail("record_not_found", 404)
    await check_user_permission(
        db, access.project, access.user, "read_record", protocol=protocol, record=record
    )
    return record


def operation_view(op):
    state = (
        "expired"
        if op.state in ("pending", "approved") and op.expires_at <= now()
        else op.state
    )
    return {
        "id": str(op.id),
        "kind": op.kind,
        "protocol_id": str(op.protocol_id),
        "digest": op.digest,
        "state": state,
        "summary": op.summary,
        "result": op.result,
        "expires_at": op.expires_at.isoformat(),
    }


async def import_preview(db, access, protocol_id, text, preview=True):
    from app.routers.records import import_records_transaction

    if text is None or len(text.encode()) > MAX_CSV_BYTES:
        fail("csv_required_or_too_large", 422)
    # External import is a canonical variable table, not a metadata/file backdoor.
    try:
        headers = next(csv.reader(io.StringIO(text), strict=True), [])
    except csv.Error:
        fail("invalid_csv", 422)
    if not headers or any(
        not name.removeprefix("\ufeff").startswith("var.") for name in headers
    ):
        fail("use_canonical_csv_template", 422)
    return await import_records_transaction(
        protocol_id,
        db,
        access.user,
        BackgroundTasks(),
        UploadFile(filename="records.csv", file=io.BytesIO(text.encode())),
        input_format="csv",
        include_template_defaults=False,
        preview=preview,
        commit=False,
        executor_credentials=False,
    )


async def preview_operation(db, access, args, kind):
    scope(access, "records:import" if kind == "import" else "records:revise")
    if not args.request_key:
        fail("request_key_required", 422)
    protocol, version = await protocol_context(
        db, access, args.protocol_id, "create_record"
    )
    payload = args.model_dump(mode="json", exclude_none=True)
    fingerprint = digest({"kind": kind, "payload": payload})
    existing = await db.scalar(
        select(ExternalOperation).where(
            ExternalOperation.grant_id == access.grant.id,
            ExternalOperation.request_key == args.request_key,
        )
    )
    if existing:
        if existing.digest != fingerprint:
            fail("idempotency_key_conflict", 409)
        if existing.policy_revision != access.policy.revision:
            fail("policy_changed_preview_again", 409)
        if kind == "revision":
            scope(access, "records:read")
            record = await read_record(db, access, protocol, args.record_id)
            if record.user_id != access.user.id:
                fail("record_revision_forbidden")
        return operation_view(existing)
    await expire_operations(db, access.grant.id)
    count = await db.scalar(
        select(func.count())
        .select_from(ExternalOperation)
        .where(
            ExternalOperation.grant_id == access.grant.id,
            ExternalOperation.state.in_(["pending", "approved"]),
        )
    )
    if count >= 10:
        fail("pending_operation_limit", 429)
    if kind == "import":
        require_writable_schema(access, version)
        result = await import_preview(db, access, protocol.id, args.csv)
        if result.get("errors"):
            return {
                "state": "invalid",
                "errors": validation_errors(
                    result["errors"], external_fields(access, version)
                ),
                "created_records": 0,
            }
        summary = {
            "protocol_name": protocol.name,
            "protocol_version": version.version,
            "row_count": result["row_count"],
            "project_name": access.project.name,
        }
    else:
        scope(access, "records:read")
        record = await read_record(db, access, protocol, args.record_id)
        if record.user_id != access.user.id:
            fail("record_revision_forbidden")
        _, version = await protocol_context(
            db, access, protocol.id, "create_record", record.protocol_version
        )
        require_writable_schema(access, version)
        if args.expected_version != record.version:
            fail("record_changed", 409)
        if not args.reason or not args.reason.strip() or not args.changes:
            fail("revision_reason_and_changes_required", 422)
        if not set(args.changes) <= set(external_fields(access, version)):
            fail("unknown_or_restricted_field", 422)
        values = {**record.data.get("var", {}), **args.changes}
        if any(
            safe_value(value) != value
            for value in [*record.data.get("var", {}).values(), *args.changes.values()]
        ):
            fail("restricted_or_complex_record_use_platform", 422)
        await validate_revision(version, values)
        summary = {
            "project_name": access.project.name,
            "protocol_name": protocol.name,
            "record_id": str(record.id),
            "expected_version": record.version,
            "changes": {
                key: {"before": record.data.get("var", {}).get(key), "after": value}
                for key, value in args.changes.items()
            },
            "reason": args.reason,
        }
    op = ExternalOperation(
        grant_id=access.grant.id,
        request_key=args.request_key,
        kind=kind,
        protocol_id=protocol.id,
        protocol_version_id=version.id,
        policy_revision=access.policy.revision,
        digest=fingerprint,
        payload=payload,
        summary=summary,
        created_at=now(),
        expires_at=now() + OPERATION_TTL,
    )
    db.add(op)
    await db.flush()
    audit(
        db,
        access.user.id,
        "operation.previewed",
        access.grant.id,
        operation_id=str(op.id),
        digest=op.digest,
    )
    return {
        **operation_view(op),
        "confirmation_url": f"{config.SITE_URL.rstrip('/')}/users/{access.user.username}/settings#external-access",
        "instruction": "The user must review and approve in Platform. Agent tokens cannot approve operations.",
    }


async def validate_revision(version, values):
    from app.libs.protocol_agent import prepare_protocol_package, protocol_exec

    await prepare_protocol_package(version)
    result = await protocol_exec("var_validate", version.package_name, values)
    if not result.get("success") or result.get("data", {}).get("errors"):
        raise HTTPException(
            422,
            detail={
                "code": "invalid_record",
                "errors": validation_errors(
                    result.get("data", {}).get("errors", []),
                    version.json_schema.get("vars", {}).get("properties", {}),
                ),
            },
        )


async def execute_operation(db, access, op):
    required = "records:import" if op.kind == "import" else "records:revise"
    scope(access, required)
    if op.state == "succeeded":
        return operation_view(op)
    if op.state != "approved" or op.expires_at <= now():
        fail("operation_not_approved_or_expired", 409)
    if access.policy.revision != op.policy_revision:
        fail("policy_changed_preview_again", 409)
    args = ToolInput.model_validate(op.payload)
    protocol, version = await protocol_context(
        db, access, op.protocol_id, "create_record"
    )
    if op.kind == "revision":
        scope(access, "records:read")
        record = await read_record(db, access, protocol, args.record_id)
        _, version = await protocol_context(
            db, access, protocol.id, "create_record", record.protocol_version
        )
    if version.id != op.protocol_version_id:
        fail("protocol_changed_preview_again", 409)
    require_writable_schema(access, version)
    if op.kind == "import":
        result = await import_preview(db, access, protocol.id, args.csv, preview=False)
        ids = result["record_ids"]
        record_version = 1
    else:
        from app.routers.records import RecordCreateParams, revise_record_transaction

        if record.version != args.expected_version:
            fail("record_changed", 409)
        params = RecordCreateParams(
            **{
                **record.data,
                "var": {**record.data.get("var", {}), **args.changes},
                "report": "",
                "revision_reason": args.reason,
                "expected_version": args.expected_version,
            }
        )
        revised = await revise_record_transaction(
            protocol.id, record.id, params, access.user, db, commit=False
        )
        ids, record_version = [str(revised.id)], revised.version
        result = {"record_id": str(revised.id), "version": revised.version}
    lab = await db.get(Lab, access.project.lab_id)
    result["links"] = [
        f"/labs/{lab.uid}/projects/{access.project.uid}/protocols/{protocol.uid}/v{version.version}/record/{rid}/v{record_version}"
        for rid in ids
    ]
    op.state, op.result, op.payload = "succeeded", result, {}
    audit(
        db,
        access.user.id,
        "operation.executed",
        access.grant.id,
        operation_id=str(op.id),
        result=result,
    )
    return operation_view(op)


async def tool_call(db, access, name, args):
    scope(access, "protocols:read")
    await expire_operations(db, access.grant.id)
    if name == "access_context":
        return {
            "project": {"id": str(access.project.id), "name": access.project.name},
            "scopes": access.grant.scopes,
            "expires_at": access.grant.expires_at.isoformat(),
            "blocked_fields": access.policy.blocked_fields,
            "attachments": "not_available",
        }
    if name == "list_protocols":
        protocols = (
            await db.scalars(
                select(Protocol)
                .where(
                    Protocol.project_id == access.project.id,
                    Protocol.deleted_at.is_(None),
                )
                .order_by(Protocol.id)
                .offset(args.offset)
                .limit(50)
            )
        ).all()
        items = []
        for protocol in protocols:
            try:
                await check_user_permission(
                    db, access.project, access.user, "read_protocol", protocol=protocol
                )
            except HTTPException:
                continue
            items.append(
                {
                    "id": str(protocol.id),
                    "name": protocol.name,
                    "version": protocol.latest_version,
                }
            )
        return {
            "items": items,
            "next_offset": args.offset + 50 if len(protocols) == 50 else None,
        }
    if name in ("get_protocol", "list_records"):
        protocol, version = await protocol_context(db, access, args.protocol_id)
        if name == "get_protocol":
            fields = external_fields(access, version)
            # Only structural field metadata; no defaults, examples, AIMD, files or secrets.
            metadata = [
                {k: v for k, v in field.items() if k in ("id", "title", "required")}
                for field in import_fields(version.json_schema)
                if field["id"] in fields
            ]
            schema = {
                "vars": {
                    "properties": {
                        key: {
                            k: v
                            for k, v in value.items()
                            if k
                            in (
                                "type",
                                "format",
                                "minimum",
                                "maximum",
                                "exclusiveMinimum",
                                "exclusiveMaximum",
                                "multipleOf",
                                "enum",
                                "const",
                                "pattern",
                                "minLength",
                                "maxLength",
                            )
                        }
                        for key, value in fields.items()
                    },
                    "required": [
                        key
                        for key in version.json_schema.get("vars", {}).get(
                            "required", []
                        )
                        if key in fields
                    ],
                }
            }
            return {
                "id": str(protocol.id),
                "version": version.version,
                "name": protocol.name,
                "fields": metadata,
                "schema": schema,
                "csv_template": template_csv(schema),
            }
        scope(access, "records:read")
        # Resolve the current version before applying visibility or pagination.
        latest = aliased(
            Record,
            select(Record)
            .where(Record.protocol_id == protocol.id)
            .distinct(Record.id)
            .order_by(Record.id, Record.version.desc())
            .subquery(),
        )
        rows = (
            await db.scalars(
                select(latest)
                .where(latest.deleted_at.is_(None))
                .order_by(latest.id)
                .offset(args.offset)
                .limit(50)
            )
        ).all()
        items = []
        for record in rows:
            try:
                await check_user_permission(
                    db,
                    access.project,
                    access.user,
                    "read_record",
                    protocol=protocol,
                    record=record,
                )
            except HTTPException:
                continue
            pv = await db.scalar(
                select(ProtocolVersion).where(
                    ProtocolVersion.protocol_id == protocol.id,
                    ProtocolVersion.version == record.protocol_version,
                )
            )
            if pv:
                items.append(record_view(access, pv, record))
        return {
            "items": items,
            "next_offset": args.offset + 50 if len(rows) == 50 else None,
        }
    if name in ("preview_import", "preview_revision"):
        return await preview_operation(
            db, access, args, "import" if name == "preview_import" else "revision"
        )
    if name in ("operation_status", "execute_operation"):
        op = await db.scalar(
            select(ExternalOperation)
            .where(
                ExternalOperation.id == args.operation_id,
                ExternalOperation.grant_id == access.grant.id,
            )
            .with_for_update()
        )
        if not op:
            fail("operation_not_found", 404)
        await protocol_context(db, access, op.protocol_id)
        if op.kind == "revision":
            scope(access, "records:read")
            protocol, _ = await protocol_context(db, access, op.protocol_id)
            record = await read_record(
                db, access, protocol, UUID(op.summary["record_id"])
            )
            if record.user_id != access.user.id:
                fail("record_revision_forbidden")
        if op.policy_revision != access.policy.revision:
            fail("policy_changed_preview_again", 409)
        return (
            await execute_operation(db, access, op)
            if name == "execute_operation"
            else operation_view(op)
        )
    fail("unknown_tool", 404)
