"""Bounded file descriptors, not storage access or permission propagation.

A FileId is a typed reference, never ordinary text and never a download URL.
Runtime adapters must separately authorize, seal and verify the bytes and source
identities before supplying a reference to a downstream Protocol.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from app.services.analysis_engine import AnalysisError
from app.services.analysis_schema import MAX_SCHEMA_DEPTH, MAX_SCHEMA_NODES, _pointer
from app.services.workflow_contracts import (
    WorkflowComputeFileOutput,
    WorkflowContractError,
    WorkflowFieldSpec,
)

_EXTENSION = re.compile(r"^[a-z0-9]{1,32}$")
_FILE_ID = re.compile(
    r"^airalogy\.id\.file\.([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})\.([a-z0-9]{1,32})$"
)
_MAX_VARIANTS = 64


def _unsupported_scope(node):
    from app.services.workflow_data import _PREFILL_DIALECTS

    return (
        not isinstance(node, dict)
        or bool(
            {
                "$id",
                "$anchor",
                "$dynamicAnchor",
                "$recursiveAnchor",
                "$vocabulary",
                "$dynamicRef",
                "$recursiveRef",
            }
            & node.keys()
        )
        or ("$schema" in node and node["$schema"] not in _PREFILL_DIALECTS)
    )


def parse_workflow_file_id(value: Any) -> tuple[UUID, str]:
    if type(value) is not str or (match := _FILE_ID.fullmatch(value)) is None:
        raise WorkflowContractError("Workflow file input must be a canonical FileId")
    return UUID(match[1]), match[2]


def validate_workflow_file_value(value: Any, spec: WorkflowFieldSpec) -> str:
    if spec.value_type != "file":
        raise WorkflowContractError(
            "Workflow file input requires an explicit file port"
        )
    _, extension = parse_workflow_file_id(value)
    if spec.file_extensions is not None and extension not in spec.file_extensions:
        raise WorkflowContractError(
            "Workflow file extension conflicts with the pinned Schema"
        )
    return value


def _variants(node, documents, *, depth=0, trail=frozenset(), budget=None):
    """Keep each union branch's annotations; do not merge FileId and plain text."""
    budget = [MAX_SCHEMA_NODES] if budget is None else budget
    budget[0] -= 1
    if (
        budget[0] < 0
        or depth > MAX_SCHEMA_DEPTH
        or id(node) in trail
        or _unsupported_scope(node)
        or {"$dynamicRef", "$recursiveRef", "if", "then", "else", "not"} & node.keys()
    ):
        raise WorkflowContractError("Unsupported Workflow file Schema")
    trail = trail | {id(node)}
    result = [
        [
            {
                key: value
                for key, value in node.items()
                if key not in {"$ref", "allOf", "anyOf", "oneOf"}
            }
        ]
    ]

    def expand(child, scopes=documents):
        return _variants(child, scopes, depth=depth + 1, trail=trail, budget=budget)

    def combine(variants):
        nonlocal result
        if not variants or len(result) * len(variants) > _MAX_VARIANTS:
            raise WorkflowContractError("Workflow file Schema exceeds branch bounds")
        result = [left + right for left in result for right in variants]

    if "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str):
            raise WorkflowContractError(
                "Workflow file references must be local pointers"
            )
        found = []
        for document in documents:
            try:
                found.append((_pointer(document, ref), document))
            except KeyError:
                continue
        if not found or any(value != found[0][0] for value, _ in found[1:]):
            raise WorkflowContractError(
                "Workflow file reference is missing or ambiguous"
            )
        target, document = found[0]
        combine(
            expand(target, [document] + [d for d in documents if d is not document])
        )
    if "allOf" in node:
        branches = node["allOf"]
        if not isinstance(branches, list) or not 1 <= len(branches) <= 16:
            raise WorkflowContractError("Invalid Workflow file composition")
        for branch in branches:
            combine(expand(branch))
    for keyword in ("anyOf", "oneOf"):
        if keyword in node:
            branches = node[keyword]
            if not isinstance(branches, list) or not 1 <= len(branches) <= 16:
                raise WorkflowContractError("Invalid Workflow file union")
            combine([variant for branch in branches for variant in expand(branch)])
    return result


def protocol_file_spec(node, documents) -> WorkflowFieldSpec | None:
    """Recognize ordinary Airalogy FileId schemas including local refs/nulls.

    Every possible non-null variant must explicitly be a file. Conflicting or
    unknown asset annotations are excluded rather than treated as plain strings.
    Full JSON Schema assertions are independently checked at prefill time.
    """
    try:
        if any(_unsupported_scope(document) for document in documents):
            return None
        extensions = set()
        unrestricted = nullable = has_file = False
        for variant in _variants(node, documents):
            types = {
                "string",
                "null",
                "number",
                "integer",
                "boolean",
                "object",
                "array",
            }
            annotations = set()
            declared_extensions = set()
            for constraint in variant:
                if "type" in constraint:
                    declared = constraint["type"]
                    declared = declared if isinstance(declared, list) else [declared]
                    if not declared or any(type(item) is not str for item in declared):
                        return None
                    types &= set(declared)
                if constraint.get("const", object()) is None:
                    types &= {"null"}
                if "airalogy_type" in constraint:
                    annotation = constraint["airalogy_type"]
                    if not isinstance(annotation, str) or not re.fullmatch(
                        r"FileId(?:[A-Z0-9]+)?", annotation
                    ):
                        return None
                    annotations.add(annotation)
                    if annotation != "FileId":
                        declared_extensions.add(annotation[6:].lower())
                if "file_extension" in constraint:
                    extension = constraint["file_extension"]
                    if not isinstance(extension, str) or not _EXTENSION.fullmatch(
                        extension
                    ):
                        return None
                    declared_extensions.add(extension)
                if (
                    constraint.get("unit") is not None
                    or "contentEncoding" in constraint
                    or constraint.get("format") in {"binary", "byte"}
                ):
                    return None
            if not types:
                return None
            nullable |= "null" in types
            if types == {"null"}:
                continue
            if (
                types - {"null"} != {"string"}
                or not annotations
                or len(declared_extensions) > 1
            ):
                return None
            has_file = True
            if declared_extensions:
                extensions |= declared_extensions
            else:
                unrestricted = True
        if not has_file:
            return None
        return WorkflowFieldSpec(
            value_type="file",
            nullable=nullable,
            file_extensions=None if unrestricted else sorted(extensions),
        )
    except (
        AnalysisError,
        WorkflowContractError,
        TypeError,
        ValueError,
        AttributeError,
    ):
        return None


def compute_file_output_catalog(
    recipe: Mapping[str, Any], outputs: list[WorkflowComputeFileOutput]
) -> dict[tuple[str, str], WorkflowFieldSpec]:
    """Project only explicitly declared manifest entries, never arbitrary paths."""
    if recipe.get("kind") != "compute":
        if outputs:
            raise WorkflowContractError("Only Compute methods have file outputs")
        return {}
    declarations = recipe.get("output_files", [])
    if not isinstance(declarations, list) or any(
        not isinstance(item, dict) for item in declarations
    ):
        raise WorkflowContractError("Compute file manifest is invalid")
    manifest = {item.get("mount_name"): item for item in declarations}
    if len(manifest) != len(declarations):
        raise WorkflowContractError("Compute file manifest contains duplicate names")
    catalog = {}
    for output in outputs:
        declared = manifest.get(output.mount_name)
        extension = output.mount_name.rsplit(".", 1)[-1]
        if (
            declared is None
            or "." not in output.mount_name
            or not _EXTENSION.fullmatch(extension)
            or type(declared.get("required", True)) is not bool
        ):
            raise WorkflowContractError(
                "Compute file port requires a declared manifest file with an extension"
            )
        key = ("analysis", output.output_id)
        if key in catalog:
            raise WorkflowContractError("Compute file output IDs must be unique")
        catalog[key] = WorkflowFieldSpec(
            value_type="file",
            nullable=not declared.get("required", True),
            file_extensions=[extension],
        )
    return catalog
