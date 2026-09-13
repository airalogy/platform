"""Bounded, deterministic analysis of explicitly authorized Record snapshots.

The caller owns authorization and immutable source capture. This module accepts
only a typed recipe: field names are literal ``data.var`` keys, never paths or
expressions. AI may propose the recipe but cannot supply executable operators.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ENGINE_VERSION = "airalogy.analysis.v1"
MAX_RECORDS = 5_000
MAX_GROUPS = 200
MAX_FILTER_VALUES = 100

Scalar = (
    Annotated[str, Field(max_length=2_000)]
    | bool
    | int
    | Annotated[float, Field(allow_inf_nan=False)]
)
FilterOperator = Literal[
    "eq", "ne", "gt", "gte", "lt", "lte", "in", "missing", "present"
]


class AnalysisError(ValueError):
    """The recipe, source data or result exceeds the supported contract."""


def canonical_digest(value: Any) -> str:
    """Hash JSON values without accepting non-finite numbers or custom objects."""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _field_name(value: str) -> str:
    if not value.strip() or len(value) > 255:
        raise ValueError("Analysis field names must contain 1 to 255 characters")
    return value


class AnalysisFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    field: str = Field(min_length=1, max_length=255)
    op: FilterOperator
    value: Scalar | list[Scalar] | None = None

    @field_validator("field")
    @classmethod
    def validate_field(cls, value: str) -> str:
        return _field_name(value)

    @model_validator(mode="after")
    def validate_operand(self):
        if self.op in {"missing", "present"}:
            if self.value is not None:
                raise ValueError("Missing/present filters do not accept a value")
        elif self.op == "in":
            if not isinstance(self.value, list) or not (
                1 <= len(self.value) <= MAX_FILTER_VALUES
            ):
                raise ValueError("The in filter requires 1 to 100 scalar values")
        elif self.value is None or isinstance(self.value, list):
            raise ValueError("Comparison filters require one non-null scalar value")
        return self


class AnalysisRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    numeric_fields: list[str] = Field(min_length=1, max_length=20)
    group_by: list[str] = Field(default_factory=list, max_length=3)
    filters: list[AnalysisFilter] = Field(default_factory=list, max_length=20)
    missing_policy: Literal["exclude", "error"] = "exclude"
    chart: Literal["bar", "line", "none"] = "bar"

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_schema_version(cls, value: Any) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("Analysis recipe schema_version must be integer 1")
        return value

    @field_validator("numeric_fields", "group_by")
    @classmethod
    def validate_fields(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Analysis field selections cannot contain duplicates")
        return [_field_name(value) for value in values]


def _catalog_type(value: Any) -> str:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        non_null = [item for item in value if item != "null"]
        if len(non_null) == 1 and len(value) == len(set(value)):
            value = non_null[0]
    if not isinstance(value, str) or value not in {
        "number",
        "integer",
        "string",
        "boolean",
    }:
        raise AnalysisError(
            "Referenced fields require one supported scalar Schema type"
        )
    return value


def _finite_numeric(value: Any) -> bool:
    if type(value) not in {int, float}:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _matches_type(value: Any, field_type: str) -> bool:
    if field_type == "number":
        return _finite_numeric(value)
    if field_type == "integer":
        return type(value) is int and _finite_numeric(value)
    if field_type == "boolean":
        return type(value) is bool
    return type(value) is str


def _matches_field(value: Any, field: dict[str, Any]) -> bool:
    return _matches_type(value, field["type"]) and (
        "enum" not in field or value in field["enum"]
    )


def resolve_field_catalog(
    field_catalog: list[dict[str, Any]], referenced: set[str]
) -> dict[str, dict[str, Any]]:
    """Resolve referenced literal keys and reject ambiguous types or units.

    Catalogs may contain the same key from several pinned Protocol versions.
    Every occurrence must agree; a missing unit never implies unit conversion.
    Unreferenced complex fields do not prevent analysis of scalar fields.
    """

    catalog: dict[str, dict[str, Any]] = {}
    for item in field_catalog:
        if not isinstance(item, dict):
            raise AnalysisError("Analysis field catalog entries must be objects")
        key = item.get("key")
        if not isinstance(key, str) or key not in referenced:
            continue
        field_type = _catalog_type(item.get("type"))
        unit = item.get("unit")
        if unit is not None and not isinstance(unit, str):
            raise AnalysisError("Analysis field units must be strings")
        unit = unit.strip() if unit else ""
        enum = item.get("enum")
        if enum is not None:
            if (
                not isinstance(enum, list)
                or not enum
                or any(
                    value is not None and not _matches_type(value, field_type)
                    for value in enum
                )
            ):
                raise AnalysisError(
                    "Analysis field enum must match its scalar Schema type"
                )
            enum = sorted(
                {
                    json.dumps(value, allow_nan=False)
                    for value in enum
                    if value is not None
                }
            )
            enum = [json.loads(value) for value in enum]
        existing = catalog.get(key)
        if existing is not None and (
            existing["type"] != field_type
            or existing["unit"] != unit
            or existing.get("enum") != enum
        ):
            raise AnalysisError(f"Field {key!r} has incompatible Schema types or units")
        if existing is None:
            title = item.get("title", key)
            catalog[key] = {
                "key": key,
                "title": title if isinstance(title, str) else key,
                "type": field_type,
                "unit": unit,
            }
            if enum is not None:
                catalog[key]["enum"] = enum
    unknown = referenced - catalog.keys()
    if unknown:
        raise AnalysisError(f"Unknown analysis fields: {', '.join(sorted(unknown))}")
    return catalog


def validate_recipe(
    recipe: AnalysisRecipe, field_catalog: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Validate selected fields and typed operators against exact input Schemas."""
    if not isinstance(recipe, AnalysisRecipe):
        raise AnalysisError("Analysis requires a validated AnalysisRecipe")
    referenced = set(recipe.numeric_fields + recipe.group_by)
    referenced.update(item.field for item in recipe.filters)
    catalog = resolve_field_catalog(field_catalog, referenced)
    for key in recipe.numeric_fields:
        if catalog[key]["type"] not in {"number", "integer"}:
            raise AnalysisError(f"Field {key!r} is not Schema-confirmed numeric")
    for item in recipe.filters:
        field_type = catalog[item.field]["type"]
        if item.op in {"missing", "present"}:
            continue
        if item.op in {"gt", "gte", "lt", "lte"} and field_type not in {
            "number",
            "integer",
        }:
            raise AnalysisError("Ordered filters require a numeric Schema field")
        operands = item.value if isinstance(item.value, list) else [item.value]
        if any(not _matches_field(value, catalog[item.field]) for value in operands):
            raise AnalysisError(f"Filter value does not match field {item.field!r}")
    return catalog


def _filter_matches(
    values: dict[str, Any], item: AnalysisFilter, catalog: dict[str, dict[str, Any]]
) -> tuple[bool, bool]:
    value = values.get(item.field)
    if item.op == "missing":
        return value is None, False
    if item.op == "present":
        return value is not None, False
    if value is None:
        return False, False
    if not _matches_field(value, catalog[item.field]):
        return False, True
    operand = item.value
    if item.op == "eq":
        return value == operand, False
    if item.op == "ne":
        return value != operand, False
    if item.op == "in":
        return value in operand, False
    if item.op == "gt":
        return value > operand, False
    if item.op == "gte":
        return value >= operand, False
    if item.op == "lt":
        return value < operand, False
    return value <= operand, False


def _statistics(
    values: list[int | float], missing: int, invalid: int
) -> dict[str, Any]:
    count = len(values)
    result: dict[str, Any] = {
        "count": count,
        "missing": missing,
        "invalid": invalid,
        "mean": None,
        "median": None,
        "min": None,
        "max": None,
        "sum": None,
        "sample_stddev": None,
    }
    if not values:
        return result
    ordered = sorted(values)
    midpoint = count // 2
    try:
        total = (
            sum(values)
            if all(type(value) is int for value in values)
            else math.fsum(values)
        )
        median = (
            ordered[midpoint]
            if count % 2
            else statistics.mean(ordered[midpoint - 1 : midpoint + 1])
        )
        result.update(
            mean=statistics.mean(values),
            median=median,
            min=ordered[0],
            max=ordered[-1],
            sum=total,
            sample_stddev=statistics.stdev(values) if count > 1 else None,
        )
    except (OverflowError, ValueError) as error:
        raise AnalysisError(
            "Analysis numeric range exceeded; no result was saved"
        ) from error
    if any(
        value is not None and not _finite_numeric(value)
        for key, value in result.items()
        if key not in {"count", "missing", "invalid"}
    ):
        raise AnalysisError("Analysis numeric range exceeded; no result was saved")
    return result


def _group_order(group: dict[str, Any]) -> tuple:
    """Keep numeric chart coordinates numeric, with missing groups explicit first."""

    result = []
    for item in group["key"]:
        value = item["value"]
        if value is None:
            result.append((0, 0))
        elif item["type"] in {"number", "integer"}:
            result.append((1, value))
        elif item["type"] == "boolean":
            result.append((2, int(value)))
        else:
            result.append((3, value))
    return tuple(result)


def _prepare_analysis(
    recipe: AnalysisRecipe,
    rows: list[dict[str, Any]],
    field_catalog: list[dict[str, Any]],
) -> tuple[
    dict[str, dict[str, Any]], dict[str, dict[str, Any]], int, list[dict[str, Any]]
]:
    """Validate selection, missing data, filters and grouping without statistics.

    ``exclude`` omits missing/invalid numeric values separately for each field;
    it never removes an entire included row from the reported denominator.
    ``error`` refuses missing/invalid values in any requested numeric field.
    Filters are AND-combined. Missing values never satisfy ordinary comparisons
    (including ``ne``); use explicit ``missing``/``present`` operators instead.
    """

    catalog = validate_recipe(recipe, field_catalog)
    if not isinstance(rows, list) or len(rows) > MAX_RECORDS:
        raise AnalysisError(f"Analysis cannot exceed {MAX_RECORDS} Records")
    groups: dict[str, dict[str, Any]] = {}
    identities: set[tuple[str, int]] = set()
    included = 0
    invalid_filter_rows = 0
    warnings = Counter()
    for row in rows:
        if not isinstance(row, dict):
            raise AnalysisError("Analysis Records must be objects")
        record_id, revision = row.get("record_id"), row.get("record_version")
        if (
            not isinstance(record_id, str)
            or not record_id
            or type(revision) is not int
            or revision < 1
        ):
            raise AnalysisError(
                "Analysis requires exact Record IDs and positive revisions"
            )
        identity = (record_id, revision)
        if identity in identities:
            raise AnalysisError("Duplicate Record revisions cannot be analyzed twice")
        identities.add(identity)
        if (
            not isinstance(row.get("protocol_version"), str)
            or not row["protocol_version"]
        ):
            raise AnalysisError(
                "Analysis requires an exact Protocol version for every Record"
            )
        data = row.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("var", {}), dict):
            raise AnalysisError("Analysis Record data.var must be an object")
        values = data.get("var", {})
        matches = [_filter_matches(values, item, catalog) for item in recipe.filters]
        if not all(match for match, _invalid in matches):
            invalid_filter_rows += int(any(invalid for _match, invalid in matches))
            continue
        included += 1
        key = []
        for field in recipe.group_by:
            value = values.get(field)
            field_type = catalog[field]["type"]
            if value is not None and not _matches_field(value, catalog[field]):
                raise AnalysisError(
                    f"Grouping field {field!r} contains an invalid value"
                )
            if isinstance(value, str) and len(value) > 2_000:
                raise AnalysisError(
                    "Analysis grouping values cannot exceed 2000 characters"
                )
            # Numeric Schema values 1 and 1.0 represent the same group; booleans
            # cannot enter numeric groups and string "1" remains a string.
            if field_type == "number" and type(value) is float and value.is_integer():
                value = int(value)
            key.append({"field": field, "type": field_type, "value": value})
        group_id = json.dumps(key, ensure_ascii=False, sort_keys=True, allow_nan=False)
        if group_id not in groups:
            if len(groups) >= MAX_GROUPS:
                raise AnalysisError(f"Analysis cannot exceed {MAX_GROUPS} groups")
            groups[group_id] = {
                "key": key,
                "row_count": 0,
                "values": {field: [] for field in recipe.numeric_fields},
                "missing": Counter(),
                "invalid": Counter(),
            }
        group = groups[group_id]
        group["row_count"] += 1
        for field in recipe.numeric_fields:
            value = values.get(field)
            problem = (
                "missing"
                if value is None
                else "invalid"
                if not _matches_field(value, catalog[field])
                else None
            )
            if problem:
                if recipe.missing_policy == "error":
                    raise AnalysisError(f"Field {field!r} contains {problem} values")
                group[problem][field] += 1
                warnings[(problem, field)] += 1
            else:
                group["values"][field].append(value)
    if not groups and not recipe.group_by:
        groups["[]"] = {
            "key": [],
            "row_count": 0,
            "values": {field: [] for field in recipe.numeric_fields},
            "missing": Counter(),
            "invalid": Counter(),
        }
    output_warnings = [
        {"code": f"{problem}_values_excluded", "field": field, "count": count}
        for (problem, field), count in sorted(warnings.items())
    ]
    if invalid_filter_rows:
        output_warnings.append(
            {"code": "invalid_filter_values_excluded", "count": invalid_filter_rows}
        )
    return catalog, groups, included, output_warnings


def preview_analysis(
    recipe: AnalysisRecipe,
    rows: list[dict[str, Any]],
    field_catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate execution inputs and count exclusions, without calculating results."""

    _catalog, groups, included, warnings = _prepare_analysis(
        recipe, rows, field_catalog
    )
    return {
        "engine_version": ENGINE_VERSION,
        "counts": {
            "total": len(rows),
            "included": included,
            "filtered_out": len(rows) - included,
        },
        "fields": {
            field: {
                "count": sum(len(group["values"][field]) for group in groups.values()),
                "missing": sum(group["missing"][field] for group in groups.values()),
                "invalid": sum(group["invalid"][field] for group in groups.values()),
            }
            for field in recipe.numeric_fields
        },
        "group_count": len(groups),
        "warnings": warnings,
    }


def compute_analysis(
    recipe: AnalysisRecipe,
    rows: list[dict[str, Any]],
    field_catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute descriptive statistics and table-equivalent chart means.

    Values excluded from one field never silently change another field's sample
    size. Group and statistic ordering is independent of caller Record order.
    """

    catalog, groups, included, output_warnings = _prepare_analysis(
        recipe, rows, field_catalog
    )
    output_groups = []
    for group in sorted(groups.values(), key=_group_order):
        output_groups.append(
            {
                "key": group["key"],
                "row_count": group["row_count"],
                "fields": {
                    field: _statistics(
                        sorted(group["values"][field]),
                        group["missing"][field],
                        group["invalid"][field],
                    )
                    for field in recipe.numeric_fields
                },
            }
        )
    result = {
        "engine_version": ENGINE_VERSION,
        "counts": {
            "total": len(rows),
            "included": included,
            "filtered_out": len(rows) - included,
        },
        "fields": [catalog[field] for field in recipe.numeric_fields],
        "group_by": [catalog[field] for field in recipe.group_by],
        "groups": output_groups,
        "table": output_groups,
        "chart": {
            "type": recipe.chart,
            "statistic": "mean",
            "series": []
            if recipe.chart == "none"
            else [
                {
                    "field": field,
                    "title": catalog[field]["title"],
                    "unit": catalog[field]["unit"],
                    "points": [
                        {
                            "group_index": index,
                            "value": group["fields"][field]["mean"],
                            "count": group["fields"][field]["count"],
                        }
                        for index, group in enumerate(output_groups)
                    ],
                }
                for field in recipe.numeric_fields
            ],
        },
        "warnings": output_warnings,
    }
    canonical_digest(result)
    return result
