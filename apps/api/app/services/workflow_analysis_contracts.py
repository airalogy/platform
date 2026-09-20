"""Pure, bounded contracts for published builtin methods in Workflow v2.

The caller authorizes the Project method publication and every exact upstream
Record/Protocol revision. These helpers never select Records, infer latest data,
publish private methods or grant access. They reuse the existing deterministic
analysis engine and its Schema reader, not another scientific interpreter.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.services.analysis_engine import (
    ENGINE_VERSION,
    MAX_GROUPS,
    AnalysisError,
    AnalysisRecipe,
    canonical_digest,
    resolve_field_catalog,
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
    WorkflowProjectAnalysisOutput,
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


class _ProjectMethodVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    version: str = Field(min_length=1, max_length=255)
    schema_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    json_schema: dict
    fields: dict

    @field_validator("id")
    @classmethod
    def exact_id(cls, value):
        if str(UUID(value)) != value:
            raise ValueError("Pinned Schema IDs must be canonical UUIDs")
        return value


class _ProjectMethodSlot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    slot_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    label: str = Field(min_length=1, max_length=255)
    protocol_id: str
    versions: list[_ProjectMethodVersion] = Field(
        min_length=1, max_length=MAX_WORKFLOW_NODES
    )

    @field_validator("protocol_id")
    @classmethod
    def exact_id(cls, value):
        if str(UUID(value)) != value:
            raise ValueError("Pinned Protocol IDs must be canonical UUIDs")
        return value


class _ProjectMethodContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: int
    slots: list[_ProjectMethodSlot] = Field(min_length=2, max_length=8)

    @field_validator("schema_version")
    @classmethod
    def exact_version(cls, value):
        if value != 1:
            raise ValueError("Project method contract requires version 1")
        return value


def _project_recipe(value):
    from app.services.project_analysis_engine import ProjectAnalysisRecipe

    return ProjectAnalysisRecipe.model_validate(
        value.model_dump(mode="json")
        if isinstance(value, ProjectAnalysisRecipe)
        else value
    )


def _project_contract_inputs(recipe, project_contract, versions_by_slot=None):
    """One Schema-only validator shared by publication, graph and projection."""
    from app.services.project_analysis_engine import validate_project_input_schemas

    try:
        recipe = _project_recipe(recipe)
        contract = _ProjectMethodContract.model_validate(project_contract)
        _bounded_json(contract.model_dump(mode="json"), MAX_GRAPH_BYTES)
        expected_slots = {slot.slot_id: slot for slot in recipe.slots}
        if (
            {slot.slot_id for slot in contract.slots} != set(expected_slots)
            or len(contract.slots) != len(expected_slots)
            or len({slot.protocol_id for slot in contract.slots}) != len(contract.slots)
            or sum(len(slot.versions) for slot in contract.slots) > MAX_WORKFLOW_NODES
        ):
            raise ValueError("Published Project input slots are missing or duplicated")
        if versions_by_slot is not None and (
            not isinstance(versions_by_slot, Mapping)
            or set(versions_by_slot) != set(expected_slots)
        ):
            raise ValueError("Actual Project source slots must match the method")
        sources = {}
        version_ids = set()
        actual_count = 0
        for slot in contract.slots:
            if slot.label != expected_slots[slot.slot_id].label:
                raise ValueError("Published Project source label changed")
            allowed = {}
            version_names = set()
            for version in slot.versions:
                if version.id in version_ids or version.version in version_names:
                    raise ValueError("Published Project input versions must be unique")
                version_ids.add(version.id)
                version_names.add(version.version)
                payload = {
                    **version.model_dump(exclude={"schema_digest"}),
                    "protocol_id": slot.protocol_id,
                }
                if canonical_digest(payload) != version.schema_digest:
                    raise ValueError("Published Project input Schema digest changed")
                allowed[version.id] = version.schema_digest
            if versions_by_slot is not None:
                actual = versions_by_slot[slot.slot_id]
                if not isinstance(actual, (list, tuple)) or not actual:
                    raise ValueError(
                        "Every Project input slot requires explicit versions"
                    )
                actual_count += len(actual)
                if actual_count > MAX_WORKFLOW_NODES:
                    raise ValueError("Actual Project inputs exceed the node limit")
                for version in actual:
                    payload = {
                        "id": str(version.id),
                        "protocol_id": str(version.protocol_id),
                        "version": version.version,
                        "json_schema": version.json_schema,
                        "fields": version.fields,
                    }
                    if payload["protocol_id"] != slot.protocol_id or allowed.get(
                        payload["id"]
                    ) != canonical_digest(payload):
                        raise ValueError(
                            "Actual Project Schema is not a pinned input version"
                        )
            schemas = [
                version.model_dump(exclude={"schema_digest"})
                for version in slot.versions
            ]
            sources[slot.slot_id] = {
                "schemas": schemas,
                "fields": [
                    field
                    for version in schemas
                    for field in schema_fields(SimpleNamespace(**version))
                ],
            }
        catalogs, joined = validate_project_input_schemas(recipe, sources)
        fields = {
            slot: [catalog[key] for key in sorted(catalog)]
            for slot, catalog in catalogs.items()
        }
        return recipe, fields, joined
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise WorkflowContractError(str(error)) from error


def validate_project_method_inputs(recipe, project_contract, versions_by_slot=None):
    """Validate all allowed Schemas, and optionally exact actual node versions.

    Repeated nodes may use the same pinned version in one slot. They never imply
    repeated source slots or permission to choose different Protocols/versions.
    """
    return _project_contract_inputs(recipe, project_contract, versions_by_slot)[1]


def _project_outputs(values):
    if not isinstance(values, (list, tuple)) or len(values) > MAX_ANALYSIS_OUTPUTS:
        raise WorkflowContractError(
            "Project analysis output declarations exceed their bound"
        )
    try:
        result = [
            WorkflowProjectAnalysisOutput.model_validate(
                item.model_dump(mode="json")
                if isinstance(item, WorkflowProjectAnalysisOutput)
                else item
            )
            for item in values
        ]
    except (ValueError, TypeError) as error:
        raise WorkflowContractError(
            "Invalid Project analysis output declaration"
        ) from error
    if len({item.output_id for item in result}) != len(result):
        raise WorkflowContractError("Project analysis output IDs must be unique")
    return result


def _project_report_contracts(recipe, fields, joined):
    result = {
        ("local", slot.slot_id): (slot.recipe, fields[slot.slot_id])
        for slot in recipe.slots
    }
    if recipe.join:
        from app.services.project_analysis_engine import _output_fields

        result[("join", None)] = (recipe.join.recipe, _output_fields(joined))
    return result


def _project_output_selection(output):
    source = output.source
    return (source.kind, getattr(source, "slot_id", None))


def _plain_project_output(output):
    return WorkflowAnalysisOutput.model_validate(
        output.model_dump(mode="json", exclude={"source"})
    )


def project_method_output_catalog(recipe, project_contract, outputs):
    """Describe named local/Join ports with the ordinary scalar output rules."""
    recipe, fields, joined = _project_contract_inputs(recipe, project_contract)
    reports = _project_report_contracts(recipe, fields, joined)
    catalog = {}
    for output in _project_outputs(outputs):
        selection = reports.get(_project_output_selection(output))
        if selection is None:
            raise WorkflowContractError(
                "Project output must select a declared local slot or Join"
            )
        selected_recipe, selected_fields = selection
        catalog.update(
            analysis_output_catalog(
                selected_recipe, selected_fields, [_plain_project_output(output)]
            )
        )
    return catalog


def project_workflow_outputs(recipe, project_contract, result, outputs, catalog):
    """Project sealed reports by slot identity, never a report or group index.

    The caller verifies source/result/publication seals and current source ACLs.
    This validates every local report contract, even unselected report-only slots.
    """
    from app.services.project_analysis_engine import (
        ENGINE_VERSION as PROJECT_ENGINE_VERSION,
    )
    from app.services.project_analysis_engine import RESULT_SCHEMA

    recipe, fields, joined = _project_contract_inputs(recipe, project_contract)
    outputs = _project_outputs(outputs)
    expected = project_method_output_catalog(recipe, project_contract, outputs)
    if dict(catalog) != expected:
        raise WorkflowContractError("Project analysis output catalog changed")
    if (
        type(result) is not dict
        or result.get("schema") != RESULT_SCHEMA
        or result.get("engine_version") != PROJECT_ENGINE_VERSION
        or result.get("mode") != recipe.mode
        or result.get("recipe_digest")
        != canonical_digest(recipe.model_dump(mode="json"))
        or type(result.get("local_results")) is not list
        or len(result["local_results"]) != len(recipe.slots)
    ):
        raise WorkflowContractError("Project analysis result contract changed")
    report_contracts = _project_report_contracts(recipe, fields, joined)
    reports = {}
    for item in result["local_results"]:
        if type(item) is not dict or type(item.get("slot_id")) is not str:
            raise WorkflowContractError(
                "Project result requires explicit local slot identities"
            )
        key = ("local", item["slot_id"])
        if key not in report_contracts or key in reports:
            raise WorkflowContractError(
                "Project result local slots are missing or duplicated"
            )
        if item.get("recipe_digest") != canonical_digest(
            report_contracts[key][0].model_dump(mode="json")
        ):
            raise WorkflowContractError("Project local result recipe changed")
        reports[key] = item.get("report")
    if recipe.join:
        actual_join = result.get("join")
        if type(actual_join) is not dict or actual_join.get("fields") != joined:
            raise WorkflowContractError("Project Join result field contract changed")
        reports[("join", None)] = actual_join.get("report")
    elif result.get("join") is not None:
        raise WorkflowContractError(
            "Independent Project evidence cannot contain a Join"
        )
    values = {}
    for key, (selected_recipe, selected_fields) in report_contracts.items():
        report = reports[key]
        if type(report) is not dict:
            raise WorkflowContractError("Project result report is missing")
        # A count-only port still cannot conceal a changed field type or unit.
        for name, keys in (
            ("fields", selected_recipe.numeric_fields),
            ("group_by", selected_recipe.group_by),
        ):
            entries = report.get(name)
            if (
                type(entries) is not list
                or any(
                    type(entry) is not dict or type(entry.get("key")) is not str
                    for entry in entries
                )
                or len(entries) != len(keys)
                or {entry["key"] for entry in entries} != set(keys)
            ):
                raise WorkflowContractError("Project result selected fields changed")
        try:
            resolve_field_catalog(
                [*selected_fields, *report["fields"], *report["group_by"]],
                set(selected_recipe.numeric_fields + selected_recipe.group_by),
            )
        except AnalysisError as error:
            raise WorkflowContractError(
                "Project result fields or units changed"
            ) from error
        selected_outputs = [
            _plain_project_output(output)
            for output in outputs
            if _project_output_selection(output) == key
        ]
        selected_catalog = {
            ("analysis", output.output_id): expected[("analysis", output.output_id)]
            for output in selected_outputs
        }
        values.update(
            project_analysis_outputs(
                selected_recipe, report, selected_outputs, selected_catalog
            )["analysis"]
        )
    _bounded_json(values, MAX_GRAPH_BYTES)
    return {"analysis": values}
