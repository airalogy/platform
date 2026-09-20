"""Known-result, lineage and fail-closed contracts for Project analysis."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.services import project_analysis_engine as engine
from app.services.analysis_engine import (
    AnalysisError,
    canonical_digest,
    compute_analysis,
)
from app.services.analysis_schema import schema_fields
from app.services.project_analysis_engine import (
    ENGINE_VERSION,
    ProjectAnalysisError,
    ProjectAnalysisRecipe,
    compute_project_analysis,
    preview_project_analysis,
    project_source_fields,
    validate_project_recipe,
)


def make_source(protocol, rows, properties):
    schema = {"type": "object", "properties": deepcopy(properties)}
    version = SimpleNamespace(version="1.0.0", json_schema=schema)
    return {
        "schema_version": 1,
        "protocol_id": str(UUID(int=protocol)),
        "records": [
            {
                "record_id": str(UUID(int=protocol * 10000 + index + 1)),
                "record_version": 1,
                "protocol_version": "1.0.0",
                "record_hash": canonical_digest({"var": values}),
                "data": {"var": deepcopy(values)},
            }
            for index, values in enumerate(rows)
        ],
        "schemas": [
            {
                "id": str(UUID(int=100 + protocol)),
                "version": version.version,
                "json_schema": schema,
                "fields": {},
            }
        ],
        "fields": schema_fields(version),
    }


def refresh_fields(source):
    source["fields"] = [
        field
        for schema in source["schemas"]
        for field in schema_fields(SimpleNamespace(**schema))
    ]


def project_fixture(mode="relational"):
    """Two explicit Protocols: S1/S2 matched; S3 and S4 remain unmatched."""
    snapshot = {
        "schema": "airalogy.project-snapshot.v1",
        "project_id": str(UUID(int=999)),
        "inputs": [
            {
                "slot_id": "treatment",
                "label": "treatment",
                "snapshot": make_source(
                    1,
                    [
                        {"sample_id": "S1", "dose": 2},
                        {"sample_id": "S2", "dose": 4},
                        {"sample_id": "S3", "dose": 6},
                    ],
                    {
                        "sample_id": {"type": "string"},
                        "dose": {"type": "number", "unit": "mg"},
                    },
                ),
            },
            {
                "slot_id": "assay",
                "label": "assay",
                "snapshot": make_source(
                    2,
                    [
                        {"specimen_code": "S1", "response": 10},
                        {"specimen_code": "S2", "response": 20},
                        {"specimen_code": "S4", "response": 40},
                    ],
                    {
                        "specimen_code": {"type": "string"},
                        "response": {"type": "number", "unit": "%"},
                    },
                ),
            },
        ],
    }
    payload = {
        "kind": "project",
        "schema_version": 1,
        "mode": mode,
        "slots": [
            {
                "slot_id": "treatment",
                "label": "Drug administration",
                "recipe": {"numeric_fields": ["dose"]},
            },
            {
                "slot_id": "assay",
                "label": "Viability measurements",
                "recipe": {"numeric_fields": ["response"]},
            },
        ],
    }
    if mode == "relational":
        payload["join"] = {
            "left_slot_id": "treatment",
            "right_slot_id": "assay",
            "kind": "inner",
            "keys": [{"left_field": "sample_id", "right_field": "specimen_code"}],
            "semantic_alignment_confirmed": True,
            "outputs": [
                {
                    "output_id": "dose",
                    "slot_id": "treatment",
                    "field": "dose",
                    "semantic_label": "Administered dose",
                    "unit": "mg",
                },
                {
                    "output_id": "response",
                    "slot_id": "assay",
                    "field": "response",
                    "semantic_label": "Observed viability",
                    "unit": "%",
                },
            ],
            "recipe": {"numeric_fields": ["dose", "response"]},
        }
    return ProjectAnalysisRecipe.model_validate(payload), snapshot


def source(snapshot, slot="treatment"):
    return next(
        item["snapshot"] for item in snapshot["inputs"] if item["slot_id"] == slot
    )


def values(snapshot, slot="treatment", row=0):
    return source(snapshot, slot)["records"][row]["data"]["var"]


def change_recipe(recipe, *, join=None, **updates):
    payload = recipe.model_dump(mode="json")
    payload.update(updates)
    if join is not None:
        payload["join"].update(join)
    return ProjectAnalysisRecipe.model_validate(payload)


def stats(report, field):
    return report["groups"][0]["fields"][field]


def failure(recipe, snapshot, code):
    with pytest.raises(ProjectAnalysisError) as exc:
        compute_project_analysis(recipe, snapshot)
    assert exc.value.code == code
    return exc.value


def test_known_inner_join_uses_only_matched_samples_and_exact_field_lineage():
    recipe, snapshot = project_fixture()
    result = compute_project_analysis(recipe, snapshot)
    assert result["schema"] == "airalogy.project-result.v1"
    assert result["engine_version"] == ENGINE_VERSION
    assert result["counts"] == {"protocols": 2, "records": 6}
    assert result["source_digest"] == canonical_digest(snapshot)
    assert result["recipe_digest"] == canonical_digest(recipe.model_dump(mode="json"))
    joined = result["join"]
    assert joined["audit"]["output_rows"] == 2
    assert joined["audit"]["left"] == {
        "slot_id": "treatment",
        "total": 3,
        "filtered_out": 0,
        "key_missing": 0,
        "invalid_keys": 0,
        "excluded": 0,
        "duplicate_keys": 0,
        "duplicate_rows": 0,
        "matched": 2,
        "unmatched": 1,
    }
    assert joined["audit"]["right"] == {**joined["audit"]["left"], "slot_id": "assay"}
    assert stats(joined["report"], "dose")["mean"] == 3
    assert stats(joined["report"], "response")["mean"] == 15
    assert joined["rows"][0]["values"] == {"dose": 2, "response": 10}
    for row in joined["rows"]:
        assert row["row_id"].startswith("derived:")
        for field, slot in (("dose", "treatment"), ("response", "assay")):
            ref = row["sources"][slot]
            assert ref["record_id"] in {
                r["record_id"] for r in source(snapshot, slot)["records"]
            }
            assert ref["record_version"] == 1
            assert (
                ref["protocol_version_id"] == source(snapshot, slot)["schemas"][0]["id"]
            )
            assert row["field_lineage"][field] == {**ref, "field_path": ["var", field]}
            assert row["row_id"] != ref["record_id"]
    assert result["warnings"] == [{"code": "association_not_causation"}]


def test_preview_and_execution_are_identical_without_mutating_snapshot_or_recipe():
    recipe, snapshot = project_fixture()
    before = deepcopy(snapshot), recipe.model_dump(mode="json")
    assert preview_project_analysis(recipe, snapshot) == compute_project_analysis(
        recipe, snapshot
    )
    assert before == (snapshot, recipe.model_dump(mode="json"))
    validate_project_recipe(recipe, snapshot)


def test_evidence_synthesis_keeps_protocol_denominators_and_display_labels():
    recipe, snapshot = project_fixture("evidence_synthesis")
    result = compute_project_analysis(recipe, snapshot)
    assert result["join"] is None
    assert result["warnings"] == [{"code": "separate_evidence_not_pooled"}]
    for slot, entry in zip(recipe.slots, result["local_results"], strict=True):
        own_source = source(snapshot, slot.slot_id)
        assert entry["label"] == slot.label != slot.slot_id
        assert entry["source_digest"] == canonical_digest(own_source)
        assert entry["report"] == compute_analysis(
            slot.recipe, own_source["records"], own_source["fields"]
        )
        assert entry["report"]["counts"]["total"] == 3
    assert stats(result["local_results"][0]["report"], "dose")["mean"] == 4
    assert stats(result["local_results"][1]["report"], "response")[
        "mean"
    ] == pytest.approx(70 / 3)


def test_synthesis_does_not_merge_same_named_fields_with_different_units():
    recipe, snapshot = project_fixture("evidence_synthesis")
    right = source(snapshot, "assay")
    right["schemas"][0]["json_schema"]["properties"]["dose"] = {
        "type": "number",
        "unit": "mM",
    }
    for row in right["records"]:
        row["data"]["var"]["dose"] = row["data"]["var"].pop("response")
    refresh_fields(right)
    payload = recipe.model_dump(mode="json")
    payload["slots"][1]["recipe"]["numeric_fields"] = ["dose"]
    recipe = ProjectAnalysisRecipe.model_validate(payload)
    result = compute_project_analysis(recipe, snapshot)
    assert [
        entry["report"]["fields"][0]["unit"] for entry in result["local_results"]
    ] == ["mg", "mM"]


def test_eight_independent_protocols_are_supported_but_nine_are_not():
    recipe, snapshot = project_fixture("evidence_synthesis")
    payload = recipe.model_dump(mode="json")
    for index in range(3, 9):
        slot_id = f"source_{index}"
        payload["slots"].append(
            {
                "slot_id": slot_id,
                "label": slot_id,
                "recipe": {"numeric_fields": ["dose"]},
            }
        )
        snapshot["inputs"].append(
            {
                "slot_id": slot_id,
                "label": slot_id,
                "snapshot": make_source(
                    index, [{"dose": index}], {"dose": {"type": "integer"}}
                ),
            }
        )
    recipe = ProjectAnalysisRecipe.model_validate(payload)
    assert compute_project_analysis(recipe, snapshot)["counts"] == {
        "protocols": 8,
        "records": 12,
    }
    payload["slots"].append({**payload["slots"][-1], "slot_id": "source_9"})
    with pytest.raises(ValidationError):
        ProjectAnalysisRecipe.model_validate(payload)


def test_left_join_keeps_unmatched_left_without_fabricated_right_evidence():
    recipe, snapshot = project_fixture()
    result = compute_project_analysis(
        change_recipe(recipe, join={"kind": "left"}), snapshot
    )["join"]
    assert result["audit"]["output_rows"] == 3
    row = next(row for row in result["rows"] if row["sources"]["assay"] is None)
    assert row["values"] == {"dose": 6, "response": None}
    assert row["field_lineage"]["response"] is None
    assert stats(result["report"], "response")["count"] == 2
    assert stats(result["report"], "response")["missing"] == 1
    assert stats(result["report"], "dose")["count"] == 3


@pytest.mark.parametrize("missing", [None, "absent"])
def test_missing_keys_fail_with_counts_or_require_explicit_exclusion(missing):
    recipe, snapshot = project_fixture()
    values(snapshot)["sample_id"] = None
    values(snapshot, "assay")["specimen_code"] = None
    if missing == "absent":
        del values(snapshot)["sample_id"]
        del values(snapshot, "assay")["specimen_code"]
    error = failure(recipe, snapshot, "missing_join_keys")
    assert (
        error.audit["left"]["key_missing"] == error.audit["right"]["key_missing"] == 1
    )
    assert error.audit["left"]["matched"] == 1
    excluded = compute_project_analysis(
        change_recipe(recipe, join={"missing_key_policy": "exclude"}), snapshot
    )["join"]
    assert excluded["audit"]["output_rows"] == 1
    assert excluded["audit"]["left"]["excluded"] == 1
    assert excluded["rows"][0]["values"] == {"dose": 4, "response": 20}


@pytest.mark.parametrize(
    "side,slot,key",
    [("left", "treatment", "sample_id"), ("right", "assay", "specimen_code")],
)
def test_duplicate_keys_never_expand_samples_or_disclose_key_values(side, slot, key):
    recipe, snapshot = project_fixture()
    values(snapshot, slot, 0)[key] = "private-key"
    values(snapshot, slot, 1)[key] = "private-key"
    error = failure(recipe, snapshot, "duplicate_join_keys")
    assert error.audit[side]["duplicate_keys"] == 1
    assert error.audit[side]["duplicate_rows"] == 2
    assert error.audit["output_rows"] == 0
    assert "private-key" not in str(error) + str(error.audit)


def test_join_audit_precedes_unrelated_local_missing_measurement_failure():
    recipe, snapshot = project_fixture()
    payload = recipe.model_dump(mode="json")
    payload["slots"][0]["recipe"]["missing_policy"] = "error"
    values(snapshot)["dose"] = None
    values(snapshot)["sample_id"] = values(snapshot, row=1)["sample_id"]
    assert (
        failure(
            ProjectAnalysisRecipe.model_validate(payload),
            snapshot,
            "duplicate_join_keys",
        ).audit["left"]["duplicate_rows"]
        == 2
    )


def test_composite_keys_disambiguate_repeats_without_cartesian_expansion():
    recipe, snapshot = project_fixture()
    for slot, key in (("treatment", "sample_id"), ("assay", "specimen_code")):
        own = source(snapshot, slot)
        own["schemas"][0]["json_schema"]["properties"]["replicate"] = {
            "type": "integer"
        }
        for index, row in enumerate(own["records"]):
            row["data"]["var"].update({key: "same", "replicate": index})
        refresh_fields(own)
    recipe = change_recipe(
        recipe,
        join={
            "keys": [
                *recipe.join.model_dump()["keys"],
                {"left_field": "replicate", "right_field": "replicate"},
            ]
        },
    )
    result = compute_project_analysis(recipe, snapshot)["join"]
    assert result["audit"]["output_rows"] == 3
    assert result["audit"]["left"]["duplicate_keys"] == 0
    assert stats(result["report"], "response")["sum"] == 70


@pytest.mark.parametrize(
    "kind,left_value,right_value,matched",
    [
        ("number", 1, 1.0, True),
        ("number", -0.0, 0, True),
        ("integer", 1, 1, True),
        ("boolean", True, True, True),
        ("boolean", True, False, False),
        ("string", "1", "01", False),
        ("string", "S1", " S1 ", False),
        ("string", "S1", "s1", False),
    ],
)
def test_key_matching_is_typed_without_coercion_or_normalization(
    kind, left_value, right_value, matched
):
    recipe, snapshot = project_fixture()
    for slot, key, value in (
        ("treatment", "sample_id", left_value),
        ("assay", "specimen_code", right_value),
    ):
        own = source(snapshot, slot)
        own["records"] = own["records"][:1]
        own["records"][0]["data"]["var"][key] = value
        own["schemas"][0]["json_schema"]["properties"][key] = {"type": kind}
        refresh_fields(own)
    result = compute_project_analysis(recipe, snapshot)["join"]
    assert result["audit"]["output_rows"] == int(matched)
    assert result["audit"]["left"]["unmatched"] == int(not matched)


@pytest.mark.parametrize(
    "kind,value",
    [
        ("number", True),
        ("integer", 1.0),
        ("number", "1"),
        ("boolean", 1),
        ("string", {"value": "S1"}),
        ("string", "x" * 2001),
    ],
)
def test_wrong_runtime_key_type_fails_closed_even_with_exclude_policy(kind, value):
    recipe, snapshot = project_fixture()
    for slot, key in (("treatment", "sample_id"), ("assay", "specimen_code")):
        own = source(snapshot, slot)
        own["records"] = own["records"][:1]
        own["schemas"][0]["json_schema"]["properties"][key] = {"type": kind}
        own["records"][0]["data"]["var"][key] = value
        refresh_fields(own)
    error = failure(
        change_recipe(recipe, join={"missing_key_policy": "exclude"}),
        snapshot,
        "invalid_join_keys",
    )
    assert error.audit["left"]["invalid_keys"] == 1
    assert error.audit["output_rows"] == 0


def test_local_filters_apply_before_join_and_join_filters_have_their_own_audit():
    recipe, snapshot = project_fixture()
    payload = recipe.model_dump(mode="json")
    payload["slots"][0]["recipe"]["filters"] = [
        {"field": "dose", "op": "gt", "value": 2}
    ]
    payload["join"]["kind"] = "left"
    payload["join"]["recipe"]["filters"] = [{"field": "response", "op": "present"}]
    result = compute_project_analysis(
        ProjectAnalysisRecipe.model_validate(payload), snapshot
    )
    joined = result["join"]
    assert result["local_results"][0]["report"]["counts"]["filtered_out"] == 1
    assert (
        joined["audit"]["left"]["filtered_out"]
        == joined["audit"]["left"]["excluded"]
        == 1
    )
    assert joined["audit"]["output_rows"] == 2
    assert joined["report"]["counts"] == {"total": 2, "included": 1, "filtered_out": 1}
    assert stats(joined["report"], "dose")["mean"] == 4


def test_declared_but_unused_output_is_still_strictly_typed():
    recipe, snapshot = project_fixture()
    recipe = change_recipe(recipe, join={"recipe": {"numeric_fields": ["dose"]}})
    values(snapshot, "assay")["response"] = {"private": "not a scalar"}
    error = failure(recipe, snapshot, "invalid_join_outputs")
    assert error.audit["invalid_output_values"] == {"response": 1}
    assert "not a scalar" not in str(error.audit)


def test_output_catalog_preserves_source_enum_constraints_for_join_filters():
    recipe, snapshot = project_fixture()
    own = source(snapshot)
    own["schemas"][0]["json_schema"]["properties"]["dose"]["enum"] = [2, 4, 6]
    refresh_fields(own)
    report = compute_project_analysis(recipe, snapshot)["join"]
    assert report["fields"][0]["enum"] == [2, 4, 6]
    assert report["report"]["fields"][0]["enum"] == [2, 4, 6]
    recipe = change_recipe(
        recipe,
        join={
            "recipe": {
                "numeric_fields": ["dose"],
                "filters": [{"field": "dose", "op": "eq", "value": 999}],
            }
        },
    )
    with pytest.raises(AnalysisError, match="Filter value"):
        validate_project_recipe(recipe, snapshot)


def test_join_chart_and_group_statistics_reference_the_same_derived_rows():
    recipe, snapshot = project_fixture()
    payload = recipe.model_dump(mode="json")
    payload["join"]["outputs"].append(
        {
            "output_id": "sample",
            "slot_id": "treatment",
            "field": "sample_id",
            "semantic_label": "Explicit sample identifier",
            "unit": None,
        }
    )
    payload["join"]["recipe"].update(group_by=["sample"], chart="line")
    result = compute_project_analysis(
        ProjectAnalysisRecipe.model_validate(payload), snapshot
    )["join"]
    assert result["report"]["table"] == result["report"]["groups"]
    assert len(result["report"]["groups"]) == len(result["rows"]) == 2
    for point, group in zip(
        result["report"]["chart"]["series"][0]["points"],
        result["report"]["groups"],
        strict=True,
    ):
        matching = [
            row
            for row in result["rows"]
            if row["values"]["sample"] == group["key"][0]["value"]
        ]
        assert point["count"] == group["row_count"] == len(matching) == 1
        assert point["value"] == matching[0]["values"]["dose"]


def test_keys_retain_exact_old_record_and_schema_revisions_in_lineage():
    recipe, snapshot = project_fixture()
    own = source(snapshot)
    own["records"][0]["record_version"] = 7
    own["records"][0]["record_hash"] = "sealed-historical-hash"
    result = compute_project_analysis(recipe, snapshot)
    ref = result["join"]["rows"][0]["field_lineage"]["dose"]
    assert ref["record_version"] == 7
    assert ref["record_hash"] == "sealed-historical-hash"
    assert ref["protocol_version_id"] == own["schemas"][0]["id"]
    assert ref["field_path"] == ["var", "dose"]


@pytest.mark.parametrize("unit", [None, "g", " mg "])
def test_output_units_cannot_be_implicitly_assigned_or_converted(unit):
    recipe, snapshot = project_fixture()
    payload = recipe.model_dump(mode="json")
    payload["join"]["outputs"][0]["unit"] = unit
    failure(
        ProjectAnalysisRecipe.model_validate(payload),
        snapshot,
        "unit_conversion_required",
    )


@pytest.mark.parametrize("right_schema", [{"type": "number"}, {"type": "integer"}])
def test_join_key_schema_type_mismatch_is_not_coerced(right_schema):
    recipe, snapshot = project_fixture()
    right = source(snapshot, "assay")
    right["schemas"][0]["json_schema"]["properties"]["specimen_code"] = right_schema
    refresh_fields(right)
    failure(recipe, snapshot, "join_key_contract")


def test_numeric_join_keys_require_the_same_unit():
    recipe, snapshot = project_fixture()
    for slot, key, unit in (
        ("treatment", "sample_id", "mg"),
        ("assay", "specimen_code", "g"),
    ):
        own = source(snapshot, slot)
        own["schemas"][0]["json_schema"]["properties"][key] = {
            "type": "number",
            "unit": unit,
        }
        refresh_fields(own)
    failure(recipe, snapshot, "join_key_contract")


@pytest.mark.parametrize(
    "bad_schema",
    [
        {"type": "string", "airalogy_type": "FileId"},
        {"type": "array", "items": {"type": "string"}},
        {"type": "object"},
        {"anyOf": [{"type": "number"}, {"type": "string"}]},
        {"$ref": "https://invalid.example/schema"},
        {"$dynamicRef": "#node", "type": "string"},
    ],
)
def test_complex_file_and_remote_schema_fields_never_become_scalar_keys(bad_schema):
    recipe, snapshot = project_fixture()
    own = source(snapshot)
    own["schemas"][0]["json_schema"]["properties"]["sample_id"] = bad_schema
    refresh_fields(own)
    failure(recipe, snapshot, "unsupported_field")


def test_unreferenced_complex_fields_do_not_disable_independent_analysis():
    recipe, snapshot = project_fixture()
    own = source(snapshot)
    own["schemas"][0]["json_schema"]["properties"]["attachment"] = {
        "type": "string",
        "airalogy_type": "FileId",
    }
    refresh_fields(own)
    validate_project_recipe(recipe, snapshot)


def test_discovery_catalog_does_not_offer_file_ids_as_string_keys():
    _, snapshot = project_fixture()
    own = source(snapshot)
    properties = own["schemas"][0]["json_schema"]["properties"]
    properties.update(
        attachment={"type": "string", "airalogy_type": "FileId"},
        table={"type": "array", "items": {"type": "number"}},
    )
    refresh_fields(own)
    # A latest-schema discovery has no selection yet; exact selection includes
    # Records, but both views must expose the same field capabilities.
    discovery = {key: value for key, value in own.items() if key != "records"}
    fields = {field["key"]: field for field in project_source_fields(discovery)}
    assert fields == {field["key"]: field for field in project_source_fields(own)}
    assert fields["dose"]["type"] == "number"
    assert fields["dose"]["unit"] == "mg"
    assert fields["sample_id"]["type"] == "string"
    for key in ("attachment", "table"):
        assert fields[key]["type"] == "unsupported"
        assert fields[key]["unsupported_reason"]


@pytest.mark.parametrize("change", ["missing", "type", "unit", "enum", "file"])
def test_discovery_catalog_matches_the_intersection_of_all_selected_schemas(change):
    _, snapshot = project_fixture()
    own = source(snapshot)
    second = deepcopy(own["schemas"][0])
    second.update(id=str(UUID(int=444)), version="2.0.0")
    properties = second["json_schema"]["properties"]
    if change == "missing":
        del properties["dose"]
    elif change == "type":
        properties["dose"]["type"] = "integer"
    elif change == "unit":
        properties["dose"]["unit"] = "g"
    elif change == "enum":
        properties["dose"]["enum"] = [2, 4, 6]
    else:
        properties["dose"] = {"type": "string", "airalogy_type": "FileId"}
    own["records"][0]["protocol_version"] = "2.0.0"
    own["schemas"].append(second)
    refresh_fields(own)
    fields = {field["key"]: field for field in project_source_fields(own)}
    assert fields["dose"]["type"] == "unsupported"
    assert fields["sample_id"]["type"] == "string"


def test_catalog_rebuilds_each_schema_only_once_per_requested_view(monkeypatch):
    _, snapshot = project_fixture()
    own = source(snapshot)
    properties = own["schemas"][0]["json_schema"]["properties"]
    properties.update({f"extra_{index}": {"type": "number"} for index in range(30)})
    refresh_fields(own)
    actual = engine.protocol_field_catalog
    calls = []

    def tracked(version):
        calls.append(version.version)
        return actual(version)

    monkeypatch.setattr(engine, "protocol_field_catalog", tracked)
    assert len(project_source_fields(own)) == 32
    assert calls == ["1.0.0"]


def test_forged_or_duplicated_display_catalog_is_rejected():
    recipe, snapshot = project_fixture()
    source(snapshot)["fields"].append(deepcopy(source(snapshot)["fields"][0]))
    failure(recipe, snapshot, "schema_changed")


def test_local_references_and_historical_var_wrapper_preserve_units():
    recipe, snapshot = project_fixture()
    for item in snapshot["inputs"]:
        own = item["snapshot"]
        schema = own["schemas"][0]["json_schema"]
        own["schemas"][0]["json_schema"] = {
            "vars": {
                "$defs": {"variables": schema},
                "type": "object",
                "properties": {"var": {"$ref": "#/$defs/variables"}},
            }
        }
        refresh_fields(own)
    assert (
        compute_project_analysis(recipe, snapshot)["join"]["fields"][0]["unit"] == "mg"
    )


def test_property_order_is_not_a_schema_change():
    recipe, snapshot = project_fixture()
    own = source(snapshot)
    properties = own["schemas"][0]["json_schema"]["properties"]
    own["schemas"][0]["json_schema"]["properties"] = dict(
        reversed(list(properties.items()))
    )
    validate_project_recipe(recipe, snapshot)


@pytest.mark.parametrize("change", ["missing", "type", "unit", "enum"])
def test_each_referenced_field_must_exist_compatibly_in_every_exact_version(change):
    recipe, snapshot = project_fixture()
    own = source(snapshot)
    second = deepcopy(own["schemas"][0])
    second.update(id=str(UUID(int=444)), version="2.0.0")
    field = second["json_schema"]["properties"]["dose"]
    if change == "missing":
        del second["json_schema"]["properties"]["dose"]
    elif change == "type":
        field["type"] = "string"
    elif change == "unit":
        field["unit"] = "g"
    else:
        field["enum"] = [2, 4, 6]
    own["records"][0]["protocol_version"] = "2.0.0"
    own["schemas"].append(second)
    refresh_fields(own)
    with pytest.raises(ProjectAnalysisError):
        compute_project_analysis(recipe, snapshot)


@pytest.mark.parametrize(
    "malformation",
    [
        "missing_slot",
        "duplicate_slot",
        "extra_slot",
        "duplicate_protocol",
        "duplicate_record",
        "multiple_record_revisions",
        "missing_schema",
        "bad_version",
        "bad_record_version",
        "no_records",
        "bad_uuid",
    ],
)
def test_snapshot_requires_exact_distinct_sources_without_silent_drop(malformation):
    recipe, snapshot = project_fixture()
    if malformation == "missing_slot":
        snapshot["inputs"].pop()
    elif malformation == "duplicate_slot":
        snapshot["inputs"][1]["slot_id"] = "treatment"
    elif malformation == "extra_slot":
        snapshot["inputs"].append(
            {**deepcopy(snapshot["inputs"][1]), "slot_id": "third"}
        )
    elif malformation == "duplicate_protocol":
        source(snapshot, "assay")["protocol_id"] = source(snapshot)["protocol_id"]
    elif malformation == "duplicate_record":
        source(snapshot)["records"].append(deepcopy(source(snapshot)["records"][0]))
    elif malformation == "multiple_record_revisions":
        historical = deepcopy(source(snapshot)["records"][0])
        historical["record_version"] += 1
        source(snapshot)["records"].append(historical)
    elif malformation == "missing_schema":
        source(snapshot)["schemas"] = []
    elif malformation == "bad_version":
        source(snapshot)["schema_version"] = True
    elif malformation == "bad_record_version":
        source(snapshot)["records"][0]["record_version"] = True
    elif malformation == "no_records":
        source(snapshot)["records"] = []
    else:
        snapshot["project_id"] = "not-a-project-id"
    with pytest.raises(ProjectAnalysisError):
        compute_project_analysis(recipe, snapshot)


@pytest.mark.parametrize("version", [True, 1.0, "1", 2])
def test_recipe_versions_are_exact_integers(version):
    recipe, _ = project_fixture()
    with pytest.raises(ValidationError):
        change_recipe(recipe, schema_version=version)


@pytest.mark.parametrize(
    "join",
    [
        {"kind": "outer"},
        {"cardinality": "many_to_many"},
        {"duplicate_key_policy": "first"},
        {"missing_key_policy": "guess"},
        {"semantic_alignment_confirmed": False},
        {"semantic_alignment_confirmed": 1},
        {"conversion": "x * 1000"},
        {"left_slot_id": "unknown"},
    ],
)
def test_unsupported_or_unconfirmed_join_semantics_are_not_executed(join):
    recipe, _ = project_fixture()
    with pytest.raises(ValidationError):
        change_recipe(recipe, join=join)


def test_duplicate_output_and_key_selections_are_rejected():
    recipe, _ = project_fixture()
    payload = recipe.model_dump(mode="json")
    with pytest.raises(ValidationError):
        change_recipe(recipe, join={"keys": payload["join"]["keys"] * 2})
    with pytest.raises(ValidationError):
        change_recipe(recipe, join={"outputs": payload["join"]["outputs"] * 2})
    with pytest.raises(ValidationError):
        change_recipe(recipe, slots=payload["slots"] * 2)
    with pytest.raises(ValidationError):
        change_recipe(recipe, mode="evidence_synthesis")


def test_total_source_limit_rejects_5001_without_truncation():
    recipe, snapshot = project_fixture("evidence_synthesis")
    own = source(snapshot)
    template = own["records"][0]
    own["records"] = [
        {**deepcopy(template), "record_id": str(UUID(int=500000 + index))}
        for index in range(4998)
    ]
    failure(recipe, snapshot, "record_limit")
    assert len(own["records"]) == 4998


@pytest.mark.parametrize(
    "constant", ["MAX_PROJECT_SNAPSHOT_BYTES", "MAX_PROJECT_RESULT_BYTES"]
)
def test_json_size_bounds_are_explicit_and_do_not_truncate(monkeypatch, constant):
    recipe, snapshot = project_fixture()
    monkeypatch.setattr(engine, constant, 1)
    failure(recipe, snapshot, "size_limit")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_source_data_cannot_be_sealed_as_json(value):
    recipe, snapshot = project_fixture()
    values(snapshot)["dose"] = value
    with pytest.raises(ProjectAnalysisError, match="finite JSON"):
        compute_project_analysis(recipe, snapshot)


def test_overflowing_statistics_fail_without_returning_a_result():
    recipe, snapshot = project_fixture()
    values(snapshot)["dose"] = 1e308
    values(snapshot, row=1)["dose"] = 1e308
    with pytest.raises(AnalysisError, match="numeric range"):
        compute_project_analysis(recipe, snapshot)


def test_record_order_does_not_change_join_rows_or_local_statistics():
    recipe, snapshot = project_fixture()
    first = compute_project_analysis(recipe, snapshot)
    for item in snapshot["inputs"]:
        item["snapshot"]["records"].reverse()
    second = compute_project_analysis(recipe, snapshot)
    assert first["join"] == second["join"]
    assert [entry["report"] for entry in first["local_results"]] == [
        entry["report"] for entry in second["local_results"]
    ]
    assert first["source_digest"] != second["source_digest"]


def test_saved_old_kernel_contract_is_not_extended_with_project_fields():
    recipe, snapshot = project_fixture("evidence_synthesis")
    old = recipe.slots[0].recipe
    assert old.model_dump(mode="json") == {
        "schema_version": 1,
        "numeric_fields": ["dose"],
        "group_by": [],
        "filters": [],
        "missing_policy": "exclude",
        "chart": "bar",
    }
    result = compute_project_analysis(recipe, snapshot)
    assert (
        result["local_results"][0]["report"]["engine_version"] == "airalogy.analysis.v1"
    )
