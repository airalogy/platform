"""Protocol compatibility, migration, projection, and durable-job services."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from collections import deque
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from airalogy.migrations import (
    apply_declarative_migration,
    migration_rule_hash,
    validate_migration_manifest,
)
from airalogy.record.hash import get_data_sha1
from airalogy.schema_compatibility import compare_json_schemas
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.libs.protocol_agent import prepare_protocol_package, protocol_exec
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.resource import (
    RecordProjection,
    SchemaMigrationRun,
)


class SchemaGovernanceError(ValueError):
    pass


GovernanceError = SchemaGovernanceError


def _semver(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if len(parts) != 3:
        raise SchemaGovernanceError("Protocol version must use major.minor.patch")
    try:
        result = tuple(int(part) for part in parts)
    except ValueError as error:
        raise SchemaGovernanceError(
            "Protocol version must use major.minor.patch"
        ) from error
    if any(part < 0 for part in result):
        raise SchemaGovernanceError(
            "Protocol version components must be non-negative"
        )
    return result  # type: ignore[return-value]


def actual_semver_bump(previous: str, current: str) -> Literal["patch", "minor", "major"]:
    before = _semver(previous)
    after = _semver(current)
    if after <= before:
        raise SchemaGovernanceError(
            "Protocol version must be greater than the current version"
        )
    if after[0] != before[0]:
        return "major"
    if after[1] != before[1]:
        return "minor"
    return "patch"


def build_compatibility_report(
    previous_schema: dict[str, Any],
    current_schema: dict[str, Any],
    *,
    previous_version: str,
    current_version: str,
) -> dict[str, Any]:
    report = compare_json_schemas(previous_schema, current_schema).model_dump()
    actual_bump = actual_semver_bump(previous_version, current_version)
    rank = {"patch": 0, "minor": 1, "major": 2}
    report["actual_bump"] = actual_bump
    report["semver_valid"] = (
        rank[actual_bump] >= rank[report["recommended_bump"]]
    )
    if not report["semver_valid"]:
        raise SchemaGovernanceError(
            f'Schema changes require a {report["recommended_bump"]} version, '
            f"but {previous_version} -> {current_version} is {actual_bump}"
        )
    return report


def load_package_migration_manifests(package_dir: Path) -> list[dict[str, Any]]:
    migrations_dir = package_dir / "migrations"
    if not migrations_dir.is_dir():
        return []
    manifests: list[dict[str, Any]] = []
    edges: set[tuple[str, str]] = set()
    for path in sorted(migrations_dir.rglob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SchemaGovernanceError(
                f"Invalid migration manifest {path.name}: {error}"
            ) from error
        if not isinstance(value, dict):
            raise SchemaGovernanceError(
                f"Migration manifest {path.name} must be an object"
            )
        issues = validate_migration_manifest(value)
        if issues:
            raise SchemaGovernanceError(
                f"Invalid migration manifest {path.name}: "
                + "; ".join(
                    f"{issue.path}: {issue.message}" for issue in issues
                )
            )
        edge = (str(value["from"]), str(value["to"]))
        if edge in edges:
            raise SchemaGovernanceError(
                f"Duplicate migration edge {edge[0]} -> {edge[1]}"
            )
        edges.add(edge)
        manifests.append(value)
    return manifests


def find_migration_path(
    manifests: list[dict[str, Any]],
    source_version: str,
    target_version: str,
) -> list[dict[str, Any]]:
    """Return the shortest deterministic directed migration path."""
    if source_version == target_version:
        return []
    adjacency: dict[str, list[dict[str, Any]]] = {}
    for manifest in manifests:
        source = str(manifest.get("from") or "")
        target = str(manifest.get("to") or "")
        if source and target:
            adjacency.setdefault(source, []).append(manifest)
    for edges in adjacency.values():
        edges.sort(key=lambda item: str(item["to"]))

    queue: deque[tuple[str, list[dict[str, Any]]]] = deque(
        [(source_version, [])]
    )
    visited = {source_version}
    while queue:
        version, path = queue.popleft()
        for manifest in adjacency.get(version, []):
            next_version = str(manifest["to"])
            next_path = [*path, manifest]
            if next_version == target_version:
                return next_path
            if next_version not in visited:
                visited.add(next_version)
                queue.append((next_version, next_path))
    raise SchemaGovernanceError(
        f"No migration path from {source_version} to {target_version}"
    )


def migration_path_hash(manifests: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        json.dumps(
            manifests,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _schema_property_paths(schema: Any, prefix: str = "") -> set[str]:
    if not isinstance(schema, dict):
        return set()
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return set()
    paths: set[str] = set()
    for name, child in properties.items():
        path = f"{prefix}.{name}" if prefix else name
        paths.add(path)
        paths.update(_schema_property_paths(child, path))
    return paths


def projection_not_collected(
    source_schema: dict[str, Any],
    target_schema: dict[str, Any],
) -> list[str]:
    return sorted(
        _schema_property_paths(target_schema)
        - _schema_property_paths(source_schema)
    )


def preview_declarative_migration(
    data: dict[str, Any],
    manifest: dict[str, Any],
    *,
    source_schema: dict[str, Any],
    target_schema: dict[str, Any],
) -> dict[str, Any]:
    result = apply_declarative_migration(data, manifest)
    return {
        "data": result.data,
        "status": result.status,
        "issues": [
            {"path": issue.path, "message": issue.message}
            for issue in result.issues
        ],
        "rule_hash": result.rule_hash,
        "not_collected": projection_not_collected(source_schema, target_schema),
        "requires_sandbox": isinstance(manifest.get("transform"), dict),
    }


async def preview_migration_path(
    data: dict[str, Any],
    manifests: list[dict[str, Any]],
    *,
    source_version: ProtocolVersion,
    target_version: ProtocolVersion,
    versions_by_name: dict[str, ProtocolVersion],
) -> dict[str, Any]:
    current_data = data
    issues: list[dict[str, str]] = []
    status = "completed"
    step_results: list[dict[str, Any]] = []
    for manifest in manifests:
        step_target = versions_by_name.get(str(manifest["to"]))
        if step_target is None:
            raise SchemaGovernanceError(
                f'Migration target {manifest["to"]} is not a published Protocol version'
            )
        if manifest.get("transform"):
            await prepare_protocol_package(step_target)
            execution = await protocol_exec(
                "schema_migrate",
                step_target.package_name,
                {"data": current_data, "manifest": manifest},
            )
            if not execution.get("success"):
                raise SchemaGovernanceError(
                    str(execution.get("message") or "migration failed")
                )
            step = execution["data"]
        else:
            step_source = versions_by_name.get(str(manifest["from"]))
            if step_source is None:
                raise SchemaGovernanceError(
                    f'Migration source {manifest["from"]} is not published'
                )
            step = preview_declarative_migration(
                current_data,
                manifest,
                source_schema=step_source.json_schema,
                target_schema=step_target.json_schema,
            )
        current_data = step["data"]
        step_issues = step.get("issues") or []
        issues.extend(
            {
                **item,
                "migration": f'{manifest["from"]}->{manifest["to"]}',
            }
            for item in step_issues
        )
        if step.get("status") == "needs_review":
            status = "needs_review"
        elif step.get("status") not in {"completed", "needs_review"}:
            status = "failed"
        step_results.append(
            {
                "from": manifest["from"],
                "to": manifest["to"],
                "status": step.get("status", "completed"),
                "rule_hash": migration_rule_hash(manifest),
            }
        )
    return {
        "data": current_data,
        "status": status,
        "issues": issues,
        "rule_hash": migration_path_hash(manifests),
        "not_collected": projection_not_collected(
            source_version.json_schema, target_version.json_schema
        ),
        "requires_sandbox": False,
        "steps": step_results,
    }


async def run_schema_migration(
    db_session: AsyncSession,
    *,
    record: Record,
    target_version: ProtocolVersion,
    source_version: ProtocolVersion,
    manifests: list[dict[str, Any]],
    versions_by_name: dict[str, ProtocolVersion],
    user_id: UUID,
    reason: str,
    idempotency_key: str,
) -> tuple[SchemaMigrationRun, Record]:
    existing = (
        await db_session.execute(
            select(SchemaMigrationRun).where(
                SchemaMigrationRun.idempotency_key == idempotency_key
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        migrated = (
            await db_session.execute(
                select(Record).where(Record.migration_run_id == existing.id)
            )
        ).scalar_one_or_none()
        if migrated is None:
            raise SchemaGovernanceError(
                "migration run exists without a Record revision"
            )
        return existing, migrated

    rule_hash = migration_path_hash(manifests)
    manifest_plan = {
        "version": "airalogy.migration-plan.v1",
        "from": source_version.version,
        "to": target_version.version,
        "steps": manifests,
    }
    migration_run = SchemaMigrationRun(
        protocol_id=record.protocol_id,
        source_version=source_version.version,
        target_version=target_version.version,
        manifest=manifest_plan,
        rule_hash=rule_hash,
        code_hash=(
            hashlib.sha256(
                "|".join(
                    str(item.get("transform", {}).get("code_hash") or "")
                    for item in manifests
                    if isinstance(item.get("transform"), dict)
                ).encode()
            ).hexdigest()
            if any(isinstance(item.get("transform"), dict) for item in manifests)
            else None
        ),
        status="running",
        issues=[],
        idempotency_key=idempotency_key,
        created_by_user_id=user_id,
    )
    db_session.add(migration_run)
    await db_session.flush()

    migrated = await preview_migration_path(
        record.data,
        manifests,
        source_version=source_version,
        target_version=target_version,
        versions_by_name=versions_by_name,
    )

    if migrated["status"] not in {"completed", "needs_review"}:
        migration_run.status = "failed"
        migration_run.issues = migrated.get("issues") or []
        raise SchemaGovernanceError(
            "migration preview contains blocking errors"
        )

    next_version = (
        await db_session.scalar(
            select(Record.version)
            .where(Record.id == record.id)
            .order_by(Record.version.desc())
            .limit(1)
            .with_for_update()
        )
        or record.version
    ) + 1
    migrated_data = migrated["data"]
    migrated_record = Record(
        id=record.id,
        version=next_version,
        protocol_id=record.protocol_id,
        protocol_version=target_version.version,
        user_id=user_id,
        data=migrated_data,
        report=record.report,
        number=record.number,
        hash=get_data_sha1(migrated_data),
        revision_kind="schema_migration",
        revision_reason=reason,
        source_protocol_version=record.protocol_version,
        migration_run_id=migration_run.id,
    )
    db_session.add(migrated_record)
    migration_run.status = (
        "needs_review" if migrated["status"] == "needs_review" else "completed"
    )
    migration_run.issues = migrated.get("issues") or []
    migration_run.completed_at = datetime.now(UTC)
    await db_session.flush()
    return migration_run, migrated_record


async def get_or_create_projection(
    db_session: AsyncSession,
    *,
    record: Record,
    source_version: ProtocolVersion,
    target_version: ProtocolVersion,
    manifests: list[dict[str, Any]] | None,
    versions_by_name: dict[str, ProtocolVersion],
) -> RecordProjection:
    effective_manifests = manifests or []
    rule_hash = migration_path_hash(effective_manifests)
    existing = (
        await db_session.execute(
            select(RecordProjection).where(
                RecordProjection.record_id == record.id,
                RecordProjection.record_version == record.version,
                RecordProjection.target_protocol_version == target_version.version,
                RecordProjection.rule_hash == rule_hash,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    preview = await preview_migration_path(
        record.data,
        effective_manifests,
        source_version=source_version,
        target_version=target_version,
        versions_by_name=versions_by_name,
    ) if effective_manifests else {
        "data": record.data,
        "status": "completed",
        "issues": [],
        "not_collected": [],
        "requires_sandbox": False,
    }
    projection = RecordProjection(
        record_id=record.id,
        record_version=record.version,
        protocol_id=record.protocol_id,
        source_protocol_version=source_version.version,
        target_protocol_version=target_version.version,
        rule_hash=rule_hash,
        status=(
            "needs_review"
            if preview["requires_sandbox"] or preview["status"] == "needs_review"
            else "completed"
        ),
        projected_data=preview["data"],
        not_collected=preview["not_collected"],
        issues=preview["issues"],
    )
    db_session.add(projection)
    await db_session.flush()
    return projection
