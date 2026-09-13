"""Extract scalar analysis fields from pinned, local Protocol JSON Schemas.

This is not a general JSON Schema interpreter. Unsupported fields remain visible
but unselectable; they never prevent analysis of unrelated supported variables.
No reference is fetched, evaluated or interpreted as a filesystem path.
"""

from __future__ import annotations

import json
import math
from typing import Any

from app.services.analysis_engine import AnalysisError

MAX_SCHEMA_DEPTH = 16
MAX_SCHEMA_FIELDS = 2_000
MAX_ENUM_VALUES = 1_000
MAX_REFERENCE_LENGTH = 2_000
MAX_SCHEMA_NODES = 512
_SCALAR_TYPES = {"number", "integer", "string", "boolean"}


def _type_signature(value: Any) -> tuple[str, bool]:
    values = value if isinstance(value, list) else [value]
    if not values or not all(isinstance(item, str) for item in values):
        raise AnalysisError("Analysis requires an explicit scalar Schema type")
    non_null = set(values) - {"null"}
    if len(values) != len(set(values)) or len(non_null) != 1:
        raise AnalysisError("Analysis does not merge different non-null Schema types")
    field_type = next(iter(non_null))
    if field_type not in _SCALAR_TYPES:
        raise AnalysisError("Only scalar Schema fields support this analysis")
    return field_type, "null" in values


def _unit(node: dict[str, Any]) -> str | None:
    value = node.get("unit")
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 255:
        raise AnalysisError("Schema units must be bounded text")
    return value.strip() or None


def _merge(base: dict[str, Any], sibling: dict[str, Any]) -> dict[str, Any]:
    """Do not silently override type, unit or enum constraints behind a ref."""

    for name in ("type", "enum", "const"):
        if name in base and name in sibling and base[name] != sibling[name]:
            raise AnalysisError(
                "Conflicting Schema reference or composition constraints"
            )
    base_unit, sibling_unit = _unit(base), _unit(sibling)
    if base_unit and sibling_unit and base_unit != sibling_unit:
        raise AnalysisError("Conflicting Schema units require an explicit mapping")
    result = {**base, **sibling}
    for name in ("properties", "$defs", "definitions"):
        if name in base and name in sibling:
            left, right = base[name], sibling[name]
            if not isinstance(left, dict) or not isinstance(right, dict):
                raise AnalysisError("Malformed Schema object composition")
            if any(left[key] != right[key] for key in left.keys() & right.keys()):
                raise AnalysisError("Conflicting Schema object composition")
            result[name] = {**left, **right}
    if base_unit or sibling_unit:
        result["unit"] = sibling_unit or base_unit
    return result


def _pointer(document: dict[str, Any], ref: str) -> Any:
    if not ref.startswith("#/") or len(ref) > MAX_REFERENCE_LENGTH:
        raise AnalysisError("Only bounded local JSON Pointer references are supported")
    node: Any = document
    for encoded in ref[2:].split("/"):
        # JSON Pointer decoding order matters for names containing literal ~1.
        for index, char in enumerate(encoded):
            if char == "~" and (
                index + 1 == len(encoded) or encoded[index + 1] not in "01"
            ):
                raise AnalysisError("Invalid local JSON Pointer escape")
        key = encoded.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or key not in node:
            raise KeyError(ref)
        node = node[key]
    return node


def _resolve(
    node: Any,
    documents: list[dict[str, Any]],
    *,
    depth: int = 0,
    trail: frozenset[int] = frozenset(),
    budget: list[int] | None = None,
) -> dict[str, Any]:
    budget = [MAX_SCHEMA_NODES] if budget is None else budget
    budget[0] -= 1
    if budget[0] < 0:
        raise AnalysisError("Analysis Schema resolution node budget exceeded")
    if depth > MAX_SCHEMA_DEPTH:
        raise AnalysisError("Analysis Schema reference depth exceeded")
    if not isinstance(node, dict):
        raise AnalysisError("Analysis field Schema must be an object")
    if id(node) in trail:
        raise AnalysisError("Cyclic analysis Schema references are unsupported")
    trail = trail | {id(node)}
    resolved = dict(node)
    if "$dynamicRef" in resolved or "$recursiveRef" in resolved:
        raise AnalysisError("Dynamic Schema references are unsupported")
    if "$ref" in resolved:
        ref = resolved.pop("$ref")
        if not isinstance(ref, str):
            raise AnalysisError("Schema references must be local JSON Pointers")
        target = None
        target_document = None
        for document in documents:
            try:
                target = _pointer(document, ref)
                target_document = document
                break
            except KeyError:
                continue
        if target_document is None:
            raise AnalysisError("Local Schema reference cannot be resolved")
        scopes = [target_document] + [d for d in documents if d is not target_document]
        resolved = _merge(
            _resolve(target, scopes, depth=depth + 1, trail=trail, budget=budget),
            resolved,
        )
    for keyword in ("anyOf", "oneOf"):
        if keyword not in resolved:
            continue
        branches = resolved.pop(keyword)
        if not isinstance(branches, list) or not 1 <= len(branches) <= 16:
            raise AnalysisError("Analysis Schema union exceeds supported bounds")
        items = [
            _resolve(branch, documents, depth=depth + 1, trail=trail, budget=budget)
            for branch in branches
        ]
        nullable = any(
            item.get("type") == "null" or item == {"const": None} for item in items
        )
        non_null = [
            item
            for item in items
            if item.get("type") != "null" and item != {"const": None}
        ]
        if not non_null:
            raise AnalysisError("A null-only Schema cannot be analyzed")
        if keyword == "oneOf" and len(non_null) > 1:
            raise AnalysisError(
                "Overlapping oneOf alternatives require explicit mapping"
            )
        signatures = [_type_signature(item.get("type")) for item in non_null]
        types = {item[0] for item in signatures}
        if len(types) != 1:
            raise AnalysisError(
                "Analysis does not merge different non-null Schema types"
            )
        nullable = nullable or any(item[1] for item in signatures)
        units = {_unit(item) for item in non_null}
        if len(units) != 1:
            raise AnalysisError(
                "Conflicting Schema union units require explicit mapping"
            )
        merged = dict(non_null[0])
        field_type = next(iter(types))
        merged["type"] = [field_type, "null"] if nullable else field_type
        if len(non_null) > 1:
            if all("enum" in item for item in non_null):
                if any(not isinstance(item["enum"], list) for item in non_null):
                    raise AnalysisError("Schema enum must be a list")
                values = [value for item in non_null for value in item["enum"]]
                if len(values) > MAX_ENUM_VALUES:
                    raise AnalysisError("Analysis Schema enum is too large")
                merged["enum"] = list(
                    {
                        json.dumps(value, sort_keys=True, allow_nan=False): value
                        for value in values
                    }.values()
                )
            else:
                merged.pop("enum", None)
        resolved = _merge(merged, resolved)
    if "allOf" in resolved:
        branches = resolved.pop("allOf")
        if not isinstance(branches, list) or not 1 <= len(branches) <= 16:
            raise AnalysisError("Analysis Schema composition exceeds supported bounds")
        for branch in branches:
            resolved = _merge(
                _resolve(
                    branch, documents, depth=depth + 1, trail=trail, budget=budget
                ),
                resolved,
            )
    return resolved


def _variables_root(
    schema: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if "vars" in schema:
        root = schema["vars"]
    elif "research_variable" in schema:
        root = schema["research_variable"]
    else:
        root = schema
    if not isinstance(root, dict):
        raise AnalysisError("Protocol variable Schema must be an object")
    documents = [root] if root is schema else [root, schema]
    resolved = _resolve(root, documents)
    # Historic resource and Record migrations also store a properties.var wrapper.
    properties = resolved.get("properties")
    if (
        isinstance(properties, dict)
        and "var" in properties
        and set(properties) <= {"var", "step", "check", "quiz"}
    ):
        candidate = _resolve(properties["var"], documents)
        if candidate.get("type") == "object" or "properties" in candidate:
            resolved = candidate
    if resolved.get("type") not in {None, "object"}:
        raise AnalysisError("Protocol variable Schema must describe an object")
    if not isinstance(resolved.get("properties", {}), dict):
        raise AnalysisError("Protocol Schema properties must be an object")
    if len(resolved.get("properties", {})) > MAX_SCHEMA_FIELDS:
        raise AnalysisError("Protocol analysis field catalog exceeds 2000 fields")
    # Independently generated vars Schemas may own $defs, while envelope-level
    # definitions remain a fallback. Dereferenced documents retain their scope.
    documents = [resolved] + [d for d in documents if d is not resolved]
    return resolved, documents


def _enum_values(node: dict[str, Any], field_type: str, nullable: bool) -> list | None:
    values = node.get("enum")
    if "const" in node:
        if values is not None and node["const"] not in values:
            raise AnalysisError("Schema const conflicts with its enum")
        values = [node["const"]]
    if values is None:
        return None
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_ENUM_VALUES:
        raise AnalysisError("Schema enum must contain 1 to 1000 scalar values")
    for value in values:
        valid = (
            value is None
            and nullable
            or field_type == "string"
            and type(value) is str
            or field_type == "boolean"
            and type(value) is bool
            or field_type == "integer"
            and type(value) is int
            or field_type == "number"
            and type(value) in {int, float}
        )
        if not valid:
            raise AnalysisError("Schema enum values do not match the scalar type")
        if type(value) in {int, float}:
            try:
                finite = math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite:
                raise AnalysisError("Non-finite Schema enum values are unsupported")
    return list(values)


def schema_fields(version: Any) -> list[dict[str, Any]]:
    """Return literal scalar field contracts from an exact ProtocolVersion.

    ``version`` is duck-typed and only needs ``json_schema`` and ``version``.
    Scalar constraints come from that stored Schema, not inferred from Records.
    Unsupported local fields retain their name with ``type='unsupported'``.
    """

    schema = version.json_schema
    if not isinstance(schema, dict):
        raise AnalysisError("Protocol variable Schema must be an object")
    root, documents = _variables_root(schema)
    result = []
    for key, raw in root.get("properties", {}).items():
        if not isinstance(key, str):
            raise AnalysisError("Protocol Schema field names must be strings")
        title = raw.get("title") if isinstance(raw, dict) else None
        field = {
            "key": key,
            "title": title if isinstance(title, str) and title else key,
            "type": "unsupported",
            "unit": None,
            "protocol_version": version.version,
        }
        try:
            node = _resolve(raw, documents)
            field_type, nullable = _type_signature(node.get("type"))
            unit = _unit(node)
            enum = _enum_values(node, field_type, nullable)
            field.update(
                title=node.get("title") if isinstance(node.get("title"), str) else key,
                type=[field_type, "null"] if nullable else field_type,
                unit=unit,
            )
            if enum is not None:
                field["enum"] = enum
        except (AnalysisError, ValueError, TypeError) as error:
            field["unsupported_reason"] = str(error)
        result.append(field)
    return result
