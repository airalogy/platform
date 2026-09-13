"""Pure, Schema-based data flow for immutable manual Workflow graphs.

Protocol paths are ``['var', literal_field_key]`` relative to ``Record.data``;
published Workflow v2 analysis outputs use ``['analysis', declared_output_id]``.
The shared analysis Schema reader is the sole local-reference interpreter. Only
supported top-level scalars are exposed by default. Version 4 callers may opt in
to typed FileId ports, whose storage identity, bytes and permissions must already
have been authorized by the separate runtime adapter. They never become text.

The caller must load and authorize exact source Record revisions, verify their
hashes and completed Actions, and attach those identities to these value receipts.
This module cannot grant access, select latest Records or attest to provenance.
The merged initial values require the target Protocol's complete supported Schema
validation before user confirmation. Dynamic assigners and complete Record
validation remain the responsibility of the normal Record workflow.
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from app.services.analysis_engine import AnalysisError
from app.services.analysis_schema import (
    MAX_SCHEMA_DEPTH,
    MAX_SCHEMA_NODES,
    _pointer,
    _resolve,
    _variables_root,
    schema_fields,
)
from app.services.workflow_contracts import (
    MAX_INITIAL_VALUE_BYTES,
    WorkflowBinding,
    WorkflowContractError,
    WorkflowFieldCatalog,
    WorkflowFieldSpec,
    WorkflowGraph,
    _bounded_json,
    _matches_scalar_type,
    evaluate_workflow_condition,
    validate_workflow_conditions,
    validate_workflow_graph,
)

MAX_SAFE_JSON_INTEGER = 2**53 - 1
_PREFILL_FORMAT_CHECKER = FormatChecker()
_PREFILL_DIALECTS = {
    "https://json-schema.org/draft/2020-12/schema",
    "http://json-schema.org/draft/2020-12/schema",
}


@_PREFILL_FORMAT_CHECKER.checks("date-time", raises=ValueError)
def _prefill_datetime(value: Any) -> bool:
    """Validate timezone-qualified timestamps without optional network libraries.

    Python's datetime deliberately rejects leap seconds instead of guessing their
    date-specific validity. Like JSON Schema formats, non-strings are unaffected.
    """
    if not isinstance(value, str):
        return True
    if not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]+)?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])",
        value,
    ):
        return False
    datetime.fromisoformat(value.upper().replace("Z", "+00:00"))
    return True


_SCHEMA_ANNOTATIONS = {
    "$comment",
    "title",
    "description",
    "default",
    "examples",
    "deprecated",
    "readOnly",
    "writeOnly",
    "unit",
    "airalogy_type",
    "file_extension",
}
_SCHEMA_MAPS = {"properties", "patternProperties", "dependentSchemas"}
_SCHEMA_LISTS = {"allOf", "anyOf", "oneOf", "prefixItems"}
_SCHEMA_SINGLES = {
    "additionalProperties",
    "unevaluatedProperties",
    "propertyNames",
    "items",
    "contains",
    "unevaluatedItems",
    "not",
    "if",
    "then",
    "else",
}
_SCHEMA_ASSERTIONS = {
    "type",
    "enum",
    "const",
    "multipleOf",
    "maximum",
    "exclusiveMaximum",
    "minimum",
    "exclusiveMinimum",
    "maxLength",
    "minLength",
    "pattern",
    "maxItems",
    "minItems",
    "uniqueItems",
    "maxContains",
    "minContains",
    "maxProperties",
    "minProperties",
    "required",
    "dependentRequired",
    "format",
}
ResolvedScalar = (
    StrictStr
    | StrictBool
    | StrictInt
    | Annotated[float, Field(strict=True, allow_inf_nan=False)]
)


def _prefill_reference(ref: Any, documents: list[dict]) -> tuple[Any, list[dict]]:
    """Use the shared local pointer, but never guess conflicting document scope."""
    if not isinstance(ref, str):
        raise WorkflowContractError(
            "Workflow prefill references must be local pointers"
        )
    found = []
    for document in documents:
        try:
            found.append((_pointer(document, ref), document))
        except KeyError:
            continue
        except AnalysisError as error:
            raise WorkflowContractError(str(error)) from error
    if not found:
        raise WorkflowContractError(
            "Workflow prefill local reference cannot be resolved"
        )
    target, document = found[0]
    if any(other != target for other, _ in found[1:]):
        raise WorkflowContractError(
            "Workflow prefill reference has conflicting local definition scopes"
        )
    return target, [document] + [item for item in documents if item is not document]


def _prefill_root_properties(
    node: Any,
    documents: list[dict],
    *,
    depth: int = 0,
    trail: frozenset[int] = frozenset(),
    budget: list[int] | None = None,
) -> dict[str, list[Any]]:
    """Read only object shape, preserving each conjunct's original constraints."""
    budget = [MAX_SCHEMA_NODES] if budget is None else budget
    budget[0] -= 1
    if budget[0] < 0 or depth > MAX_SCHEMA_DEPTH or id(node) in trail:
        raise WorkflowContractError(
            "Workflow prefill Schema exceeds local resolution bounds"
        )
    if not isinstance(node, dict):
        raise WorkflowContractError("Workflow variable Schema must describe an object")
    trail = trail | {id(node)}
    result: dict[str, list[Any]] = {}
    if "$ref" in node:
        target, scopes = _prefill_reference(node["$ref"], documents)
        result = _prefill_root_properties(
            target, scopes, depth=depth + 1, trail=trail, budget=budget
        )
    for branch in node.get("allOf", []):
        for key, values in _prefill_root_properties(
            branch, documents, depth=depth + 1, trail=trail, budget=budget
        ).items():
            result.setdefault(key, []).extend(values)
    for key, value in node.get("properties", {}).items():
        result.setdefault(key, []).append(value)
    return result


def _compile_prefill_schema(
    node: Any,
    documents: list[dict],
    *,
    mode: str,
    selected: frozenset[str] | None,
    depth: int = 0,
    trail: frozenset[int] = frozenset(),
    budget: list[int] | None = None,
) -> dict | bool:
    """Expand local references by conjunction, never the analysis reader's merge.

    This is a bounded Schema-preserving adapter, not another scalar interpreter.
    JSON Schema itself performs every assertion. No reference survives this walk,
    so validation cannot access a network, filesystem, registry or dynamic scope.
    """
    budget = [MAX_SCHEMA_NODES] if budget is None else budget
    budget[0] -= 1
    if budget[0] < 0 or depth > MAX_SCHEMA_DEPTH or id(node) in trail:
        raise WorkflowContractError(
            "Workflow prefill Schema exceeds local resolution bounds"
        )
    if type(node) is bool:
        return node
    if not isinstance(node, dict):
        raise WorkflowContractError(
            "Workflow prefill Schema must be an object or boolean"
        )
    trail = trail | {id(node)}
    result: dict[str, Any] = {}
    conjuncts = []

    def compile_child(child, *, child_mode="value", scopes=documents):
        return _compile_prefill_schema(
            child,
            scopes,
            mode=child_mode,
            selected=selected,
            depth=depth + 1,
            trail=trail,
            budget=budget,
        )

    for key, value in node.items():
        if key == "$ref":
            target, scopes = _prefill_reference(value, documents)
            conjuncts.append(compile_child(target, child_mode=mode, scopes=scopes))
        elif key in {"$defs", "definitions"}:
            # Original documents remain pointer sources; unused definitions are
            # not evaluated, and referenced definitions are expanded in place.
            continue
        elif key == "$schema":
            if value not in _PREFILL_DIALECTS:
                raise WorkflowContractError(
                    "Workflow prefill requires a supported Schema dialect"
                )
        elif key in _SCHEMA_ANNOTATIONS:
            result[key] = copy.deepcopy(value)
        elif mode == "wrapper" and key == "properties":
            if "var" in value:
                variables = value["var"]
                scopes = (
                    [variables] if isinstance(variables, dict) else []
                ) + documents
                conjuncts.append(
                    compile_child(variables, child_mode="variables", scopes=scopes)
                )
        elif mode == "wrapper" and key in {"type", "required", "additionalProperties"}:
            # The historical Record envelope is not being prefilled: only its
            # var object is. Other envelope-level assertions cannot be projected.
            if (
                key == "type"
                and value != "object"
                or key == "additionalProperties"
                and type(value) is not bool
            ):
                raise WorkflowContractError(
                    "Unsupported Workflow Record wrapper constraint"
                )
        elif mode == "wrapper" and key != "allOf":
            raise WorkflowContractError(
                "Unsupported Workflow Record wrapper constraint"
            )
        elif key in _SCHEMA_MAPS:
            entries = (
                ((name, value[name]) for name in selected if name in value)
                if mode == "variables" and key == "properties" and selected is not None
                else value.items()
            )
            result[key] = {name: compile_child(schema) for name, schema in entries}
        elif key in _SCHEMA_LISTS:
            # Only positive conjuncts relax top-level required for partial input;
            # requirements inside alternatives/conditionals retain exact meaning.
            child_mode = mode if key == "allOf" else "value"
            result[key] = [compile_child(item, child_mode=child_mode) for item in value]
        elif key in _SCHEMA_SINGLES:
            result[key] = compile_child(value)
        elif key in _SCHEMA_ASSERTIONS:
            if key == "required" and mode == "variables":
                continue
            if key == "format" and value not in _PREFILL_FORMAT_CHECKER.checkers:
                raise WorkflowContractError(
                    "Unsupported Workflow prefill Schema format"
                )
            result[key] = copy.deepcopy(value)
        else:
            raise WorkflowContractError(
                f"Unsupported Workflow prefill Schema keyword: {key}"
            )
    if conjuncts:
        # Keep unevaluatedProperties/Items alongside the reference's annotation
        # results, rather than isolating those assertions in another allOf arm.
        result["allOf"] = [*conjuncts, *result.get("allOf", [])]
    return result


def _prepare_prefill_schema(version: Any) -> tuple[dict, list[dict], dict, bool]:
    """Validate the complete original structure once per catalog, never globally."""
    try:
        schema = version.json_schema
        _bounded_json(schema, MAX_INITIAL_VALUE_BYTES)
        if not isinstance(schema, dict):
            raise WorkflowContractError("Workflow prefill requires a variable Schema")
        root = schema.get("vars", schema.get("research_variable", schema))
        if not isinstance(root, dict):
            raise WorkflowContractError("Workflow prefill requires an object Schema")
        documents = [root] if root is schema else [root, schema]
        for document in documents:
            if "$schema" in document and document["$schema"] not in _PREFILL_DIALECTS:
                raise WorkflowContractError(
                    "Workflow prefill requires a supported Schema dialect"
                )
            if set(document) & {
                "$id",
                "$anchor",
                "$dynamicAnchor",
                "$recursiveAnchor",
                "$vocabulary",
            }:
                raise WorkflowContractError(
                    "Workflow prefill does not guess alternate reference scopes"
                )
            Draft202012Validator.check_schema(document)
        properties = _prefill_root_properties(root, documents)
        wrapper = False
        if "var" in properties and set(properties) <= {"var", "step", "check", "quiz"}:
            # Reuse the shared type view solely to identify the historic wrapper;
            # the original branches, not its merged output, are validated below.
            candidate = _resolve({"allOf": properties["var"]}, documents)
            wrapper = candidate.get("type") == "object" or "properties" in candidate
        if wrapper:
            variables = {}
            for part in properties["var"]:
                scopes = ([part] if isinstance(part, dict) else []) + documents
                for key, values in _prefill_root_properties(part, scopes).items():
                    variables.setdefault(key, []).extend(values)
            properties = variables
        if not properties or root.get("type", "object") != "object":
            raise WorkflowContractError(
                "Workflow prefill requires known object properties"
            )
        return root, documents, properties, wrapper
    except (
        AnalysisError,
        SchemaError,
        AttributeError,
        TypeError,
        KeyError,
        ValueError,
    ) as error:
        if isinstance(error, WorkflowContractError):
            raise
        raise WorkflowContractError(
            "Workflow prefill Schema is invalid or unsupported"
        ) from error


def _prepared_prefill_schema(
    prepared: tuple[dict, list[dict], dict, bool],
    field_names: frozenset[str] | None,
) -> dict[str, Any]:
    root, documents, properties, wrapper = prepared
    try:
        if field_names is not None and not field_names <= properties.keys():
            raise WorkflowContractError(
                "Workflow initial values contain unknown fields"
            )
        compiled = _compile_prefill_schema(
            root,
            documents,
            mode="wrapper" if wrapper else "variables",
            selected=field_names,
        )
        allowed = properties.keys() if field_names is None else field_names
        result = {
            "allOf": [
                compiled,
                {
                    "type": "object",
                    "properties": {key: {} for key in allowed},
                    "additionalProperties": False,
                },
            ],
        }
        Draft202012Validator.check_schema(result)
        _bounded_json(result, MAX_INITIAL_VALUE_BYTES)
        return result
    except (
        AnalysisError,
        SchemaError,
        AttributeError,
        TypeError,
        KeyError,
        ValueError,
    ) as error:
        if isinstance(error, WorkflowContractError):
            raise
        raise WorkflowContractError(
            "Workflow prefill Schema is invalid or unsupported"
        ) from error


def protocol_prefill_schema(
    version: Any,
    *,
    field_names: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Return a bounded, constraint-preserving Schema for flat partial values.

    Historical vars/research_variable/Record.var roots share the local pointer
    reader. Ref siblings and allOf constraints remain conjunctive. Only required
    at the variable-object level is relaxed; nested requirements remain intact.
    When field_names is specified, other fields are explicitly forbidden rather
    than expanded: unsupported absent fields cannot disable a usable scalar.
    """
    return _prepared_prefill_schema(_prepare_prefill_schema(version), field_names)


def validate_protocol_initial_values(version: Any, values: dict[str, Any]) -> None:
    """Validate partial flat prefill against every supported pinned constraint.

    This validates JSON Schema, not dynamic assigners or full Record submission.
    Empty initial values remain valid for Protocols without a field Schema.
    """
    if type(values) is not dict:
        raise WorkflowContractError("Workflow initial values must be an object")
    _bounded_json(values, MAX_INITIAL_VALUE_BYTES)
    if not values:
        return
    schema = protocol_prefill_schema(version, field_names=frozenset(values))
    error = next(
        Draft202012Validator(
            schema, format_checker=_PREFILL_FORMAT_CHECKER
        ).iter_errors(values),
        None,
    )
    if error is not None:
        # Do not put potentially private entered values into diagnostic strings.
        raise WorkflowContractError(
            "Workflow initial values do not satisfy the pinned Protocol Schema"
        )


def _asset_annotation(node: dict[str, Any]) -> bool:
    annotation = node.get("airalogy_type")
    if annotation is not None and not isinstance(annotation, str):
        return True
    if isinstance(annotation, str) and (
        annotation.startswith("FileId")
        or annotation
        in {
            "File",
            "ResearchFile",
            "ResourceRef",
            "EntityRef",
            "DataAsset",
            "DataAssetRef",
        }
    ):
        return True
    format_name = node.get("format")
    return (
        "file_extension" in node
        or "contentMediaType" in node
        or "contentEncoding" in node
        or format_name is not None
        and not isinstance(format_name, str)
        or isinstance(format_name, str)
        and format_name in {"binary", "byte"}
    )


def _contains_asset_annotation(
    node: Any,
    documents: list[dict[str, Any]],
    *,
    depth: int = 0,
    budget: list[int] | None = None,
    trail: frozenset[int] = frozenset(),
) -> bool:
    """Inspect every alternative's annotations without interpreting its type.

    The shared reader can merge a same-scalar-type union for analysis; a union
    containing FileId must nevertheless not become a plain-string data binding.
    This bounded metadata walk uses its exact local pointer resolver and scope.
    Unresolved annotations fail closed rather than guessing a reference type.
    """
    budget = [MAX_SCHEMA_NODES] if budget is None else budget
    budget[0] -= 1
    if budget[0] < 0 or depth > MAX_SCHEMA_DEPTH or id(node) in trail:
        return True
    if not isinstance(node, dict) or _asset_annotation(node):
        return True
    trail = trail | {id(node)}
    if "$ref" in node:
        target = None
        target_document = None
        for document in documents:
            try:
                target = _pointer(document, node["$ref"])
                target_document = document
                break
            except KeyError:
                continue
            except (AnalysisError, TypeError, AttributeError):
                return True
        if target_document is None or _contains_asset_annotation(
            target,
            [target_document]
            + [item for item in documents if item is not target_document],
            depth=depth + 1,
            budget=budget,
            trail=trail,
        ):
            return True
    for keyword in ("anyOf", "oneOf", "allOf"):
        if keyword not in node:
            continue
        branches = node[keyword]
        if not isinstance(branches, list) or any(
            _contains_asset_annotation(
                branch, documents, depth=depth + 1, budget=budget, trail=trail
            )
            for branch in branches
        ):
            return True
    return False


def protocol_field_catalog(
    version: Any,
    *,
    for_target: bool = False,
    include_files: bool = False,
) -> dict[tuple[str, str], WorkflowFieldSpec]:
    """Build trusted scalar specifications from one pinned ProtocolVersion.

    Unsupported fields are omitted, so a condition/binding naming one fails
    closed without blocking an unrelated supported field. Nullable fields are
    visible; an actual null value is never accepted as a binding or predicate.
    """
    try:
        fields = schema_fields(version)
        root, documents = _variables_root(version.json_schema)
    except (AnalysisError, AttributeError, TypeError, ValueError):
        # Graphs without data references do not need a variable Schema. A later
        # attempt to name any field in this empty catalog fails explicitly.
        return {}
    prepared = None
    all_targets_supported = False
    if for_target:
        try:
            prepared = _prepare_prefill_schema(version)
        except WorkflowContractError:
            return {}
        try:
            _prepared_prefill_schema(prepared, None)
            all_targets_supported = True
        except WorkflowContractError:
            # Only selected supported fields need expansion. Preparing/checking
            # the whole original Schema is not repeated for each target field.
            pass
    catalog = {}
    for field in fields:
        key = field["key"]
        if not key or len(key) > 255:
            continue
        field_type = field["type"]
        nullable = isinstance(field_type, list)
        if nullable:
            non_null = [item for item in field_type if item != "null"]
            if len(non_null) != 1:
                continue
            field_type = non_null[0]
        if field_type not in {"number", "integer", "string", "boolean"}:
            continue
        try:
            # Reuse the same bounded interpreter, including local $defs scope,
            # to keep FileId annotations that the analysis display omits.
            resolved = _resolve(root["properties"][key], documents)
        except (AnalysisError, ValueError, TypeError, KeyError):
            continue
        if _asset_annotation(resolved) or _contains_asset_annotation(
            root["properties"][key], documents
        ):
            if include_files:
                from app.services.workflow_file_contracts import protocol_file_spec

                file_spec = protocol_file_spec(root["properties"][key], documents)
                if file_spec is not None:
                    if for_target and not all_targets_supported:
                        try:
                            _prepared_prefill_schema(prepared, frozenset({key}))
                        except WorkflowContractError:
                            continue
                    catalog[("var", key)] = file_spec
            continue
        if field["unit"] is not None and field_type not in {"number", "integer"}:
            continue
        if for_target and not all_targets_supported:
            try:
                _prepared_prefill_schema(prepared, frozenset({key}))
            except WorkflowContractError:
                continue
        catalog[("var", key)] = WorkflowFieldSpec(
            value_type=field_type, nullable=nullable, unit=field["unit"]
        )
    return catalog


def _binding_field(
    binding: WorkflowBinding,
    catalog: WorkflowFieldCatalog,
    *,
    source: bool,
) -> WorkflowFieldSpec:
    path = binding.source_path if source else binding.target_path
    name = "source" if source else "target"
    spec = catalog.get(tuple(path))
    if not isinstance(spec, WorkflowFieldSpec):
        raise WorkflowContractError(
            f"Workflow binding {name} field is unknown or unsupported"
        )
    if spec.value_type != binding.value_type:
        raise WorkflowContractError(
            f"Workflow binding {name} field type does not match its pinned Schema"
        )
    if spec.unit != binding.unit:
        raise WorkflowContractError(
            f"Workflow binding {name} field unit does not match its pinned Schema"
        )
    return spec


def validate_workflow_data(
    graph: WorkflowGraph,
    field_catalog_by_node: Mapping[str, WorkflowFieldCatalog],
) -> None:
    """Require exact types/units and compatible file extensions for bindings."""
    graph = validate_workflow_graph(graph)
    validate_workflow_conditions(graph, field_catalog_by_node)
    for binding in graph.bindings:
        source = _binding_field(
            binding, field_catalog_by_node.get(binding.source_node_id, {}), source=True
        )
        target = _binding_field(
            binding, field_catalog_by_node.get(binding.target_node_id, {}), source=False
        )
        if (
            binding.value_type == "file"
            and source.file_extensions is not None
            and target.file_extensions is not None
            and not set(source.file_extensions) <= set(target.file_extensions)
        ):
            raise WorkflowContractError(
                "Workflow file port extensions conflict with the target Schema"
            )


class WorkflowResolvedBinding(WorkflowBinding):
    """A value receipt only; the authorized Record identity comes from the caller."""

    value: ResolvedScalar
    value_digest: StrictStr = Field(pattern=r"^[a-f0-9]{64}$")


class WorkflowBindingResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    initial_values: dict[str, Any]
    bindings: list[dict[str, Any]]


def _read_bound_value(binding: WorkflowBinding, output: Any) -> ResolvedScalar:
    value = output
    for segment in binding.source_path:
        if type(value) is not dict or segment not in value:
            raise WorkflowContractError("Workflow binding source value is missing")
        value = value[segment]
    if binding.value_type == "file":
        from app.services.workflow_file_contracts import parse_workflow_file_id

        parse_workflow_file_id(value)
        return value
    if not _matches_scalar_type(value, binding.value_type):
        raise WorkflowContractError(
            "Workflow binding source value is null or has a conflicting scalar type"
        )
    if isinstance(value, str) and value.strip().startswith("airalogy.id.file."):
        raise WorkflowContractError(
            "File references require a separate authorized file binding"
        )
    if (
        type(value) in {int, float}
        and (type(value) is int or value.is_integer())
        and abs(value) > MAX_SAFE_JSON_INTEGER
    ):
        raise WorkflowContractError(
            "Workflow binding integer cannot be represented exactly in the confirmation interface"
        )
    _bounded_json(value, MAX_INITIAL_VALUE_BYTES)
    return value


def resolve_workflow_bindings(
    graph: WorkflowGraph,
    target_node_id: str,
    source_outputs_by_node: Mapping[str, Any],
    field_catalog_by_node: Mapping[str, WorkflowFieldCatalog],
    *,
    file_values_by_binding: Mapping[str, str] | None = None,
) -> WorkflowBindingResolution:
    """Merge one target's static values with authorized direct-parent values.

    Caller-supplied outputs must be exact authorized Record.data or verified,
    declared analysis output projections of completed parents, not Action
    summaries or a guessed/latest Record. A binding
    from an inactive edge fails rather than borrowing another branch's evidence.
    Version 4 file values must be authorized sealed references, not original file
    IDs taken unchecked from JSON. The result is a draft: it neither writes
    Records nor approves downstream work.
    """
    graph = validate_workflow_graph(graph)
    validate_workflow_data(graph, field_catalog_by_node)
    target = next(
        (node for node in graph.nodes if node.node_id == target_node_id), None
    )
    if target is None or target.kind != "protocol":
        raise WorkflowContractError("Workflow binding target Protocol node is unknown")
    if file_values_by_binding is not None and set(file_values_by_binding) != {
        binding.binding_id
        for binding in graph.bindings
        if binding.target_node_id == target_node_id and binding.value_type == "file"
    }:
        raise WorkflowContractError(
            "Authorized file values must match the exact target binding set"
        )
    initial_values = copy.deepcopy(target.initial_values)
    edges = {(edge.source_node_id, edge.target_node_id): edge for edge in graph.edges}
    receipts = []
    for binding in sorted(graph.bindings, key=lambda item: item.binding_id):
        if binding.target_node_id != target_node_id:
            continue
        if binding.source_node_id not in source_outputs_by_node:
            raise WorkflowContractError(
                "Workflow binding has no authorized completed source output"
            )
        output = source_outputs_by_node[binding.source_node_id]
        edge = edges[(binding.source_node_id, binding.target_node_id)]
        if edge.condition is not None and not evaluate_workflow_condition(
            edge.condition, output, field_catalog_by_node[binding.source_node_id]
        ):
            raise WorkflowContractError(
                "Workflow binding source control edge was not selected"
            )
        value = (
            file_values_by_binding[binding.binding_id]
            if binding.value_type == "file" and file_values_by_binding is not None
            else _read_bound_value(binding, output)
        )
        if binding.value_type == "file":
            from app.services.workflow_file_contracts import (
                validate_workflow_file_value,
            )

            for node_id, path in (
                (binding.source_node_id, binding.source_path),
                (binding.target_node_id, binding.target_path),
            ):
                validate_workflow_file_value(
                    value, field_catalog_by_node[node_id][tuple(path)]
                )
        initial_values[binding.target_path[1]] = value
        receipts.append(
            WorkflowResolvedBinding(
                **binding.model_dump(mode="json"),
                value=value,
                value_digest=hashlib.sha256(
                    _bounded_json(value, MAX_INITIAL_VALUE_BYTES)
                ).hexdigest(),
            ).model_dump(mode="json")
        )
    _bounded_json(initial_values, MAX_INITIAL_VALUE_BYTES)
    return WorkflowBindingResolution(initial_values=initial_values, bindings=receipts)
