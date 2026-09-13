"""Actual Pydantic and historical AIMD Schema extraction for Record analysis."""

from __future__ import annotations

import ast
import copy
import inspect
from enum import Enum
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, Field

from app.services import analysis_schema
from app.services.analysis_engine import AnalysisError, AnalysisRecipe, validate_recipe
from app.services.analysis_schema import (
    MAX_ENUM_VALUES,
    MAX_SCHEMA_DEPTH,
    MAX_SCHEMA_FIELDS,
    schema_fields,
)


def version(schema):
    return SimpleNamespace(json_schema=schema, version="1.2.3")


def object_schema(**properties):
    return {"type": "object", "properties": properties}


@pytest.mark.parametrize(
    "wrapper", ["vars", "research_variable", "root", "properties_var"]
)
def test_historical_variable_schema_shapes(wrapper):
    variables = object_schema(
        yield_value={"type": "number", "title": "Yield", "unit": " mg "}
    )
    if wrapper in {"vars", "research_variable"}:
        schema = {wrapper: variables, "steps": {}, "checks": {}}
    elif wrapper == "properties_var":
        schema = object_schema(var=variables)
    else:
        schema = variables
    assert schema_fields(version(schema)) == [
        {
            "key": "yield_value",
            "title": "Yield",
            "type": "number",
            "unit": "mg",
            "protocol_version": "1.2.3",
        }
    ]


def test_actual_pydantic_nullable_enum_and_numeric_unit():
    class Treatment(str, Enum):
        CONTROL = "control"
        EXPOSED = "exposed"

    class Variables(BaseModel):
        treatment: Treatment | None = Field(None, title="Treatment group")
        concentration: float = Field(json_schema_extra={"unit": "mg/L"})

    # Pydantic's anyOf contains a local $ref and null, the exact gap being fixed.
    schema = Variables.model_json_schema()
    assert "$ref" in schema["properties"]["treatment"]["anyOf"][0]
    fields = schema_fields(version({"vars": schema}))
    catalog = {field["key"]: field for field in fields}
    assert catalog["treatment"] == {
        "key": "treatment",
        "title": "Treatment group",
        "type": ["string", "null"],
        "unit": None,
        "protocol_version": "1.2.3",
        "enum": ["control", "exposed"],
    }
    assert catalog["concentration"]["unit"] == "mg/L"
    validate_recipe(
        AnalysisRecipe(numeric_fields=["concentration"], group_by=["treatment"]), fields
    )


@pytest.mark.parametrize("location", ["local", "envelope", "properties_var"])
def test_defs_resolve_from_variable_or_envelope_scope(location):
    definitions = {"Measurement": {"type": "number", "unit": "s"}}
    variables = object_schema(
        duration={"$ref": "#/$defs/Measurement", "title": "Duration"}
    )
    if location == "local":
        variables["$defs"] = definitions
        schema = {"vars": variables}
    elif location == "envelope":
        schema = {"vars": variables, "$defs": definitions}
    else:
        schema = {**object_schema(var=variables), "$defs": definitions}
    field = schema_fields(version(schema))[0]
    assert (
        field["type"] == "number"
        and field["title"] == "Duration"
        and field["unit"] == "s"
    )


def test_variable_root_prefers_its_standalone_defs_and_preserves_input():
    schema = {
        "vars": {
            **object_schema(value={"$ref": "#/$defs/Value"}),
            "$defs": {"Value": {"type": "integer", "unit": "count"}},
        },
        "$defs": {"Value": {"type": "string"}},
    }
    original = copy.deepcopy(schema)
    assert schema_fields(version(schema))[0]["type"] == "integer"
    assert schema == original


def test_chained_local_defs_pointer_escapes_and_root_reference():
    schema = {
        "vars": {"$ref": "#/$defs/Variables"},
        "$defs": {
            "Variables": object_schema(value={"$ref": "#/$defs/A~1B~0C"}),
            "A/B~C": {"$ref": "#/$defs/Measurement"},
            "Measurement": {"type": "number", "unit": "g"},
        },
    }
    assert schema_fields(version(schema))[0]["unit"] == "g"


def test_legacy_definitions_references_are_local_json_pointers_too():
    schema = {
        **object_schema(value={"$ref": "#/definitions/Value"}),
        "definitions": {"Value": {"type": "number"}},
    }
    assert schema_fields(version(schema))[0]["type"] == "number"


@pytest.mark.parametrize("keyword", ["anyOf", "oneOf"])
def test_nullable_numeric_unions_preserve_unit(keyword):
    schema = object_schema(
        value={keyword: [{"type": "number", "unit": "kg"}, {"type": "null"}]}
    )
    field = schema_fields(version(schema))[0]
    assert field["type"] == ["number", "null"] and field["unit"] == "kg"


def test_nullable_enum_at_direct_union_parent_is_preserved():
    schema = object_schema(
        category={
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "enum": ["A", "B", None],
        }
    )
    field = schema_fields(version(schema))[0]
    assert field["enum"] == ["A", "B", None]


def test_same_type_enum_alternatives_form_schema_union_not_data_coercion():
    schema = object_schema(
        category={
            "anyOf": [
                {"type": "string", "enum": ["A"]},
                {"type": "string", "enum": ["B"]},
            ]
        }
    )
    assert schema_fields(version(schema))[0]["enum"] == ["A", "B"]


def test_unbounded_same_type_union_does_not_inherit_one_branch_enum():
    schema = object_schema(
        category={
            "anyOf": [
                {"type": "string", "enum": ["A"]},
                {"type": "string"},
            ]
        }
    )
    field = schema_fields(version(schema))[0]
    assert field["type"] == "string" and "enum" not in field


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "object", "properties": {"x": {"type": "number"}}},
        {"type": "array", "items": {"type": "number"}},
        {"type": ["number", "string"]},
        {"anyOf": [{"type": "integer"}, {"type": "number"}]},
        {"anyOf": [{"type": "number", "unit": "mg"}, {"type": "number", "unit": "g"}]},
        {"oneOf": [{"type": "number"}, {"type": "number", "minimum": 0}]},
        {"type": "number", "unit": {"symbol": "g"}},
        {"type": "number", "unit": "x" * 256},
        {"type": "integer", "enum": [True]},
        {"type": "number", "enum": ["1"]},
        {"type": "number", "enum": [float("nan")]},
        {"type": "number", "enum": [float("inf")]},
        {"type": "number", "enum": []},
        {"type": "number", "enum": list(range(MAX_ENUM_VALUES + 1))},
        {"type": "number", "const": 1, "enum": [2]},
        {"$dynamicRef": "#node"},
        True,
    ],
)
def test_unreferenced_unsupported_fields_do_not_block_scalar_analysis(bad):
    fields = schema_fields(
        version(object_schema(value={"type": "number"}, unsupported=bad))
    )
    unsupported = next(field for field in fields if field["key"] == "unsupported")
    assert unsupported["type"] == "unsupported" and unsupported["unsupported_reason"]
    validate_recipe(AnalysisRecipe(numeric_fields=["value"]), fields)
    with pytest.raises(AnalysisError):
        validate_recipe(
            AnalysisRecipe(numeric_fields=["value"], group_by=["unsupported"]), fields
        )


@pytest.mark.parametrize(
    "ref",
    [
        "https://example.invalid/schema.json",
        "file:///etc/passwd",
        "../schema.json#/$defs/A",
        "#anchor",
        "#/$defs/Missing",
        "#/$defs/A~2B",
        7,
    ],
)
def test_remote_missing_and_invalid_refs_never_resolve(ref):
    fields = schema_fields(
        version(object_schema(value={"type": "number"}, bad={"$ref": ref}))
    )
    assert fields[1]["type"] == "unsupported"
    assert fields[0]["type"] == "number"


@pytest.mark.parametrize("sibling", [{"type": "string"}, {"unit": "g"}, {"enum": [3]}])
def test_ref_siblings_cannot_override_scientific_constraints(sibling):
    schema = {
        **object_schema(value={"$ref": "#/$defs/Value", **sibling}),
        "$defs": {"Value": {"type": "number", "unit": "mg", "enum": [1, 2]}},
    }
    assert schema_fields(version(schema))[0]["type"] == "unsupported"


def test_ref_title_override_is_an_annotation_not_a_type_override():
    schema = {
        **object_schema(value={"$ref": "#/$defs/Value", "title": "Custom title"}),
        "$defs": {"Value": {"type": "number", "title": "Shared title", "unit": "mg"}},
    }
    assert schema_fields(version(schema))[0]["title"] == "Custom title"


def test_cycles_and_deep_refs_fail_closed_per_field():
    definitions = {"Cycle": {"$ref": "#/$defs/Cycle"}}
    for index in range(MAX_SCHEMA_DEPTH + 2):
        definitions[f"Depth{index}"] = {"$ref": f"#/$defs/Depth{index + 1}"}
    definitions[f"Depth{MAX_SCHEMA_DEPTH + 2}"] = {"type": "number"}
    schema = {
        **object_schema(
            value={"type": "number"},
            cycle={"$ref": "#/$defs/Cycle"},
            deep={"$ref": "#/$defs/Depth0"},
        ),
        "$defs": definitions,
    }
    fields = {field["key"]: field for field in schema_fields(version(schema))}
    assert fields["value"]["type"] == "number"
    assert "Cyclic" in fields["cycle"]["unsupported_reason"]
    assert "depth" in fields["deep"]["unsupported_reason"]


def test_repeated_reference_union_has_a_node_budget_not_exponential_work():
    definitions = {"Leaf": {"type": "number"}}
    for index in reversed(range(6)):
        target = "Leaf" if index == 5 else f"Level{index + 1}"
        definitions[f"Level{index}"] = {
            "anyOf": [{"$ref": f"#/$defs/{target}"} for _ in range(8)]
        }
    schema = {**object_schema(value={"$ref": "#/$defs/Level0"}), "$defs": definitions}
    field = schema_fields(version(schema))[0]
    assert field["type"] == "unsupported"
    assert "node budget" in field["unsupported_reason"]


def test_complex_literal_var_field_does_not_hide_unrelated_numeric_fields():
    fields = schema_fields(
        version(object_schema(value={"type": "number"}, var={"type": "array"}))
    )
    assert [field["key"] for field in fields] == ["value", "var"]
    validate_recipe(AnalysisRecipe(numeric_fields=["value"]), fields)


def test_allof_objects_keep_disjoint_properties_and_reject_conflicts():
    schema = {
        "allOf": [
            object_schema(a={"type": "number"}),
            object_schema(b={"type": "string"}),
        ]
    }
    assert {field["key"] for field in schema_fields(version(schema))} == {"a", "b"}
    with pytest.raises(AnalysisError, match="Conflicting Schema object composition"):
        schema_fields(
            version(
                {
                    "allOf": [
                        object_schema(a={"type": "number"}),
                        object_schema(a={"type": "string"}),
                    ]
                }
            )
        )


@pytest.mark.parametrize(
    "schema",
    [None, [], {"vars": []}, {"vars": True}, {"type": "array"}, {"properties": []}],
)
def test_invalid_variable_roots_raise_an_explicit_analysis_error(schema):
    with pytest.raises(AnalysisError):
        schema_fields(version(schema))


def test_root_cycle_and_oversized_catalog_are_bounded():
    with pytest.raises(AnalysisError, match="Cyclic"):
        schema_fields(
            version(
                {"$ref": "#/$defs/Root", "$defs": {"Root": {"$ref": "#/$defs/Root"}}}
            )
        )
    with pytest.raises(AnalysisError, match="2000 fields"):
        schema_fields(
            version(
                object_schema(
                    **{
                        f"f{i}": {"type": "number"}
                        for i in range(MAX_SCHEMA_FIELDS + 1)
                    }
                )
            )
        )


def test_schema_reader_imports_no_network_filesystem_or_code_executor():
    tree = ast.parse(inspect.getsource(analysis_schema))
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
            ("requests", "urllib", "httpx", "socket", "pathlib", "os", "subprocess")
        )
        for name in imports
        if name
    )
