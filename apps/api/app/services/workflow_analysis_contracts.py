"""Pure, bounded contracts for published builtin methods in Workflow v2.

The caller authorizes the Project method publication and every exact upstream
Record/Protocol revision. These helpers never select Records, infer latest data,
publish private methods or grant access. They reuse the existing deterministic
analysis engine and its Schema reader, not another scientific interpreter.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from app.services.analysis_engine import (
    ENGINE_VERSION,
    MAX_GROUPS,
    AnalysisError,
    AnalysisRecipe,
    validate_recipe,
)
from app.services.analysis_schema import schema_fields
from app.services.workflow_contracts import (
    MAX_ANALYSIS_OUTPUTS,
    MAX_GRAPH_BYTES,
    MAX_WORKFLOW_NODES,
    WorkflowAnalysisOutput,
    WorkflowContractError,
    WorkflowFieldCatalog,
    WorkflowFieldSpec,
    _bounded_json,
    _matches_scalar_type,
)

_COUNTS = {"count", "missing", "invalid"}
_PRESERVE_NUMERIC_TYPE = {"min", "max", "sum"}


def _recipe(value: AnalysisRecipe | dict) -> AnalysisRecipe:
    try:
        if isinstance(value, AnalysisRecipe):
            value = value.model_dump(mode="json")
        return AnalysisRecipe.model_validate(value)
    except (ValidationError, ValueError, TypeError) as error:
        raise WorkflowContractError(
            "Workflow analysis requires a supported builtin recipe"
        ) from error


def _outputs(
    values: Sequence[WorkflowAnalysisOutput | dict],
) -> list[WorkflowAnalysisOutput]:
    if not isinstance(values, (list, tuple)) or len(values) > MAX_ANALYSIS_OUTPUTS:
        raise WorkflowContractError(
            "Workflow analysis output declarations exceed their bound"
        )
    try:
        result = [
            WorkflowAnalysisOutput.model_validate(
                item.model_dump(mode="json")
                if isinstance(item, WorkflowAnalysisOutput)
                else item
            )
            for item in values
        ]
    except (ValidationError, TypeError, ValueError) as error:
        raise WorkflowContractError(
            "Invalid Workflow analysis output declaration"
        ) from error
    if len({item.output_id for item in result}) != len(result):
        raise WorkflowContractError("Workflow analysis output IDs must be unique")
    return result


def validate_analysis_method_inputs(
    recipe: AnalysisRecipe | dict,
    versions: Sequence[Any],
) -> list[dict[str, Any]]:
    """Require the recipe's fields in every pinned input Schema, then merge.

    Protocol/Project ownership and scientific equivalence are caller checks;
    matching scalar types and units alone do not authorize cross-Protocol reuse.
    Nullable inputs follow the saved recipe's explicit missing-value policy.
    """
    recipe = _recipe(recipe)
    if (
        not isinstance(versions, (list, tuple))
        or not 1 <= len(versions) <= MAX_WORKFLOW_NODES
    ):
        raise WorkflowContractError(
            "Workflow analysis requires explicit pinned input versions"
        )
    combined = []
    try:
        for version in versions:
            fields = schema_fields(version)
            # A union-only check could hide a referenced field missing from one
            # exact source version. Validate each separately before combining.
            validate_recipe(recipe, fields)
            combined.extend(fields)
        catalog = validate_recipe(recipe, combined)
    except (AnalysisError, AttributeError, TypeError, ValueError) as error:
        raise WorkflowContractError(
            "Workflow analysis input Schemas are missing or incompatible"
        ) from error
    return [catalog[key] for key in sorted(catalog)]


def _validated_catalog(recipe: AnalysisRecipe, fields: list[dict]) -> dict[str, dict]:
    try:
        return validate_recipe(recipe, fields)
    except (AnalysisError, TypeError, ValueError) as error:
        raise WorkflowContractError(
            "Workflow analysis fields do not match the pinned recipe"
        ) from error


def _check_output_group(
    output: WorkflowAnalysisOutput, recipe: AnalysisRecipe, fields: Mapping[str, dict]
) -> None:
    if set(output.group) != set(recipe.group_by):
        raise WorkflowContractError(
            "Analysis output must declare the complete exact group key"
        )
    for field, value in output.group.items():
        spec = fields[field]
        if value is not None and (
            not _matches_scalar_type(value, spec["type"])
            or "enum" in spec
            and value not in spec["enum"]
        ):
            raise WorkflowContractError(
                "Analysis output group value does not match the pinned Schema"
            )


def analysis_output_catalog(
    recipe: AnalysisRecipe | dict,
    fields: list[dict[str, Any]],
    outputs: Sequence[WorkflowAnalysisOutput | dict],
) -> dict[tuple[str, str], WorkflowFieldSpec]:
    """Describe stable named ports, never a runtime group's array index."""
    recipe = _recipe(recipe)
    fields_by_key = _validated_catalog(recipe, fields)
    result = {}
    for output in _outputs(outputs):
        if output.field not in recipe.numeric_fields:
            raise WorkflowContractError(
                "Analysis outputs require a recipe-selected numeric field"
            )
        _check_output_group(output, recipe, fields_by_key)
        source = fields_by_key[output.field]
        is_count = output.statistic in _COUNTS
        result[("analysis", output.output_id)] = WorkflowFieldSpec(
            value_type="integer"
            if is_count
            else source["type"]
            if output.statistic in _PRESERVE_NUMERIC_TYPE
            else "number",
            nullable=not is_count,
            unit=None if is_count else source["unit"] or None,
        )
    return result


def _exact_group_key(
    group: Any, recipe: AnalysisRecipe, fields: Mapping[str, dict]
) -> dict[str, Any]:
    if type(group) is not dict or type(group.get("key")) is not list:
        raise WorkflowContractError("Analysis result has an invalid group key")
    key = {}
    for entry in group["key"]:
        if type(entry) is not dict or set(entry) != {"field", "type", "value"}:
            raise WorkflowContractError(
                "Analysis result has an invalid typed group key"
            )
        name = entry["field"]
        if not isinstance(name, str) or name not in recipe.group_by or name in key:
            raise WorkflowContractError(
                "Analysis result group fields are missing or duplicated"
            )
        field = fields[name]
        value = entry["value"]
        if (
            entry["type"] != field["type"]
            or value is not None
            and (
                not _matches_scalar_type(value, field["type"])
                or "enum" in field
                and value not in field["enum"]
            )
        ):
            raise WorkflowContractError(
                "Analysis result group type does not match its Schema"
            )
        key[name] = value
    if set(key) != set(recipe.group_by):
        raise WorkflowContractError(
            "Analysis result requires a complete typed group key"
        )
    return key


def project_analysis_outputs(
    recipe: AnalysisRecipe | dict,
    result: dict[str, Any],
    outputs: Sequence[WorkflowAnalysisOutput | dict],
    catalog: WorkflowFieldCatalog,
) -> dict[str, dict[str, Any]]:
    """Project a verified builtin report into declared nullable scalar ports.

    Caller must first verify the persisted result/source/publication digests.
    Null is retained as evidence, not replaced with zero: downstream predicates
    and bindings reject it. No declaration means an ordinary report-only node.
    """
    recipe = _recipe(recipe)
    outputs = _outputs(outputs)
    if type(result) is not dict or result.get("engine_version") != ENGINE_VERSION:
        raise WorkflowContractError(
            "Workflow analysis result uses an unsupported engine"
        )
    if (
        type(result.get("fields")) is not list
        or type(result.get("group_by")) is not list
    ):
        raise WorkflowContractError(
            "Workflow analysis result is missing its field contracts"
        )
    # Report fields cover numeric/grouping outputs, not filters used only during
    # selection. Validate this view against a filter-free projection recipe.
    projection_recipe = recipe.model_copy(update={"filters": []})
    result_fields = result["fields"] + result["group_by"]
    expected = analysis_output_catalog(projection_recipe, result_fields, outputs)
    if dict(catalog) != expected:
        raise WorkflowContractError(
            "Workflow analysis result output types or units changed"
        )
    fields = _validated_catalog(projection_recipe, result_fields)
    groups = result.get("groups")
    if type(groups) is not list or len(groups) > MAX_GROUPS:
        raise WorkflowContractError(
            "Workflow analysis result groups exceed their bound"
        )
    # Validate all group keys, not only the chosen first match. A malformed or
    # repeated group can never become an arbitrary deterministic-looking choice.
    keyed_groups = [
        (_exact_group_key(group, recipe, fields), group) for group in groups
    ]
    identities = [
        tuple((field, key[field]) for field in recipe.group_by)
        for key, _group in keyed_groups
    ]
    if len(identities) != len(set(identities)):
        raise WorkflowContractError(
            "Analysis result contains duplicate exact group keys"
        )
    result_values = {}
    for output in outputs:
        selected = [group for key, group in keyed_groups if key == output.group]
        if len(selected) != 1:
            raise WorkflowContractError(
                "Analysis output requires exactly one explicitly selected group"
            )
        group_fields = selected[0].get("fields")
        statistics = (
            group_fields.get(output.field) if type(group_fields) is dict else None
        )
        if type(statistics) is not dict or output.statistic not in statistics:
            raise WorkflowContractError(
                "Analysis result is missing a declared statistic"
            )
        value = statistics[output.statistic]
        spec = expected[("analysis", output.output_id)]
        if value is None:
            if not spec.nullable:
                raise WorkflowContractError("Analysis count outputs cannot be null")
        elif (
            not _matches_scalar_type(value, spec.value_type)
            or output.statistic in _COUNTS
            and value < 0
        ):
            raise WorkflowContractError(
                "Analysis result statistic has a conflicting scalar type"
            )
        result_values[output.output_id] = value
    _bounded_json(result_values, MAX_GRAPH_BYTES)
    return {"analysis": result_values}
