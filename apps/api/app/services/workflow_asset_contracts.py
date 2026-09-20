"""Pure contracts for exact DataAsset Workflow inputs, without storage or ACLs.

The caller must verify the version, source ResearchFile, blob bytes and current
read permissions before using these functions. A Schema is not evidence that a
file contains particular values: only ``parse_asset_json`` reads actual bytes.
File aliases are created by the authorized runtime, never by interpreting JSON.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.services.workflow_compute_contracts import (
    _prepare as _prepare_local_schema,
)
from app.services.workflow_compute_contracts import (
    _result_fields as _local_scalar_fields,
)
from app.services.workflow_contracts import (
    MAX_GRAPH_BYTES,
    MAX_INITIAL_VALUE_BYTES,
    MAX_WORKFLOW_ASSET_PATH_KEYS,
    WorkflowAssetBinding,
    WorkflowContractError,
    WorkflowFieldCatalog,
    WorkflowFieldSpec,
    WorkflowGraph,
    _bounded_json,
    _matches_scalar_type,
    validate_workflow_graph,
)
from app.services.workflow_data import (
    _PREFILL_FORMAT_CHECKER,
    MAX_SAFE_JSON_INTEGER,
)

MAX_ASSET_JSON_BYTES = MAX_GRAPH_BYTES


def _schema(schema: dict) -> dict:
    """Reuse the shared local-only, full-constraint compiler, not a type merge."""
    try:
        return _prepare_local_schema(schema)[1]
    except (WorkflowContractError, TypeError, ValueError, RecursionError) as error:
        raise WorkflowContractError(
            "DataAsset JSON Schema is invalid or unsupported"
        ) from error


def asset_field_catalog(schema: dict) -> dict[tuple[str, ...], WorkflowFieldSpec]:
    """Expose declared object-key scalars, never array rows or FileId strings.

    Ambiguous/complex fields have no scalar port. The complete Schema remains
    mandatory for parsing, so a field catalog never discards validation rules.
    """
    return {
        ("json", *field["path"]): WorkflowFieldSpec(
            **{name: field[name] for name in ("value_type", "unit", "nullable")}
        )
        for field in _local_scalar_fields(_schema(schema))
        if len(field["path"]) <= MAX_WORKFLOW_ASSET_PATH_KEYS
    }


def asset_file_catalog(extension: str) -> dict[tuple[str, ...], WorkflowFieldSpec]:
    """Describe a separately verified whole file, not user-supplied metadata.

    The runtime derives this extension from the actual sealed logical file and
    validates file type/header independently. This function grants no access.
    """
    if type(extension) is not str or not re.fullmatch(r"[a-z0-9]{1,32}", extension):
        raise WorkflowContractError(
            "DataAsset whole-file input requires a canonical file extension"
        )
    return {
        ("file",): WorkflowFieldSpec(
            value_type="file", nullable=False, file_extensions=[extension]
        )
    }


def _unique_object(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            raise WorkflowContractError("DataAsset JSON contains duplicate object keys")
        value[key] = child
    return value


def _reject_constant(_value):
    raise WorkflowContractError("DataAsset JSON numbers must be finite")


def _safe_numbers(value: Any) -> None:
    """Do not carry browser-inexact integer values through a sealed JSON view."""
    pending = [value]
    while pending:
        item = pending.pop()
        if type(item) is dict:
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)
        elif (
            type(item) in {int, float}
            and (type(item) is int or item.is_integer())
            and abs(item) > MAX_SAFE_JSON_INTEGER
        ):
            raise WorkflowContractError(
                "DataAsset JSON integer cannot be represented exactly in the confirmation interface"
            )


def parse_asset_json(content: bytes, schema: dict) -> dict[str, Any]:
    """Parse bounded actual UTF-8 bytes and enforce the complete fixed Schema.

    No defaults, coercion, inferred units, external references or field repair.
    Error text deliberately excludes private values and JSON validation details.
    """
    if type(content) is not bytes or not 0 < len(content) <= MAX_ASSET_JSON_BYTES:
        raise WorkflowContractError("DataAsset JSON bytes are missing or exceed 1 MiB")
    compiled = _schema(schema)
    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError, RecursionError) as error:
        if isinstance(error, WorkflowContractError):
            raise
        raise WorkflowContractError("DataAsset file is not valid UTF-8 JSON") from error
    if type(value) is not dict:
        raise WorkflowContractError("DataAsset JSON must contain an object document")
    _bounded_json(value, MAX_ASSET_JSON_BYTES)
    _safe_numbers(value)
    try:
        validator = Draft202012Validator(
            compiled, format_checker=_PREFILL_FORMAT_CHECKER
        )
        invalid = next(validator.iter_errors(value), None)
    except (ValueError, TypeError, RecursionError) as error:
        raise WorkflowContractError(
            "DataAsset JSON Schema cannot be validated"
        ) from error
    if invalid is not None:
        raise WorkflowContractError("DataAsset JSON violates its complete fixed Schema")
    return value


def _binding(value: WorkflowAssetBinding | dict) -> WorkflowAssetBinding:
    try:
        return WorkflowAssetBinding.model_validate(
            value.model_dump(mode="json")
            if isinstance(value, WorkflowAssetBinding)
            else value
        )
    except (ValidationError, TypeError, ValueError) as error:
        raise WorkflowContractError("Invalid Workflow DataAsset binding") from error


def _field(
    binding: WorkflowAssetBinding,
    catalog: WorkflowFieldCatalog,
    *,
    target: bool,
) -> WorkflowFieldSpec:
    path = binding.target_path if target else binding.source_path
    name = "target" if target else "source"
    spec = catalog.get(tuple(path)) if isinstance(catalog, Mapping) else None
    if not isinstance(spec, WorkflowFieldSpec):
        raise WorkflowContractError(
            f"Workflow DataAsset {name} field is unknown or unsupported"
        )
    try:
        spec = WorkflowFieldSpec.model_validate(spec.model_dump(mode="json"))
    except ValidationError as error:
        raise WorkflowContractError(
            "Workflow DataAsset field catalog is invalid"
        ) from error
    if (binding.value_type, binding.unit) != (spec.value_type, spec.unit):
        raise WorkflowContractError(
            f"Workflow DataAsset {name} type or unit differs from the pinned Schema"
        )
    return spec


def validate_workflow_asset_targets(
    graph: WorkflowGraph, target_catalogs: Mapping[str, WorkflowFieldCatalog]
) -> None:
    """Validate public target contracts without selecting/disclosing private assets.

    Complete target prefill constraints and actual file extension compatibility
    must also be checked once the runtime resolves a particular source version.
    """
    graph = validate_workflow_graph(graph)
    if not isinstance(target_catalogs, Mapping):
        raise WorkflowContractError(
            "Workflow target catalogs must be explicit mappings"
        )
    for binding in graph.asset_bindings:
        _field(binding, target_catalogs.get(binding.target_node_id, {}), target=True)


def resolve_asset_value(
    binding: WorkflowAssetBinding | dict,
    payload: dict,
    catalog: WorkflowFieldCatalog,
) -> str | bool | int | float:
    """Read one declared scalar from the actual parsed JSON document.

    ``payload`` is the direct return from ``parse_asset_json``, not a ``json``
    envelope. Null never becomes a successful binding, including nullable fields.
    Whole-file bindings require a runtime-sealed alias and intentionally fail here.
    """
    binding = _binding(binding)
    _field(binding, catalog, target=False)
    if binding.value_type == "file":
        raise WorkflowContractError(
            "Whole-file DataAsset bindings require an authorized runtime file receipt"
        )
    _bounded_json(payload, MAX_ASSET_JSON_BYTES)
    value = payload
    for key in binding.source_path[1:]:
        if type(value) is not dict or key not in value:
            raise WorkflowContractError("Workflow DataAsset source value is missing")
        value = value[key]
    if not _matches_scalar_type(value, binding.value_type):
        raise WorkflowContractError(
            "Workflow DataAsset source value is null or has a conflicting scalar type"
        )
    if type(value) is str and value.strip().startswith("airalogy.id.file."):
        raise WorkflowContractError(
            "File references require a separately authorized whole-file DataAsset binding"
        )
    _safe_numbers(value)
    _bounded_json(value, MAX_INITIAL_VALUE_BYTES)
    return value
