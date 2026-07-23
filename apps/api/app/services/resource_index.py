"""Projection of versioned resource JSON into typed query rows."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from app.models.resource import ResourceFieldIndex, ResourceRevision


def _walk(value: Any, path: str = "") -> Iterable[tuple[str, int, Any]]:
    if isinstance(value, dict):
        if isinstance(value.get("id"), (str, int)) and isinstance(
            value.get("entity"), str
        ):
            yield path, 0, value
            return
        for key in sorted(value):
            child_path = f"{path}.{key}" if path else str(key)
            yield from _walk(value[key], child_path)
        return
    if isinstance(value, list):
        for ordinal, item in enumerate(value):
            if isinstance(item, (dict, list)):
                yield from _walk(item, f"{path}.{ordinal}")
            else:
                yield path, ordinal, item
        return
    yield path, 0, value


def _index_value(row: ResourceFieldIndex, value: Any) -> None:
    if isinstance(value, dict):
        row.value_type = "reference"
        row.ref_id = str(value["id"])
        row.value_text = str(value.get("label") or value["id"])
    elif isinstance(value, bool):
        row.value_type = "boolean"
        row.value_boolean = value
    elif isinstance(value, (int, float, Decimal)):
        row.value_type = "numeric"
        row.value_numeric = Decimal(str(value))
    elif isinstance(value, str):
        row.value_type = "text"
        row.value_text = value
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                row.value_numeric = Decimal(value)
                row.value_type = "numeric"
            except InvalidOperation:
                pass
        else:
            row.value_timestamp = parsed
            row.value_type = "timestamp"
    elif value is None:
        row.value_type = "null"
    else:
        row.value_type = "text"
        row.value_text = str(value)


def build_resource_indexes(
    *,
    resource_type_id,
    resource_id,
    revision: ResourceRevision,
) -> list[ResourceFieldIndex]:
    rows: list[ResourceFieldIndex] = []
    for path, ordinal, value in _walk(revision.data):
        if not path:
            continue
        row = ResourceFieldIndex(
            resource_type_id=resource_type_id,
            resource_id=resource_id,
            resource_revision_id=revision.id,
            path=path,
            ordinal=ordinal,
            value_type="null",
        )
        _index_value(row, value)
        rows.append(row)
    return rows
