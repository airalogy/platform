"""Finite Project analysis: independent evidence or an explicitly typed 1:1 join.

Authorization and source capture belong to the caller. This module never fetches
Records, guesses relations, executes expressions, or edits scientific conclusions.
Local statistics reuse the existing single-Protocol kernel without merging its
field catalogs across Protocols. Joined statistical rows are explicitly derived
in-memory adapters; public lineage always points to real source Records.
"""

from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.analysis_engine import (
    AnalysisError,
    AnalysisRecipe,
    _filter_matches,
    _matches_field,
    canonical_digest,
    compute_analysis,
    resolve_field_catalog,
    validate_recipe,
)
from app.services.analysis_schema import schema_fields
from app.services.workflow_data import protocol_field_catalog

ENGINE_VERSION = "airalogy.project-analysis.v1"
SNAPSHOT_SCHEMA = "airalogy.project-snapshot.v1"
RESULT_SCHEMA = "airalogy.project-result.v1"
MAX_PROJECT_RECORDS = 5_000
MAX_PROJECT_SNAPSHOT_BYTES = 32 * 1024 * 1024
MAX_PROJECT_RESULT_BYTES = 32 * 1024 * 1024


class ProjectAnalysisError(AnalysisError):
    """Displayable counts, never potentially restricted raw key values."""

    def __init__(self, message: str, *, code="invalid_project_analysis", audit=None):
        super().__init__(message)
        self.code = code
        self.audit = deepcopy(audit) if audit is not None else None


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProjectAnalysisSlot(Contract):
    slot_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    label: str = Field(min_length=1, max_length=255)
    recipe: AnalysisRecipe

    @field_validator("label")
    @classmethod
    def meaningful_label(cls, value):
        if not value.strip():
            raise ValueError("Project source labels must not be blank")
        return value


class ProjectJoinKey(Contract):
    left_field: str = Field(min_length=1, max_length=255)
    right_field: str = Field(min_length=1, max_length=255)


class ProjectJoinOutput(Contract):
    output_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    slot_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    field: str = Field(min_length=1, max_length=255)
    semantic_label: str = Field(min_length=1, max_length=255)
    unit: str | None = Field(max_length=255)

    @field_validator("semantic_label", "field")
    @classmethod
    def meaningful_text(cls, value):
        if not value.strip():
            raise ValueError("Join field names and meanings must not be blank")
        return value


class ProjectJoinPlan(Contract):
    left_slot_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    right_slot_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    kind: Literal["inner", "left"]
    cardinality: Literal["one_to_one"] = "one_to_one"
    keys: list[ProjectJoinKey] = Field(min_length=1, max_length=4)
    missing_key_policy: Literal["error", "exclude"] = "error"
    duplicate_key_policy: Literal["error"] = "error"
    semantic_alignment_confirmed: Literal[True]
    outputs: list[ProjectJoinOutput] = Field(min_length=1, max_length=32)
    recipe: AnalysisRecipe

    @field_validator("semantic_alignment_confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Explicit field meaning confirmation is required")
        return value

    @model_validator(mode="after")
    def exact_plan(self):
        if self.left_slot_id == self.right_slot_id:
            raise ValueError("Join requires two different source slots")
        if any(
            len({getattr(key, name) for key in self.keys}) != len(self.keys)
            for name in ("left_field", "right_field")
        ):
            raise ValueError("Join key fields cannot be repeated")
        if len({item.output_id for item in self.outputs}) != len(self.outputs):
            raise ValueError("Join output identifiers must be unique")
        if any(
            item.slot_id not in {self.left_slot_id, self.right_slot_id}
            for item in self.outputs
        ):
            raise ValueError("Join outputs must name a declared source slot")
        return self


class ProjectAnalysisRecipe(Contract):
    kind: Literal["project"] = "project"
    schema_version: Literal[1] = 1
    mode: Literal["evidence_synthesis", "relational"]
    slots: list[ProjectAnalysisSlot] = Field(min_length=2, max_length=8)
    join: ProjectJoinPlan | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Project analysis schema_version must be integer 1")
        return value

    @model_validator(mode="after")
    def distinct_modes(self):
        slots = {item.slot_id for item in self.slots}
        if len(slots) != len(self.slots):
            raise ValueError("Project source slot identifiers must be unique")
        if self.mode == "evidence_synthesis" and self.join is not None:
            raise ValueError("Evidence synthesis cannot silently join samples")
        if self.mode == "relational" and (
            self.join is None
            or len(self.slots) != 2
            or {self.join.left_slot_id, self.join.right_slot_id} != slots
        ):
            raise ValueError(
                "Relational v1 requires exactly two explicitly joined source slots"
            )
        return self


def _bounded_json(value, limit, label):
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise ProjectAnalysisError(f"{label} must contain finite JSON values") from exc
    if len(payload) > limit:
        raise ProjectAnalysisError(
            f"{label} exceeds the supported byte limit", code="size_limit"
        )


def _sources(recipe, snapshot):
    if not isinstance(recipe, ProjectAnalysisRecipe):
        raise ProjectAnalysisError("Project analysis requires a validated recipe")
    if not isinstance(snapshot, dict) or snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise ProjectAnalysisError(
            "Project analysis requires its versioned source envelope"
        )
    _bounded_json(snapshot, MAX_PROJECT_SNAPSHOT_BYTES, "Project snapshot")
    try:
        UUID(snapshot["project_id"])
        items = snapshot["inputs"]
        if not isinstance(items, list) or not 2 <= len(items) <= 8:
            raise ValueError()
        sources = {item["slot_id"]: item["snapshot"] for item in items}
        if len(sources) != len(items) or set(sources) != {
            slot.slot_id for slot in recipe.slots
        }:
            raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ProjectAnalysisError(
            "Source slots must match the recipe exactly"
        ) from exc
    protocols, identities, total = set(), set(), 0
    for source in sources.values():
        try:
            protocol_id = UUID(source["protocol_id"])
            if (
                protocol_id in protocols
                or type(source.get("schema_version")) is not int
                or source["schema_version"] != 1
            ):
                raise ValueError()
            protocols.add(protocol_id)
            records = source["records"]
            if not isinstance(records, list) or not records:
                raise ValueError()
            total += len(records)
            for record in records:
                identity = (UUID(record["record_id"]), record["record_version"])
                if (
                    type(identity[1]) is not int
                    or identity[1] < 1
                    or identity[0] in identities
                ):
                    raise ValueError()
                # Match AnalysisSelection: one exact revision per Record, not
                # multiple historical versions masquerading as extra samples.
                identities.add(identity[0])
                if (
                    not isinstance(record["record_hash"], str)
                    or not record["record_hash"]
                    or not isinstance(record["data"], dict)
                    or not isinstance(record["data"].get("var", {}), dict)
                ):
                    raise ValueError()
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ProjectAnalysisError(
                "Project sources require distinct Protocols and exact, unique Record revisions"
            ) from exc
    if total > MAX_PROJECT_RECORDS:
        raise ProjectAnalysisError(
            "Project analysis cannot exceed 5000 total Records", code="record_limit"
        )
    return sources


def _referenced(recipe):
    return set(recipe.numeric_fields + recipe.group_by) | {
        item.field for item in recipe.filters
    }


def _schema_catalogs(source):
    """Resolve each pinned Schema once, including its non-scalar annotations."""
    try:
        schemas = source["schemas"]
        if (
            not isinstance(schemas, list)
            or not schemas
            or len({item["version"] for item in schemas}) != len(schemas)
            or len({item["id"] for item in schemas}) != len(schemas)
            or (
                "records" in source
                and {item["version"] for item in schemas}
                != {record["protocol_version"] for record in source["records"]}
            )
        ):
            raise ValueError()
        fields, supported = [], []
        for item in schemas:
            UUID(item["id"])
            version = SimpleNamespace(
                version=item["version"], json_schema=item["json_schema"]
            )
            fields.extend(schema_fields(version))
            supported.append(protocol_field_catalog(version))
        # Catalog order is presentational: JSON object property order is not a
        # schema identity and cannot make an otherwise exact saved method stale.
        if sorted(map(canonical_digest, fields)) != sorted(
            map(canonical_digest, source["fields"])
        ):
            raise ProjectAnalysisError(
                "Analysis field catalog differs from its pinned Schemas",
                code="schema_changed",
            )
        return fields, supported
    except ProjectAnalysisError:
        raise
    except (AnalysisError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ProjectAnalysisError(
            "Referenced fields have missing or incompatible Protocol Schemas",
            code="schema_incompatible",
        ) from exc


def project_source_fields(snapshot):
    """Display the actual intersection of supported fields, not guessed strings.

    Accept one Protocol snapshot. Its ``records`` may be omitted for a latest-
    Schema discovery response; execution still requires exact captured Records.
    FileId, complex, absent or incompatible fields stay visible but unselectable.
    """
    fields, supported = _schema_catalogs(snapshot)
    grouped = {}
    for field in fields:
        grouped.setdefault(field["key"], []).append(field)
    result = []
    for key, definitions in grouped.items():
        try:
            if any(("var", key) not in catalog for catalog in supported):
                raise AnalysisError(
                    "Field must be a supported non-file scalar in every selected Protocol Schema"
                )
            result.append(resolve_field_catalog(definitions, {key})[key])
        except AnalysisError as exc:
            result.append(
                {
                    "key": key,
                    "title": definitions[0].get("title", key),
                    "type": "unsupported",
                    "unit": None,
                    "unsupported_reason": str(exc),
                }
            )
    return result


def _catalog(source, referenced):
    """Validate every referenced field in every exact Schema, with no flattening."""
    fields, supported = _schema_catalogs(source)
    if any(
        ("var", field) not in catalog for catalog in supported for field in referenced
    ):
        raise ProjectAnalysisError(
            "Every referenced field must be a supported scalar in every pinned Schema",
            code="unsupported_field",
        )
    try:
        return resolve_field_catalog(fields, referenced)
    except AnalysisError as exc:
        raise ProjectAnalysisError(
            "Referenced fields have missing or incompatible Protocol Schemas",
            code="schema_incompatible",
        ) from exc


def validate_project_input_schemas(recipe, sources):
    """Validate explicit slot Schemas without inventing execution Records.

    Each source contains the ordinary ``schemas`` and derived ``fields`` catalog.
    Execution still calls ``_sources`` first to enforce real, nonempty inputs.
    Neither matching fields nor this pure check establishes source authorization.
    """
    recipe = ProjectAnalysisRecipe.model_validate(
        recipe.model_dump(mode="json")
        if isinstance(recipe, ProjectAnalysisRecipe)
        else recipe
    )
    if type(sources) is not dict or set(sources) != {
        slot.slot_id for slot in recipe.slots
    }:
        raise ProjectAnalysisError("Source slots must match the recipe exactly")
    references = {slot.slot_id: _referenced(slot.recipe) for slot in recipe.slots}
    if recipe.join:
        plan = recipe.join
        references[plan.left_slot_id].update(key.left_field for key in plan.keys)
        references[plan.right_slot_id].update(key.right_field for key in plan.keys)
        for item in plan.outputs:
            references[item.slot_id].add(item.field)
    catalogs = {
        slot_id: _catalog(source, references[slot_id])
        for slot_id, source in sources.items()
    }
    for slot in recipe.slots:
        validate_recipe(slot.recipe, sources[slot.slot_id]["fields"])
    outputs = []
    if recipe.join:
        plan = recipe.join
        for key in plan.keys:
            left, right = (
                catalogs[plan.left_slot_id][key.left_field],
                catalogs[plan.right_slot_id][key.right_field],
            )
            if left["type"] != right["type"] or left["unit"] != right["unit"]:
                raise ProjectAnalysisError(
                    "Join keys require matching Schema types and units; conversion is not implicit",
                    code="join_key_contract",
                )
        for item in plan.outputs:
            field = catalogs[item.slot_id][item.field]
            if (item.unit or "") != field["unit"]:
                raise ProjectAnalysisError(
                    "Output units must match the pinned source; explicit unit conversion is not implemented",
                    code="unit_conversion_required",
                )
            output = {**item.model_dump(mode="json"), "type": field["type"]}
            if "enum" in field:
                output["enum"] = deepcopy(field["enum"])
            outputs.append(output)
        validate_recipe(plan.recipe, _output_fields(outputs))
    return catalogs, outputs


def _contracts(recipe, snapshot):
    sources = _sources(recipe, snapshot)
    catalogs, outputs = validate_project_input_schemas(recipe, sources)
    return sources, catalogs, outputs


def validate_project_recipe(recipe, snapshot):
    """Validate static source, field, relation and interpretation contracts."""
    _contracts(recipe, snapshot)


def _output_fields(outputs):
    return [
        {
            "key": item["output_id"],
            "title": item["semantic_label"],
            "type": item["type"],
            "unit": item["unit"],
            **({"enum": item["enum"]} if "enum" in item else {}),
        }
        for item in outputs
    ]


def _record_ref(source, record):
    schema = next(
        item
        for item in source["schemas"]
        if item["version"] == record["protocol_version"]
    )
    return {
        "protocol_id": source["protocol_id"],
        "record_id": record["record_id"],
        "record_version": record["record_version"],
        "record_hash": record["record_hash"],
        "protocol_version": record["protocol_version"],
        "protocol_version_id": schema["id"],
    }


def _filtered(source, slot, catalog):
    rows = []
    for record in source["records"]:
        if all(
            _filter_matches(record["data"].get("var", {}), item, catalog)[0]
            for item in slot.recipe.filters
        ):
            rows.append(record)
    return sorted(rows, key=lambda row: (row["record_id"], row["record_version"]))


def _index(rows, fields, catalog):
    index, missing, invalid = {}, [], []
    for row in rows:
        values = row["data"].get("var", {})
        if any(values.get(field) is None for field in fields):
            missing.append(row)
            continue
        if any(
            not _matches_field(values[field], catalog[field])
            or (isinstance(values[field], str) and len(values[field]) > 2000)
            for field in fields
        ):
            invalid.append(row)
            continue
        parts = []
        for field in fields:
            value, kind = values[field], catalog[field]["type"]
            if kind == "number" and type(value) is float and value.is_integer():
                value = int(value)
            parts.append({"type": kind, "value": value})
        key = json.dumps(parts, ensure_ascii=False, sort_keys=True, allow_nan=False)
        index.setdefault(key, []).append(row)
    return index, missing, invalid


def _join(recipe, sources, catalogs, outputs):
    plan = recipe.join
    slots = {slot.slot_id: slot for slot in recipe.slots}
    side_ids = {"left": plan.left_slot_id, "right": plan.right_slot_id}
    indexes, audit = {}, {}
    for side, slot_id in side_ids.items():
        source = sources[slot_id]
        candidates = _filtered(source, slots[slot_id], catalogs[slot_id])
        fields = [getattr(key, f"{side}_field") for key in plan.keys]
        index, missing, invalid = _index(candidates, fields, catalogs[slot_id])
        indexes[side] = index
        duplicates = [rows for rows in index.values() if len(rows) > 1]
        audit[side] = {
            "slot_id": slot_id,
            "total": len(source["records"]),
            "filtered_out": len(source["records"]) - len(candidates),
            "key_missing": len(missing),
            "invalid_keys": len(invalid),
            "excluded": len(source["records"])
            - len(candidates)
            + len(missing)
            + len(invalid),
            "duplicate_keys": len(duplicates),
            "duplicate_rows": sum(len(rows) for rows in duplicates),
            "matched": 0,
            "unmatched": 0,
        }
    common = indexes["left"].keys() & indexes["right"].keys()
    for side in side_ids:
        audit[side]["matched"] = sum(len(indexes[side][key]) for key in common)
        audit[side]["unmatched"] = sum(
            len(rows) for key, rows in indexes[side].items() if key not in common
        )
    audit["output_rows"] = 0
    if any(audit[side]["invalid_keys"] for side in side_ids):
        raise ProjectAnalysisError(
            "Join keys contain values that do not match their pinned types",
            code="invalid_join_keys",
            audit=audit,
        )
    if any(audit[side]["duplicate_keys"] for side in side_ids):
        raise ProjectAnalysisError(
            "One-to-one join requires unique keys; aggregate repeats explicitly before joining",
            code="duplicate_join_keys",
            audit=audit,
        )
    if plan.missing_key_policy == "error" and any(
        audit[side]["key_missing"] for side in side_ids
    ):
        raise ProjectAnalysisError(
            "Join keys are missing; explicitly choose exclusion or correct the source data",
            code="missing_join_keys",
            audit=audit,
        )
    rows = []
    invalid_outputs = {}
    for key in sorted(indexes["left"]):
        if key not in indexes["right"] and plan.kind == "inner":
            continue
        left = indexes["left"][key][0]
        right = indexes["right"][key][0] if key in indexes["right"] else None
        selected = {plan.left_slot_id: left, plan.right_slot_id: right}
        refs = {
            slot_id: _record_ref(sources[slot_id], row) if row is not None else None
            for slot_id, row in selected.items()
        }
        row_id = "derived:" + canonical_digest(
            {"sources": refs, "recipe": recipe.model_dump(mode="json")}
        )
        values, lineage = {}, {}
        for output in outputs:
            record = selected[output["slot_id"]]
            values[output["output_id"]] = (
                record["data"].get("var", {}).get(output["field"])
                if record is not None
                else None
            )
            value = values[output["output_id"]]
            if value is not None and not _matches_field(
                value, catalogs[output["slot_id"]][output["field"]]
            ):
                invalid_outputs[output["output_id"]] = (
                    invalid_outputs.get(output["output_id"], 0) + 1
                )
            ref = refs[output["slot_id"]]
            lineage[output["output_id"]] = (
                {**ref, "field_path": ["var", output["field"]]}
                if ref is not None
                else None
            )
        rows.append(
            {
                "row_id": row_id,
                "values": values,
                "sources": refs,
                "field_lineage": lineage,
            }
        )
    audit["output_rows"] = len(rows)
    if invalid_outputs:
        audit["invalid_output_values"] = invalid_outputs
        raise ProjectAnalysisError(
            "Joined output values do not match their declared scalar fields",
            code="invalid_join_outputs",
            audit=audit,
        )
    if len(rows) > MAX_PROJECT_RECORDS:
        raise ProjectAnalysisError(
            "Join row expansion exceeds the supported limit",
            code="join_expansion",
            audit=audit,
        )
    # This private adapter is never a persisted Record or public Record reference.
    # The kernel accepts opaque IDs, while all public identities remain in rows.
    derived = [
        {
            "record_id": row["row_id"],
            "record_version": 1,
            "protocol_version": ENGINE_VERSION,
            "data": {"var": row["values"]},
        }
        for row in rows
    ]
    report = compute_analysis(plan.recipe, derived, _output_fields(outputs))
    return {"audit": audit, "fields": outputs, "rows": rows, "report": report}


def compute_project_analysis(recipe, snapshot):
    sources, catalogs, outputs = _contracts(recipe, snapshot)
    # Relation failures always carry their audit, even when local statistics
    # independently reject a missing measurement in the same source Records.
    joined = _join(recipe, sources, catalogs, outputs) if recipe.join else None
    local = []
    for slot in recipe.slots:
        source = sources[slot.slot_id]
        local.append(
            {
                "slot_id": slot.slot_id,
                "label": slot.label,
                "source_digest": canonical_digest(source),
                "recipe_digest": canonical_digest(slot.recipe.model_dump(mode="json")),
                "report": compute_analysis(
                    slot.recipe, source["records"], source["fields"]
                ),
            }
        )
    result = {
        "schema": RESULT_SCHEMA,
        "engine_version": ENGINE_VERSION,
        "mode": recipe.mode,
        "source_digest": canonical_digest(snapshot),
        "recipe_digest": canonical_digest(recipe.model_dump(mode="json")),
        "counts": {
            "protocols": len(sources),
            "records": sum(len(source["records"]) for source in sources.values()),
        },
        "local_results": local,
        "join": joined,
        "warnings": [{"code": "separate_evidence_not_pooled"}]
        if recipe.mode == "evidence_synthesis"
        else [{"code": "association_not_causation"}],
    }
    _bounded_json(result, MAX_PROJECT_RESULT_BYTES, "Project analysis result")
    canonical_digest(result)
    return result


def preview_project_analysis(recipe, snapshot):
    """Use the identical finite algorithm so preview audits cannot drift."""
    return compute_project_analysis(recipe, snapshot)
