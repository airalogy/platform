"""Bounded scalar ports for explicitly published Python/R Workflow methods.

Code and private historical results never supply a Schema. The caller verifies
the immutable publication/environment, both result Schemas, persisted digests,
and every exact source Record before exposing these values to another card.
"""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import ValidationError

from app.services.analysis_engine import AnalysisError
from app.services.analysis_schema import (
    MAX_SCHEMA_DEPTH,
    MAX_SCHEMA_FIELDS,
    MAX_SCHEMA_NODES,
    _pointer,
    _resolve,
    _type_signature,
    _unit,
)
from app.services.workflow_contracts import (
    MAX_ANALYSIS_OUTPUTS,
    MAX_GRAPH_BYTES,
    MAX_WORKFLOW_NODES,
    WorkflowComputeOutput,
    WorkflowContractError,
    WorkflowFieldCatalog,
    WorkflowFieldSpec,
    _bounded_json,
    _matches_scalar_type,
)
from app.services.workflow_data import (
    _PREFILL_DIALECTS,
    _PREFILL_FORMAT_CHECKER,
    _SCHEMA_LISTS,
    _SCHEMA_MAPS,
    _SCHEMA_SINGLES,
    MAX_SAFE_JSON_INTEGER,
    _compile_prefill_schema,
    _contains_asset_annotation,
    _prefill_root_properties,
)

MAX_COMPUTE_RESULT_SCHEMA_BYTES = 50_000


def _check_local_scopes(schema: dict) -> None:
    remaining = MAX_SCHEMA_NODES

    def visit(node, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > MAX_SCHEMA_DEPTH:
            raise WorkflowContractError("Compute result Schema exceeds local bounds")
        if type(node) is bool:
            return
        if not isinstance(node, dict):
            raise WorkflowContractError("Compute result Schema node is malformed")
        if set(node) & {
            "$id",
            "$anchor",
            "$dynamicAnchor",
            "$recursiveAnchor",
            "$dynamicRef",
            "$recursiveRef",
            "$vocabulary",
        }:
            raise WorkflowContractError(
                "Compute result Schema requires fixed local scopes"
            )
        if "$schema" in node and node["$schema"] not in _PREFILL_DIALECTS:
            raise WorkflowContractError("Unsupported Compute result Schema dialect")
        if "$ref" in node:
            try:
                if not isinstance(node["$ref"], str):
                    raise ValueError("Reference must be text")
                _pointer(schema, node["$ref"])
            except (AnalysisError, KeyError, ValueError, TypeError) as error:
                raise WorkflowContractError(
                    "Compute result references must be resolvable local pointers"
                ) from error
        for key in _SCHEMA_MAPS | {"$defs", "definitions"}:
            for child in node.get(key, {}).values():
                visit(child, depth + 1)
        for key in _SCHEMA_LISTS:
            for child in node.get(key, []):
                visit(child, depth + 1)
        for key in _SCHEMA_SINGLES & node.keys():
            visit(node[key], depth + 1)

    visit(schema)


def _type_view(node: Any) -> dict:
    """Read only declared type/unit; the full Schema validates all assertions."""
    if not isinstance(node, dict):
        raise AnalysisError("A scalar port requires a declared type")
    result = {key: node[key] for key in ("type", "unit") if key in node}
    for key in ("allOf", "anyOf", "oneOf"):
        if key in node:
            result[key] = [_type_view(child) for child in node[key]]
    return result


def _declares_object(node: Any) -> bool:
    """A positive object assertion remains binding through sibling alternatives."""
    return isinstance(node, dict) and (
        node.get("type") == "object"
        or any(_declares_object(branch) for branch in node.get("allOf", []))
    )


def _prepare(schema: dict) -> tuple[dict, dict]:
    try:
        if type(schema) is not dict:
            raise WorkflowContractError("Compute result Schema must be an object")
        _bounded_json(schema, MAX_COMPUTE_RESULT_SCHEMA_BYTES)
        Draft202012Validator.check_schema(schema)
        _check_local_scopes(schema)
        compiled = _compile_prefill_schema(
            schema, [schema], mode="value", selected=None
        )
        if not _declares_object(compiled):
            raise WorkflowContractError(
                "Compute result Schema must declare an object result"
            )
        return deepcopy(schema), compiled
    except (SchemaError, AnalysisError, KeyError, TypeError, ValueError) as error:
        if isinstance(error, WorkflowContractError):
            raise
        raise WorkflowContractError(
            "Compute result Schema is invalid or unsupported"
        ) from error


def validate_compute_result_schema(schema: dict) -> dict:
    """Validate without executing code or changing the persisted Schema meaning."""
    return _prepare(schema)[0]


def _result_fields(compiled: dict) -> list[dict[str, Any]]:
    result = []
    remaining = MAX_SCHEMA_NODES

    def visit(node, path=()):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or len(path) > MAX_SCHEMA_DEPTH:
            raise WorkflowContractError("Compute output catalog exceeds local bounds")
        if _declares_object(node):
            properties = _prefill_root_properties(node, [compiled])
            for key in sorted(properties):
                if key.strip() and len(key) <= 255:
                    visit({"allOf": properties[key]}, (*path, key))
            return
        try:
            view = _resolve(_type_view(node), [compiled])
        except (AnalysisError, KeyError, ValueError, TypeError):
            # A valid but ambiguous object/union remains report-only.
            return
        if not path or _contains_asset_annotation(node, [compiled]):
            return
        try:
            value_type, nullable = _type_signature(view.get("type"))
            unit = _unit(view)
            if unit is not None and value_type not in {"number", "integer"}:
                return
        except AnalysisError:
            return
        result.append(
            {
                "path": list(path),
                "value_type": value_type,
                "unit": unit,
                "nullable": nullable,
                "title": path[-1],
            }
        )
        if len(result) > MAX_SCHEMA_FIELDS:
            raise WorkflowContractError("Compute output catalog has too many fields")

    visit(compiled)
    return result


def compute_result_fields(schema: dict) -> list[dict[str, Any]]:
    """List supported object-key scalar paths; never index arrays or guess outputs."""
    return _result_fields(_prepare(schema)[1])


def _outputs(
    values: Sequence[WorkflowComputeOutput | dict],
) -> list[WorkflowComputeOutput]:
    if not isinstance(values, (list, tuple)) or len(values) > MAX_ANALYSIS_OUTPUTS:
        raise WorkflowContractError("Compute output declarations exceed their bound")
    try:
        result = [
            WorkflowComputeOutput.model_validate(
                item.model_dump(mode="json")
                if isinstance(item, WorkflowComputeOutput)
                else item
            )
            for item in values
        ]
    except (ValidationError, ValueError, TypeError) as error:
        raise WorkflowContractError("Invalid Compute output declaration") from error
    if len({item.output_id for item in result}) != len(result):
        raise WorkflowContractError("Compute output IDs must be unique")
    return result


def _catalog(compiled, outputs):
    fields = {tuple(item["path"]): item for item in _result_fields(compiled)}
    result = {}
    for output in outputs:
        field = fields.get(tuple(output.path))
        if field is None:
            raise WorkflowContractError(
                "Compute output references an unknown or unsupported scalar path"
            )
        spec = WorkflowFieldSpec(
            **{key: field[key] for key in ("value_type", "unit", "nullable")}
        )
        if (output.value_type, output.unit, output.nullable) != (
            spec.value_type,
            spec.unit,
            spec.nullable,
        ):
            raise WorkflowContractError(
                "Compute output type, unit or nullability conflicts with its Schema"
            )
        result[("analysis", output.output_id)] = spec
    return result


def compute_output_catalog(
    schema: dict, outputs: Sequence[WorkflowComputeOutput | dict]
) -> dict[tuple[str, str], WorkflowFieldSpec]:
    return _catalog(_prepare(schema)[1], _outputs(outputs))


def project_compute_outputs(
    schema: dict,
    sealed_result: dict,
    outputs: Sequence[WorkflowComputeOutput | dict],
    catalog: WorkflowFieldCatalog,
) -> dict[str, dict[str, Any]]:
    """Validate the complete method result before projecting exact nullable ports.

    The caller separately validates the environment output Schema and seals of
    the AnalysisRun/ComputeJob. Files and usage metadata are not scalar inputs.
    """
    compiled = _prepare(schema)[1]
    outputs = _outputs(outputs)
    expected = _catalog(compiled, outputs)
    if dict(catalog) != expected:
        raise WorkflowContractError("Compute result output catalog changed")
    result = (
        sealed_result.get("computed_result") if type(sealed_result) is dict else None
    )
    if type(result) is not dict:
        raise WorkflowContractError(
            "Compute analysis has no structured computed_result"
        )
    _bounded_json(result, MAX_GRAPH_BYTES)
    validator = Draft202012Validator(compiled, format_checker=_PREFILL_FORMAT_CHECKER)
    issue = next(validator.iter_errors(result), None)
    if issue is not None:
        raise WorkflowContractError(
            f"Compute result violates its method Schema: {issue.message}"
        )
    projected = {}
    for output in outputs:
        value = result
        for key in output.path:
            if type(value) is not dict or key not in value:
                raise WorkflowContractError(
                    "Compute result is missing a declared output path"
                )
            value = value[key]
        if value is None:
            if not output.nullable:
                raise WorkflowContractError("Compute output does not permit null")
        elif (
            not _matches_scalar_type(value, output.value_type)
            or type(value) is int
            and abs(value) > MAX_SAFE_JSON_INTEGER
            or isinstance(value, str)
            and value.strip().startswith("airalogy.id.file.")
        ):
            raise WorkflowContractError("Compute output has an invalid scalar value")
        projected[output.output_id] = value
    _bounded_json(projected, MAX_GRAPH_BYTES)
    return {"analysis": projected}


def validate_compute_method_inputs(
    input_schema_contract: dict, versions: Sequence[Any]
) -> None:
    """Arbitrary code requires the complete fixed input Schema, not guessed fields."""
    if (
        type(input_schema_contract) is not dict
        or set(input_schema_contract) != {"json_schema", "fields"}
        or not isinstance(versions, (list, tuple))
        or not 1 <= len(versions) <= MAX_WORKFLOW_NODES
    ):
        raise WorkflowContractError(
            "Compute methods require complete explicit input Schema contracts"
        )
    expected = _bounded_json(input_schema_contract, MAX_GRAPH_BYTES)
    try:
        for version in versions:
            actual = {"json_schema": version.json_schema, "fields": version.fields}
            if _bounded_json(actual, MAX_GRAPH_BYTES) != expected:
                raise WorkflowContractError(
                    "Compute input Schema differs from the published method contract"
                )
    except AttributeError as error:
        raise WorkflowContractError(
            "Compute input Protocol version is unavailable"
        ) from error
