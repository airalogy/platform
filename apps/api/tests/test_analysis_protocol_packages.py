"""Portable method contracts contain no implicit source grants or executable code."""

import io
import json
import stat
import zipfile
from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.services import analysis_protocol_packages as packages
from app.services.analysis_engine import canonical_digest


def builtin_method():
    return SimpleNamespace(
        id=UUID(int=200),
        project_id=UUID(int=201),
        protocol_id=UUID(int=202),
        protocol_version_id=UUID(int=203),
        source_pipeline_revision_id=UUID(int=204),
        title="PRIVATE SOURCE TITLE",
        question="PRIVATE QUESTION",
        result={"private": 812},
        engine_version="airalogy.analysis.v1",
        recipe={
            "numeric_fields": ["dose"],
            "group_by": ["arm"],
            "filters": [{"field": "included", "op": "eq", "value": True}],
        },
        input_fields=[
            {
                "key": "dose",
                "type": "number",
                "unit": "mg",
                "title": "PRIVATE SCHEMA TITLE",
            },
            {
                "key": "arm",
                "type": "string",
                "unit": "",
                "enum": ["control", "treated"],
            },
            {"key": "included", "type": "boolean", "unit": ""},
            {"key": "unselected_private_field", "type": "object", "title": "Unrelated"},
        ],
        project_contract={},
        compute_contract={},
    )


def project_method(mode="relational"):
    row = builtin_method()
    row.engine_version = "airalogy.project-analysis.v1"
    row.protocol_id = row.protocol_version_id = None
    row.input_fields = []
    row.recipe = {
        "kind": "project",
        "schema_version": 1,
        "mode": mode,
        "slots": [
            {
                "slot_id": "treatment",
                "label": "Treatment",
                "recipe": {"numeric_fields": ["dose"]},
            },
            {
                "slot_id": "assay",
                "label": "Assay",
                "recipe": {"numeric_fields": ["response"]},
            },
        ],
    }
    if mode == "relational":
        row.recipe["join"] = {
            "left_slot_id": "treatment",
            "right_slot_id": "assay",
            "kind": "left",
            "keys": [{"left_field": "sample_id", "right_field": "specimen_id"}],
            "semantic_alignment_confirmed": True,
            "outputs": [
                {
                    "output_id": "viability",
                    "slot_id": "assay",
                    "field": "response",
                    "semantic_label": "Viability",
                    "unit": "%",
                }
            ],
            "recipe": {"numeric_fields": ["viability"]},
        }
    slots = []
    for index, (slot_id, label, key, field, unit) in enumerate(
        [
            ("treatment", "Treatment", "sample_id", "dose", "mg"),
            ("assay", "Assay", "specimen_id", "response", "%"),
        ]
    ):
        protocol_id = str(UUID(int=300 + index))
        schema = {
            "id": str(UUID(int=400 + index)),
            "version": "1.0.0",
            "json_schema": {
                "type": "object",
                "properties": {
                    key: {"type": "string"},
                    field: {
                        "type": "number",
                        "unit": unit,
                        "description": "PRIVATE SCHEMA DESCRIPTION",
                    },
                    "unselected_private_field": {
                        "type": "object",
                        "properties": {"private": {"type": "string"}},
                    },
                },
            },
            "fields": {},
        }
        schema["schema_digest"] = canonical_digest(
            {**schema, "protocol_id": protocol_id}
        )
        slots.append(
            {
                "slot_id": slot_id,
                "label": label,
                "protocol_id": protocol_id,
                "versions": [schema],
            }
        )
    row.project_contract = {"schema_version": 1, "slots": slots}
    return row


def build(method=None, **request):
    return packages.build_analysis_protocol_package(
        method or builtin_method(),
        {
            "uid": "analysis_method",
            "name": "A reviewed method",
            "locale": "en",
            **request,
        },
    )


def rewrite_manifest(package, transform):
    manifest = deepcopy(package.manifest)
    transform(manifest)
    return {**package.files, "analysis-method.json": json.dumps(manifest)}


def zip_files(
    files,
    *,
    timestamp=(2026, 9, 14, 10, 0, 0),
    mode=None,
    compression=zipfile.ZIP_DEFLATED,
):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, text in files.items():
            entry = zipfile.ZipInfo(name, timestamp)
            entry.compress_type = compression
            entry.create_system = 3
            if mode is not None:
                entry.external_attr = mode << 16
            archive.writestr(entry, text if isinstance(text, bytes) else text.encode())
    return output.getvalue()


@pytest.mark.parametrize(
    "factory",
    [builtin_method, project_method, lambda: project_method("evidence_synthesis")],
)
def test_package_strips_source_identities_and_unrelated_schema(factory):
    row = factory()
    before = deepcopy(vars(row))
    package = build(row)
    assert vars(row) == before
    assert set(package.files) == packages.PACKAGE_FILES
    text = "\n".join(package.files.values())
    for value in (
        "PRIVATE",
        "unselected_private_field",
        str(row.id),
        str(row.project_id),
        str(row.source_pipeline_revision_id),
    ):
        assert value not in text
    for slot in row.project_contract.get("slots", []):
        assert slot["protocol_id"] not in text
        assert slot["versions"][0]["id"] not in text
        assert slot["versions"][0]["schema_digest"] not in text
    for field in ("protocol_id", "protocol_version_id"):
        if getattr(row, field):
            assert str(getattr(row, field)) not in text
    assert "source_pipeline_revision_id" not in text
    assert "analysis_run_reference" in package.files["protocol.aimd"]
    assert package.manifest["schema"] == packages.MANIFEST_SCHEMA


def test_builtin_exports_only_recipe_fields_and_normalized_meaning():
    manifest = build().manifest
    assert [field["key"] for field in manifest["inputs"][0]["fields"]] == [
        "arm",
        "dose",
        "included",
    ]
    assert manifest["inputs"][0]["fields"][0]["enum"] == ["control", "treated"]
    assert manifest["inputs"][0]["fields"][1] == {
        "key": "dose",
        "type": "number",
        "unit": "mg",
    }
    assert manifest["recipe"]["filters"][0]["value"] is True


@pytest.mark.parametrize(
    "mode,expected",
    [
        (
            "relational",
            {"treatment": {"sample_id", "dose"}, "assay": {"specimen_id", "response"}},
        ),
        ("evidence_synthesis", {"treatment": {"dose"}, "assay": {"response"}}),
    ],
)
def test_project_preserves_required_join_contract_but_not_unrelated_fields(
    mode, expected
):
    package = build(project_method(mode))
    assert {
        item["slot_id"]: {field["key"] for field in item["fields"]}
        for item in package.manifest["inputs"]
    } == expected
    if mode == "relational":
        assert package.manifest["recipe"]["join"]["kind"] == "left"
        assert package.manifest["recipe"]["join"]["outputs"][0]["unit"] == "%"


def test_text_digest_does_not_depend_on_zip_timestamps_or_entry_order():
    package = build()
    first = packages.read_analysis_protocol_package_zip(zip_files(package.files))
    second = packages.read_analysis_protocol_package_zip(
        zip_files(
            dict(reversed(list(package.files.items()))),
            timestamp=(1990, 1, 1, 0, 0, 0),
            compression=zipfile.ZIP_STORED,
        )
    )
    assert first == second == package
    assert packages.analysis_protocol_package_zip_bytes(
        package
    ) == packages.analysis_protocol_package_zip_bytes(package)
    assert (
        packages.read_analysis_protocol_package_zip(
            packages.analysis_protocol_package_zip_bytes(package)
        )
        == package
    )


def test_review_seal_covers_exact_editable_text_and_metadata():
    package = build()
    for filename, changed in [
        (
            "protocol.aimd",
            package.files["protocol.aimd"] + "\nReviewed local procedure.\n",
        ),
        (
            "protocol.toml",
            package.files["protocol.toml"].replace(
                'version = "0.1.0"', 'version = "0.2.0"'
            ),
        ),
        ("analysis-method.json", json.dumps(package.manifest, separators=(",", ":"))),
    ]:
        updated = packages.validate_analysis_protocol_package(
            {**package.files, filename: changed},
            expected_manifest_digest=package.manifest_digest,
        )
        assert updated.content_digest != package.content_digest
        assert updated.manifest_digest == package.manifest_digest
    files = rewrite_manifest(package, lambda item: item["recipe"].update(chart="none"))
    with pytest.raises(packages.AnalysisProtocolPackageError, match="manifest changed"):
        packages.validate_analysis_protocol_package(
            files, expected_manifest_digest=package.manifest_digest
        )


def test_zip_writer_rejects_mutation_after_validation():
    package = build()
    package.files["protocol.aimd"] += "\nChanged after review\n"
    with pytest.raises(
        packages.AnalysisProtocolPackageError, match="changed after validation"
    ):
        packages.analysis_protocol_package_zip_bytes(package)


@pytest.mark.parametrize(
    "filename",
    [
        "../protocol.aimd",
        "nested/protocol.aimd",
        "/protocol.aimd",
        "protocol.aimd/",
        "model.py",
        "assigner.py",
        ".env",
        "PROTOCOL.aimd",
    ],
)
def test_extra_or_unsafe_zip_paths_are_rejected(filename):
    files = {**build().files, filename: "unsafe"}
    with pytest.raises(packages.AnalysisProtocolPackageError):
        packages.read_analysis_protocol_package_zip(zip_files(files))


def test_duplicate_zip_entry_rejected():
    package = build()
    data = io.BytesIO(zip_files(package.files))
    with (
        zipfile.ZipFile(data, "a") as archive,
        pytest.warns(UserWarning, match="Duplicate name"),
    ):
        archive.writestr("protocol.aimd", "# replacement")
    with pytest.raises(packages.AnalysisProtocolPackageError):
        packages.read_analysis_protocol_package_zip(data.getvalue())


@pytest.mark.parametrize(
    "mode", [stat.S_IFLNK | 0o777, stat.S_IFDIR | 0o755, stat.S_IFIFO | 0o644]
)
def test_zip_special_files_rejected(mode):
    with pytest.raises(packages.AnalysisProtocolPackageError):
        packages.read_analysis_protocol_package_zip(zip_files(build().files, mode=mode))


def test_archive_size_text_limits_and_encoding():
    package = build()
    for files in [
        {**package.files, "protocol.aimd": "x" * (packages.MAX_FILE_BYTES + 1)},
        {**package.files, "protocol.aimd": "\x00"},
        {**package.files, "protocol.aimd": b"\xff"},
    ]:
        with pytest.raises(packages.AnalysisProtocolPackageError):
            packages.read_analysis_protocol_package_zip(zip_files(files))
    with pytest.raises(packages.AnalysisProtocolPackageError):
        packages.read_analysis_protocol_package_zip(b"x" * (packages.MAX_ZIP_BYTES + 1))
    with pytest.raises(packages.AnalysisProtocolPackageError):
        packages.read_analysis_protocol_package_zip(b"not a zip")


@pytest.mark.parametrize(
    "change",
    [
        lambda item: item.update(protocol_id=str(UUID(int=1))),
        lambda item: item["inputs"][0].update(versions=[]),
        lambda item: item["inputs"][0]["fields"][0].update(description="Private"),
        lambda item: item["inputs"][0]["fields"].append(
            {"key": "unused", "type": "number", "unit": ""}
        ),
        lambda item: item["inputs"][0]["fields"].append(
            deepcopy(item["inputs"][0]["fields"][0])
        ),
        lambda item: item["recipe"].update(schema_version=True),
        lambda item: item.update(engine_version="airalogy.compute.v1"),
        lambda item: item.pop("schema"),
    ],
)
def test_strict_manifest_rejects_injected_or_inconsistent_contracts(change):
    with pytest.raises(packages.AnalysisProtocolPackageError):
        packages.validate_analysis_protocol_package(rewrite_manifest(build(), change))


@pytest.mark.parametrize(
    "change",
    [
        lambda item: item["inputs"][0]["fields"].pop(),
        lambda item: item["inputs"][0].update(label="wrong slot label"),
        lambda item: item["recipe"]["join"]["outputs"][0].update(unit="g"),
        lambda item: item["recipe"]["join"]["keys"][0].update(left_field="absent"),
        lambda item: item["inputs"][0]["fields"][-1].update(type="integer"),
    ],
)
def test_project_manifest_rechecks_full_join_meaning(change):
    with pytest.raises(packages.AnalysisProtocolPackageError):
        packages.validate_analysis_protocol_package(
            rewrite_manifest(build(project_method()), change)
        )


def test_duplicate_json_keys_and_nonfinite_filters_rejected():
    package = build()
    for manifest in [
        package.files["analysis-method.json"].replace(
            '"chart": "bar"', '"chart": "bar", "chart": "none"'
        ),
        package.files["analysis-method.json"].replace('"value": true', '"value": NaN'),
    ]:
        with pytest.raises(packages.AnalysisProtocolPackageError):
            packages.validate_analysis_protocol_package(
                {**package.files, "analysis-method.json": manifest}
            )


def test_compute_and_invalid_published_schemas_fail_without_placeholders():
    row = builtin_method()
    row.engine_version = "airalogy.compute.v1"
    with pytest.raises(
        packages.AnalysisProtocolPackageError, match="Compute is not supported"
    ):
        build(row)
    row = project_method()
    row.project_contract["slots"][0]["versions"][0]["json_schema"]["properties"][
        "dose"
    ]["unit"] = "g"
    with pytest.raises(packages.AnalysisProtocolPackageError):
        build(row)


@pytest.mark.parametrize(
    "aimd",
    [
        "# Bad\n{{var|broken name: str}}",
        '# Bad\n{{var|value: __import__("os").getcwd()}}',
        '# Bad\n{{var|value: str, default_factory=__import__("os").getcwd}}',
        "# Bad\n```assigner\ndef calculate():\n    return 1\n```",
    ],
)
def test_editable_aimd_does_not_allow_inline_execution(aimd):
    with pytest.raises(packages.AnalysisProtocolPackageError):
        packages.validate_analysis_protocol_package(
            {**build().files, "protocol.aimd": aimd}
        )


def test_untrusted_labels_and_names_are_prose_not_new_fields():
    name = "<script>bad</script> {{var|secret: str}} | ` ```"
    package = build(name=name)
    assert "{{var|secret: str}}" not in package.files["protocol.aimd"]
    assert "<script>" not in package.files["protocol.aimd"]
    assert package.metadata["name"] == name


def test_ordinary_code_example_is_prose_not_an_assigner():
    package = build()
    text = (
        package.files["protocol.aimd"]
        + '\n```python\nraise RuntimeError("DO NOT EXECUTE")\n```\n'
    )
    edited = packages.validate_analysis_protocol_package(
        {**package.files, "protocol.aimd": text}
    )
    assert edited.manifest_digest == package.manifest_digest


@pytest.mark.parametrize(
    "metadata",
    [
        '[airalogy_protocol]\nid="bad"\nname="Example"\nversion="0.1.0"',
        '[airalogy_protocol]\nid="test"\nname="Example"\nversion="latest"',
        '[airalogy_protocol]\nid="test"\nname="Example"\nversion="0.1.0"\nkind="resource_definition"',
        '[airalogy_protocol]\nid="test"\nname="Example"\nversion="0.1.0"\n[environment]\ncommand="python"',
    ],
)
def test_protocol_metadata_rejects_out_of_scope_contracts(metadata):
    with pytest.raises(packages.AnalysisProtocolPackageError):
        packages.validate_analysis_protocol_package(
            {**build().files, "protocol.toml": metadata}
        )
