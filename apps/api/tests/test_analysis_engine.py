"""Offline numerical and safety contracts for the declarative analysis engine."""

from __future__ import annotations

import ast
import copy
import inspect
import json
import math

import pytest
from pydantic import ValidationError

from app.services import analysis_engine
from app.services.analysis_engine import (
    ENGINE_VERSION,
    MAX_GROUPS,
    MAX_RECORDS,
    AnalysisError,
    AnalysisFilter,
    AnalysisRecipe,
    canonical_digest,
    compute_analysis,
    preview_analysis,
    validate_recipe,
)

CATALOG = [
    {"key": "measurement", "title": "Measurement", "type": "number", "unit": "mg"},
    {"key": "secondary", "title": "Secondary", "type": "number"},
    {"key": "replicates", "type": "integer"},
    {"key": "treatment", "title": "Treatment", "type": "string"},
    {"key": "accepted", "type": "boolean"},
]


def record(index: int, values: dict, **kwargs) -> dict:
    return {
        "record_id": f"record-{index}",
        "record_version": 1,
        "protocol_version": "1.0.0",
        "data": {"var": values},
        **kwargs,
    }


def recipe(**kwargs) -> AnalysisRecipe:
    return AnalysisRecipe.model_validate({"numeric_fields": ["measurement"], **kwargs})


def stats(result: dict, field: str = "measurement") -> dict:
    return result["groups"][0]["fields"][field]


def test_known_statistics_and_table_equivalent_chart():
    rows = [
        record(index, {"measurement": value})
        for index, value in enumerate([1, 2, 3, 4])
    ]
    result = compute_analysis(recipe(), rows, CATALOG)
    assert result["engine_version"] == ENGINE_VERSION
    assert result["counts"] == {"total": 4, "included": 4, "filtered_out": 0}
    assert stats(result) == {
        "count": 4,
        "missing": 0,
        "invalid": 0,
        "mean": 2.5,
        "median": 2.5,
        "min": 1,
        "max": 4,
        "sum": 10,
        "sample_stddev": pytest.approx(math.sqrt(5 / 3)),
    }
    assert result["table"] == result["groups"]
    assert result["chart"] == {
        "type": "bar",
        "statistic": "mean",
        "series": [
            {
                "field": "measurement",
                "title": "Measurement",
                "unit": "mg",
                "points": [{"group_index": 0, "value": 2.5, "count": 4}],
            }
        ],
    }
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    "values,mean,median,stddev",
    [
        ([], None, None, None),
        ([7], 7, 7, None),
        ([1, 4, 9], 14 / 3, 4, math.sqrt(49 / 3)),
    ],
)
def test_empty_single_and_odd_samples(values, mean, median, stddev):
    result = compute_analysis(
        recipe(), [record(i, {"measurement": v}) for i, v in enumerate(values)], CATALOG
    )
    assert (
        stats(result)["mean"] == pytest.approx(mean)
        if mean is not None
        else stats(result)["mean"] is None
    )
    assert stats(result)["median"] == median
    assert (
        stats(result)["sample_stddev"] == pytest.approx(stddev)
        if stddev is not None
        else stats(result)["sample_stddev"] is None
    )
    if not values:
        assert all(
            stats(result)[key] is None
            for key in ["mean", "median", "min", "max", "sum", "sample_stddev"]
        )


def test_missing_and_invalid_values_have_separate_per_field_denominators():
    rows = [
        record(1, {"measurement": 2, "secondary": None}),
        record(2, {"measurement": None, "secondary": 10}),
        record(3, {"secondary": 20}),
        record(4, {"measurement": "4", "secondary": False}),
        record(5, {"measurement": float("nan"), "secondary": 30}),
        record(6, {"measurement": float("inf"), "secondary": 40}),
    ]
    result = compute_analysis(
        recipe(numeric_fields=["measurement", "secondary"]), rows, CATALOG
    )
    assert result["counts"]["included"] == 6
    assert {key: stats(result)[key] for key in ["count", "missing", "invalid"]} == {
        "count": 1,
        "missing": 2,
        "invalid": 3,
    }
    assert stats(result)["mean"] == 2
    assert stats(result, "secondary")["mean"] == 25
    for field in ["measurement", "secondary"]:
        assert (
            sum(stats(result, field)[key] for key in ["count", "missing", "invalid"])
            == 6
        )
    assert {item["code"] for item in result["warnings"]} == {
        "invalid_values_excluded",
        "missing_values_excluded",
    }


@pytest.mark.parametrize(
    "value", [None, True, "12", {}, [], float("nan"), float("inf"), -float("inf")]
)
def test_error_missing_policy_rejects_missing_or_invalid_numbers(value):
    with pytest.raises(AnalysisError, match="contains (missing|invalid)"):
        compute_analysis(
            recipe(missing_policy="error"), [record(1, {"measurement": value})], CATALOG
        )


def test_integer_schema_does_not_coerce_float_or_boolean():
    result = compute_analysis(
        recipe(numeric_fields=["replicates"]),
        [
            record(i, {"replicates": value})
            for i, value in enumerate([1, 2.0, True, "3"])
        ],
        CATALOG,
    )
    assert stats(result, "replicates")["count"] == 1
    assert stats(result, "replicates")["invalid"] == 3


def test_group_order_and_results_are_stable_across_source_row_order():
    rows = [
        record(1, {"measurement": 8, "treatment": "B"}),
        record(2, {"measurement": 2, "treatment": "A"}),
        record(3, {"measurement": 4, "treatment": "A"}),
    ]
    result = compute_analysis(recipe(group_by=["treatment"]), rows, CATALOG)
    assert result == compute_analysis(
        recipe(group_by=["treatment"]), list(reversed(rows)), CATALOG
    )
    assert [group["key"] for group in result["groups"]] == [
        [{"field": "treatment", "type": "string", "value": "A"}],
        [{"field": "treatment", "type": "string", "value": "B"}],
    ]
    assert [group["fields"]["measurement"]["mean"] for group in result["groups"]] == [
        3,
        8,
    ]


def test_typed_numeric_groups_merge_integral_floats_without_rounding_large_integers():
    rows = [
        record(i, {"measurement": value})
        for i, value in enumerate([1, 1.0, 9007199254740992, 9007199254740993])
    ]
    result = compute_analysis(recipe(group_by=["measurement"]), rows, CATALOG)
    assert len(result["groups"]) == 3
    assert sorted(group["row_count"] for group in result["groups"]) == [1, 1, 2]


def test_line_chart_groups_sort_numerically_not_lexicographically():
    rows = [record(i, {"measurement": value}) for i, value in enumerate([10, 2, -1])]
    result = compute_analysis(
        recipe(group_by=["measurement"], chart="line"), rows, CATALOG
    )
    assert [group["key"][0]["value"] for group in result["groups"]] == [-1, 2, 10]


def test_missing_group_is_explicit_and_boolean_groups_remain_boolean():
    rows = [
        record(1, {"measurement": 1}),
        record(2, {"measurement": 2, "accepted": True}),
        record(3, {"measurement": 3, "accepted": False}),
    ]
    result = compute_analysis(recipe(group_by=["accepted"]), rows, CATALOG)
    assert len(result["groups"]) == 3
    assert all(group["key"][0]["type"] == "boolean" for group in result["groups"])
    assert sorted(
        type(group["key"][0]["value"]).__name__ for group in result["groups"]
    ) == ["NoneType", "bool", "bool"]
    with pytest.raises(AnalysisError, match="Grouping field"):
        compute_analysis(
            recipe(group_by=["accepted"]),
            [record(1, {"measurement": 1, "accepted": 1})],
            CATALOG,
        )


@pytest.mark.parametrize(
    "op,value,expected",
    [
        ("eq", 2, 1),
        ("ne", 2, 2),
        ("gt", 2, 1),
        ("gte", 2, 2),
        ("lt", 2, 1),
        ("lte", 2, 2),
        ("in", [1, 3], 2),
        ("missing", None, 2),
        ("present", None, 4),
    ],
)
def test_typed_numeric_filter_operators(op, value, expected):
    rows = [
        record(i, {"measurement": item}) for i, item in enumerate([1, 2, 3, None, "2"])
    ] + [record(5, {})]
    result = compute_analysis(
        recipe(filters=[{"field": "measurement", "op": op, "value": value}]),
        rows,
        CATALOG,
    )
    assert result["counts"] == {
        "total": 6,
        "included": expected,
        "filtered_out": 6 - expected,
    }
    if op not in {"missing", "present"}:
        assert {"code": "invalid_filter_values_excluded", "count": 1} in result[
            "warnings"
        ]


def test_filters_combine_with_and_and_keep_exact_string_keys():
    rows = [
        record(1, {"measurement": 1, "treatment": "A", "accepted": True}),
        record(2, {"measurement": 2, "treatment": "A", "accepted": False}),
        record(3, {"measurement": 3, "treatment": "a", "accepted": True}),
    ]
    result = compute_analysis(
        recipe(
            filters=[
                {"field": "treatment", "op": "eq", "value": "A"},
                {"field": "accepted", "op": "eq", "value": True},
            ]
        ),
        rows,
        CATALOG,
    )
    assert result["counts"]["included"] == 1
    assert stats(result)["mean"] == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"numeric_fields": []},
        {"numeric_fields": ["measurement"] * 2},
        {"numeric_fields": [f"x{i}" for i in range(21)]},
        {"group_by": ["x"] * 4},
        {"group_by": ["x", "x"]},
        {"numeric_fields": [1]},
        {"numeric_fields": [" "]},
        {"numeric_fields": ["x" * 256]},
        {"schema_version": True},
        {"schema_version": "1"},
        {"schema_version": 2},
        {"code": "print(1)"},
        {"missing_policy": "impute"},
        {"chart": "script"},
        {"filters": [{"field": "measurement", "op": "eq", "value": 1}] * 21},
    ],
)
def test_recipe_is_bounded_and_strict(patch):
    with pytest.raises(ValidationError):
        recipe(**patch)


@pytest.mark.parametrize(
    "values",
    [
        {"op": "eval", "value": "print(1)"},
        {"op": "missing", "value": 1},
        {"op": "present", "value": []},
        {"op": "eq", "value": None},
        {"op": "eq", "value": [1]},
        {"op": "in", "value": 1},
        {"op": "in", "value": []},
        {"op": "in", "value": [1] * 101},
        {"op": "in", "value": [{"x": 1}]},
        {"op": "eq", "value": float("nan")},
        {"op": "eq", "value": float("inf")},
        {"op": "eq", "value": "x" * 2001},
    ],
)
def test_filter_values_are_only_bounded_scalars(values):
    with pytest.raises(ValidationError):
        AnalysisFilter(field="measurement", **values)


@pytest.mark.parametrize("filter_value", ["2", True])
def test_numeric_filter_never_coerces_operand(filter_value):
    with pytest.raises(AnalysisError, match="Filter value"):
        validate_recipe(
            recipe(
                filters=[{"field": "measurement", "op": "eq", "value": filter_value}]
            ),
            CATALOG,
        )


def test_catalog_confirms_numeric_fields_and_disallows_ordered_string_filters():
    with pytest.raises(AnalysisError, match="Schema-confirmed numeric"):
        validate_recipe(recipe(numeric_fields=["treatment"]), CATALOG)
    with pytest.raises(AnalysisError, match="Ordered filters"):
        validate_recipe(
            recipe(filters=[{"field": "treatment", "op": "gt", "value": "A"}]), CATALOG
        )
    for key in [
        "unknown",
        "data.var.measurement",
        "measurement[0]",
        "__import__('os')",
    ]:
        with pytest.raises(AnalysisError, match="Unknown analysis fields"):
            validate_recipe(recipe(numeric_fields=[key]), CATALOG)


def test_field_names_are_literal_keys_not_paths_or_expressions():
    key = "sample.measurement[0]"
    result = compute_analysis(
        recipe(numeric_fields=[key]),
        [record(1, {key: 5, "sample": {"measurement": [99]}})],
        [{"key": key, "type": "number"}],
    )
    assert stats(result, key)["mean"] == 5


@pytest.mark.parametrize(
    "replacement",
    [
        {"type": "string", "unit": "mg"},
        {"type": "integer", "unit": "mg"},
        {"type": "number", "unit": "g"},
        {"type": "number"},
    ],
)
def test_same_name_mixed_schema_types_or_units_are_rejected(replacement):
    with pytest.raises(AnalysisError, match="incompatible Schema types or units"):
        validate_recipe(recipe(), [*CATALOG, {"key": "measurement", **replacement}])


def test_nullable_schema_is_supported_but_ambiguous_unions_are_not():
    result = validate_recipe(
        recipe(),
        [*CATALOG, {"key": "measurement", "type": ["number", "null"], "unit": "mg"}],
    )
    assert result["measurement"]["type"] == "number"
    with pytest.raises(AnalysisError, match="scalar Schema type"):
        validate_recipe(
            recipe(), [{"key": "measurement", "type": ["number", "string"]}]
        )


def test_enums_retain_schema_constraints():
    catalog = [*CATALOG, {"key": "choice", "type": "string", "enum": ["B", "A"]}]
    result = validate_recipe(recipe(group_by=["choice"]), catalog)
    assert result["choice"]["enum"] == ["A", "B"]
    with pytest.raises(AnalysisError, match="Grouping field"):
        compute_analysis(
            recipe(group_by=["choice"]),
            [record(1, {"measurement": 1, "choice": "C"})],
            catalog,
        )
    with pytest.raises(AnalysisError, match="Filter value"):
        validate_recipe(
            recipe(filters=[{"field": "choice", "op": "eq", "value": "C"}]), catalog
        )
    with pytest.raises(AnalysisError, match="incompatible Schema"):
        validate_recipe(
            recipe(group_by=["choice"]),
            [*catalog, {"key": "choice", "type": "string", "enum": ["A"]}],
        )


def test_record_and_group_hard_limits_never_truncate():
    rows = [record(i, {"measurement": i}) for i in range(MAX_RECORDS)]
    assert (
        compute_analysis(recipe(), rows, CATALOG)["counts"]["included"] == MAX_RECORDS
    )
    with pytest.raises(AnalysisError, match="5000 Records"):
        compute_analysis(
            recipe(), rows + [record(MAX_RECORDS, {"measurement": 1})], CATALOG
        )
    grouped = recipe(group_by=["measurement"])
    assert (
        len(compute_analysis(grouped, rows[:MAX_GROUPS], CATALOG)["groups"])
        == MAX_GROUPS
    )
    with pytest.raises(AnalysisError, match="200 groups"):
        compute_analysis(grouped, rows[: MAX_GROUPS + 1], CATALOG)


@pytest.mark.parametrize(
    "patch",
    [
        {"record_id": ""},
        {"record_version": True},
        {"record_version": 0},
        {"record_version": "1"},
        {"protocol_version": ""},
        {"data": []},
        {"data": {"var": []}},
    ],
)
def test_exact_source_identity_and_structured_values_are_required(patch):
    with pytest.raises(AnalysisError):
        compute_analysis(recipe(), [record(1, {"measurement": 1}, **patch)], CATALOG)


def test_duplicate_record_revisions_are_not_double_counted():
    row = record(1, {"measurement": 5})
    with pytest.raises(AnalysisError, match="Duplicate Record revisions"):
        compute_analysis(recipe(), [row, row], CATALOG)


def test_source_objects_remain_unmodified_and_chart_none_has_no_series():
    rows = [record(1, {"measurement": 5, "treatment": "A"})]
    original_rows, original_catalog = copy.deepcopy(rows), copy.deepcopy(CATALOG)
    result = compute_analysis(recipe(chart="none"), rows, CATALOG)
    assert rows == original_rows and CATALOG == original_catalog
    assert result["chart"]["series"] == []
    assert result["table"] == result["groups"]


def test_nonfinite_result_range_fails_instead_of_inventing_finite_statistics():
    rows = [record(i, {"measurement": 1e308}) for i in range(2)]
    assert preview_analysis(recipe(), rows, CATALOG)["counts"]["included"] == 2
    with pytest.raises(AnalysisError, match="numeric range exceeded"):
        compute_analysis(recipe(), rows, CATALOG)


def test_preview_counts_sources_without_executing_statistics(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Preview must not compute descriptive statistics")

    monkeypatch.setattr(analysis_engine, "_statistics", forbidden)
    rows = [
        record(1, {"measurement": 1}),
        record(2, {"measurement": None}),
        record(3, {"measurement": True}),
    ]
    result = preview_analysis(recipe(), rows, CATALOG)
    assert result["counts"] == {"total": 3, "included": 3, "filtered_out": 0}
    assert result["fields"] == {"measurement": {"count": 1, "missing": 1, "invalid": 1}}
    assert result["group_count"] == 1
    assert "groups" not in result and "chart" not in result and "table" not in result


def test_preview_blocks_missing_error_policy_and_group_overflow():
    with pytest.raises(AnalysisError, match="missing values"):
        preview_analysis(recipe(missing_policy="error"), [record(1, {})], CATALOG)
    with pytest.raises(AnalysisError, match="200 groups"):
        preview_analysis(
            recipe(group_by=["measurement"]),
            [record(i, {"measurement": i}) for i in range(MAX_GROUPS + 1)],
            CATALOG,
        )


def test_canonical_digest_is_order_stable_finite_and_not_a_string_serializer():
    assert canonical_digest({"b": 2, "a": 1}) == canonical_digest({"a": 1, "b": 2})
    assert len(canonical_digest({"a": [1, "二"]})) == 64
    with pytest.raises(ValueError):
        canonical_digest({"value": float("nan")})
    with pytest.raises(TypeError):
        canonical_digest({"value": object()})


def test_engine_contains_no_executable_expression_or_provider_boundary():
    tree = ast.parse(inspect.getsource(analysis_engine))
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not calls & {"eval", "exec", "compile", "__import__", "open"}
    imports = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    imports.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not any(
        name.startswith(
            ("subprocess", "httpx", "openai", "masterbrain", "os", "socket")
        )
        for name in imports
        if name
    )
