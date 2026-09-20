"""Portable, declarative Protocol drafts for explicitly published analysis methods.

Authorization, protected lineage, review and publication belong to the caller.
This compiler never executes an analysis or exports its source identities/data.
The three text files are ordinary editable Protocol assets; the manifest is a
recipe, not an assigner, a result, or a portable grant to the original inputs.
"""

from __future__ import annotations

import ast
import hashlib
import html
import io
import json
import stat
import tomllib
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from airalogy.markdown import generate_model, parse_aimd
from airalogy.markdown.errors import AimdParseError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.analysis_engine import (
    ENGINE_VERSION,
    AnalysisRecipe,
    Scalar,
    canonical_digest,
    resolve_field_catalog,
    validate_recipe,
)
from app.services.project_analysis_engine import (
    ENGINE_VERSION as PROJECT_ENGINE_VERSION,
)
from app.services.project_analysis_engine import ProjectAnalysisRecipe
from app.services.workflow_analysis_contracts import validate_project_method_inputs

MANIFEST_SCHEMA = "airalogy.analysis-protocol-method.v1"
PACKAGE_SCHEMA = "airalogy.analysis-protocol-package.v1"
PACKAGE_FILES = frozenset({"protocol.toml", "protocol.aimd", "analysis-method.json"})
MAX_FILE_BYTES = 512 * 1024
MAX_PACKAGE_BYTES = 1024 * 1024
MAX_ZIP_BYTES = MAX_PACKAGE_BYTES + 64 * 1024


class AnalysisProtocolPackageError(ValueError):
    """The draft exceeds the portable, non-executable package contract."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AnalysisProtocolPackageRequest(_Strict):
    uid: str = Field(pattern=r"^[a-z][a-z0-9_]*$", min_length=4, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(default="0.1.0", pattern=r"^\d{1,3}(\.\d{1,3}){2}$")
    locale: Literal["zh", "en"] = "zh"

    @field_validator("name")
    @classmethod
    def meaningful_name(cls, value):
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("Protocol name must be nonblank single-line text")
        return value


class _Metadata(_Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$", min_length=4, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(pattern=r"^\d{1,3}(\.\d{1,3}){2}$")
    kind: Literal["experiment"] = "experiment"
    description: str | None = Field(default=None, max_length=8_000)
    license: str | None = Field(default=None, max_length=255)
    keywords: list[str] | None = Field(default=None, max_length=32)
    disciplines: list[str] | None = Field(default=None, max_length=32)

    @field_validator("name")
    @classmethod
    def meaningful_name(cls, value):
        return AnalysisProtocolPackageRequest.meaningful_name(value)

    @field_validator("keywords", "disciplines")
    @classmethod
    def bounded_labels(cls, values):
        if values is not None and any(
            not item.strip() or len(item) > 255 for item in values
        ):
            raise ValueError("Metadata labels require 1 to 255 characters")
        return values


class AnalysisProtocolInputField(_Strict):
    key: str = Field(min_length=1, max_length=255)
    type: Literal["number", "integer", "string", "boolean"]
    unit: str = Field(default="", max_length=255)
    enum: list[Scalar] | None = Field(default=None, min_length=1, max_length=512)


class AnalysisProtocolInput(_Strict):
    slot_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    label: str = Field(min_length=1, max_length=255)
    fields: list[AnalysisProtocolInputField] = Field(min_length=1, max_length=80)


class AnalysisProtocolManifest(_Strict):
    schema_id: Literal[MANIFEST_SCHEMA] = Field(alias="schema")
    engine_version: Literal[ENGINE_VERSION, PROJECT_ENGINE_VERSION]
    recipe: AnalysisRecipe | ProjectAnalysisRecipe
    inputs: list[AnalysisProtocolInput] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def exact_contract(self):
        if len({item.slot_id for item in self.inputs}) != len(self.inputs):
            raise ValueError("Portable input slots cannot repeat")
        catalogs = {}
        for item in self.inputs:
            names = {field.key for field in item.fields}
            if len(names) != len(item.fields):
                raise ValueError("Portable input fields cannot repeat")
            raw = [field.model_dump(exclude_none=True) for field in item.fields]
            catalogs[item.slot_id] = resolve_field_catalog(raw, names)
        if self.engine_version == ENGINE_VERSION:
            if not isinstance(self.recipe, AnalysisRecipe) or len(self.inputs) != 1:
                raise ValueError(
                    "Builtin analysis requires one input and builtin recipe"
                )
            if self.inputs[0].slot_id != "records" or self.inputs[0].label != "Records":
                raise ValueError("Builtin portable input must be the records slot")
            expected = validate_recipe(self.recipe, list(catalogs["records"].values()))
            if set(expected) != set(catalogs["records"]):
                raise ValueError("Portable inputs must not include unused fields")
        else:
            if not isinstance(self.recipe, ProjectAnalysisRecipe):
                raise ValueError("Project engine requires a Project recipe")
            _validate_portable_project(self.recipe, self.inputs, catalogs)
        return self


@dataclass(frozen=True)
class AnalysisProtocolPackage:
    files: dict[str, str]
    metadata: dict[str, Any]
    manifest: dict[str, Any]
    content_digest: str
    manifest_digest: str


def _references(recipe):
    return set(recipe.numeric_fields + recipe.group_by) | {
        item.field for item in recipe.filters
    }


def _validate_portable_project(recipe, inputs, catalogs):
    """Validate portable scalar contracts without manufacturing source Schemas.

    Scientific operations use the existing validators. The small join checks
    below compare declarations only; they never create source/Record identities.
    """
    slots = {slot.slot_id: slot for slot in recipe.slots}
    if set(catalogs) != set(slots) or any(
        item.label != slots[item.slot_id].label for item in inputs
    ):
        raise ValueError("Portable inputs must match the Project slots and labels")
    referenced = {key: _references(slot.recipe) for key, slot in slots.items()}
    for key, slot in slots.items():
        validate_recipe(slot.recipe, list(catalogs[key].values()))
    if recipe.join:
        plan = recipe.join
        for key in plan.keys:
            referenced[plan.left_slot_id].add(key.left_field)
            referenced[plan.right_slot_id].add(key.right_field)
            left = catalogs[plan.left_slot_id][key.left_field]
            right = catalogs[plan.right_slot_id][key.right_field]
            if left["type"] != right["type"] or left["unit"] != right["unit"]:
                raise ValueError("Join keys require exact types and units")
        outputs = []
        for output in plan.outputs:
            referenced[output.slot_id].add(output.field)
            field = catalogs[output.slot_id][output.field]
            if (output.unit or "") != field["unit"]:
                raise ValueError("Join output units must equal the input units")
            outputs.append({**field, "key": output.output_id})
        validate_recipe(plan.recipe, outputs)
    if any(set(catalogs[key]) != fields for key, fields in referenced.items()):
        raise ValueError("Portable inputs must contain exactly the referenced fields")


def _json(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    )


def _text(value):
    # Labels are untrusted data, never AIMD templates, code fences or HTML.
    return (
        html.escape(value, quote=True)
        .replace("{", "&#123;")
        .replace("}", "&#125;")
        .replace("|", "&#124;")
        .replace("`", "&#96;")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def _aimd(request, manifest):
    if request.locale == "zh":
        intro = """> 这是可编辑的分析方法 Protocol，不是已执行的分析或科学结论。发布不会运行计算，也不会复制或授权原始数据。

## 方法与输入

准确的统计、筛选、分组、缺失值策略及关联规则保存在 `analysis-method.json`。字段标签、枚举和筛选常量可能包含科研信息；请在审核和共享前检查完整文件。

使用已发布的方法，在分析工作区或 Workflow 中明确选择当前有权访问的真实输入，预览后确认执行。不要把此说明文字作为程序执行；本包不包含 Python 或自动赋值器。

### 必要字段契约
"""
        closing = """
## 执行与留痕

完成真实分析后再填写，不要预填或编造结果。

分析运行引用：{{var|analysis_run_reference: str, min_length=1}}

执行说明：{{var|execution_notes: str, min_length=1}}

局限与后续：{{var|limitations: str = ""}}

结果及科学判断仍须按正常 Evidence / Knowledge 审核流程处理；提交此 Record 不代表原始分析结果已获审核。
"""
    else:
        intro = """> This editable analysis-method Protocol is not a completed analysis or a scientific conclusion. Publication neither runs calculations nor copies or authorizes original data.

## Method and inputs

The exact statistics, filters, groups, missing-value policy and join rules are in `analysis-method.json`. Labels, enums and filter constants may contain research information: review the complete files before sharing.

Use the published method in the analysis workspace or a Workflow, explicitly select real inputs you may currently access, preview, and confirm execution. Do not execute this prose as a program. This package contains no Python or assigner.

### Required field contracts
"""
        closing = """
## Execution and traceability

Complete these fields after a real analysis. Do not prefill or invent results.

Analysis run reference: {{var|analysis_run_reference: str, min_length=1}}

Execution notes: {{var|execution_notes: str, min_length=1}}

Limitations and next steps: {{var|limitations: str = ""}}

Results and scientific interpretations still require the ordinary Evidence / Knowledge review. Submitting this Record does not validate the original analysis result.
"""
    sections = [f"# {_text(request.name)}\n\n", intro]
    for slot in manifest["inputs"]:
        sections.append(
            f"\n#### {_text(slot['label'])}\n\n| Field | Type | Unit |\n| --- | --- | --- |\n"
        )
        sections.extend(
            f"| {_text(field['key'])} | {field['type']} | {_text(field['unit'])} |\n"
            for field in slot["fields"]
        )
    return "".join(sections) + closing


def _portable_fields(fields):
    return [
        {key: field[key] for key in ("key", "type", "unit", "enum") if key in field}
        for field in sorted(fields, key=lambda item: item["key"])
    ]


def build_analysis_protocol_package(
    method: Any,
    request: AnalysisProtocolPackageRequest | dict,
) -> AnalysisProtocolPackage:
    """Compile an already authorized, verified WorkflowAnalysisMethod.

    The caller MUST use get_method before calling, and store lineage separately.
    Compute packages need a governed portable environment/code contract; this
    version deliberately refuses them instead of disguising scripts as prose.
    """
    try:
        request = AnalysisProtocolPackageRequest.model_validate(
            request.model_dump()
            if isinstance(request, AnalysisProtocolPackageRequest)
            else request
        )
        if method.engine_version == ENGINE_VERSION:
            if getattr(method, "project_contract", {}) or getattr(
                method, "compute_contract", {}
            ):
                raise ValueError("Builtin method has an unexpected engine contract")
            recipe = AnalysisRecipe.model_validate(method.recipe)
            fields = validate_recipe(recipe, method.input_fields)
            inputs = [
                {
                    "slot_id": "records",
                    "label": "Records",
                    "fields": _portable_fields(fields.values()),
                }
            ]
        elif method.engine_version == PROJECT_ENGINE_VERSION:
            if getattr(method, "compute_contract", {}) or method.input_fields:
                raise ValueError("Project method has an unexpected engine contract")
            recipe = ProjectAnalysisRecipe.model_validate(method.recipe)
            fields = validate_project_method_inputs(recipe, method.project_contract)
            inputs = [
                {
                    "slot_id": slot.slot_id,
                    "label": slot.label,
                    "fields": _portable_fields(fields[slot.slot_id]),
                }
                for slot in recipe.slots
            ]
        else:
            raise AnalysisProtocolPackageError(
                "Unsupported analysis engine for Protocol promotion; Compute is not supported"
            )
        manifest = AnalysisProtocolManifest.model_validate(
            {
                "schema": MANIFEST_SCHEMA,
                "engine_version": method.engine_version,
                "recipe": recipe.model_dump(mode="json"),
                "inputs": inputs,
            }
        ).model_dump(mode="json", exclude_none=True, by_alias=True)
        metadata = {
            "id": request.uid,
            "name": request.name,
            "version": request.version,
            "kind": "experiment",
        }
        toml = "[airalogy_protocol]\n" + "".join(
            f"{key} = {json.dumps(value, ensure_ascii=False)}\n"
            for key, value in metadata.items()
        )
        return validate_analysis_protocol_package(
            {
                "protocol.toml": toml,
                "protocol.aimd": _aimd(request, manifest),
                "analysis-method.json": _json(manifest),
            }
        )
    except AnalysisProtocolPackageError:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OverflowError,
        RecursionError,
    ) as error:
        raise AnalysisProtocolPackageError(
            "Invalid published analysis method or package metadata"
        ) from error


def _safe_annotation(node):
    if isinstance(node, ast.Name):
        return node.id in {
            "str",
            "int",
            "float",
            "bool",
            "list",
            "dict",
            "tuple",
            "set",
            "Literal",
        }
    if isinstance(node, ast.Constant):
        return node.value is None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _safe_annotation(node.left) and _safe_annotation(node.right)
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        if node.value.id == "Literal":
            try:
                ast.literal_eval(node.slice)
                return True
            except (ValueError, TypeError):
                return False
        elements = (
            node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        )
        return node.value.id in {"list", "dict", "tuple", "set"} and all(
            _safe_annotation(item) for item in elements
        )
    return False


def _validate_aimd(text):
    """Parse, but never execute, the same model the executor would generate."""
    parsed = parse_aimd(text)
    templates = parsed["templates"]
    if any(
        templates.get(kind)
        for kind in ("assigner", "connectors", "collectors", "workflow")
    ):
        raise AnalysisProtocolPackageError(
            "Analysis Protocol drafts cannot embed executable or connected blocks"
        )
    tree = ast.parse(generate_model(text))
    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom):
            allowed = {"pydantic": {"BaseModel", "Field"}, "typing": {"Literal"}}
            if (
                statement.level
                or statement.module not in allowed
                or any(
                    item.asname or item.name not in allowed[statement.module]
                    for item in statement.names
                )
            ):
                raise AnalysisProtocolPackageError(
                    "AIMD inputs must use declarative builtin types"
                )
        elif isinstance(statement, ast.ClassDef):
            if (
                statement.decorator_list
                or statement.keywords
                or len(statement.bases) != 1
                or not isinstance(statement.bases[0], ast.Name)
                or statement.bases[0].id != "BaseModel"
            ):
                raise AnalysisProtocolPackageError(
                    "AIMD models cannot execute custom code"
                )
            for member in statement.body:
                if (
                    isinstance(member, ast.Pass)
                    or isinstance(member, ast.Expr)
                    and isinstance(member.value, ast.Constant)
                    and isinstance(member.value.value, str)
                ):
                    continue
                if (
                    not isinstance(member, ast.AnnAssign)
                    or not isinstance(member.target, ast.Name)
                    or not _safe_annotation(member.annotation)
                ):
                    raise AnalysisProtocolPackageError(
                        "AIMD fields require declarative builtin type annotations"
                    )
                value = member.value
                if value is None:
                    continue
                if (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id == "Field"
                    and not value.args
                ):
                    for keyword in value.keywords:
                        if keyword.arg is None:
                            raise AnalysisProtocolPackageError(
                                "AIMD fields cannot expand executable arguments"
                            )
                        ast.literal_eval(keyword.value)
                else:
                    ast.literal_eval(value)
        elif not (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            raise AnalysisProtocolPackageError("AIMD models cannot execute custom code")


def _unique_json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AnalysisProtocolPackageError("Duplicate JSON keys are not allowed")
        result[key] = value
    return result


def validate_analysis_protocol_package(
    files: Mapping[str, str],
    *,
    expected_manifest_digest: str | None = None,
) -> AnalysisProtocolPackage:
    """Validate edited text and bind its exact bytes for review.

    A supplied expected manifest seal makes the scientific recipe immutable;
    metadata/AIMD changes still create a different content seal and need review.
    """
    try:
        if not isinstance(files, Mapping) or set(files) != PACKAGE_FILES:
            raise AnalysisProtocolPackageError(
                "Package requires exactly the three root-level Protocol text files"
            )
        copied, encoded = {}, {}
        for name in sorted(PACKAGE_FILES):
            value = files[name]
            if not isinstance(value, str) or not value.strip() or "\x00" in value:
                raise AnalysisProtocolPackageError(
                    "Package files must be nonempty UTF-8 text without NUL bytes"
                )
            content = value.encode("utf-8")
            if len(content) > MAX_FILE_BYTES:
                raise AnalysisProtocolPackageError(
                    "Protocol package file exceeds its byte limit"
                )
            copied[name], encoded[name] = value, content
        if sum(map(len, encoded.values())) > MAX_PACKAGE_BYTES:
            raise AnalysisProtocolPackageError(
                "Protocol package exceeds its total byte limit"
            )
        parsed_toml = tomllib.loads(copied["protocol.toml"])
        if set(parsed_toml) != {"airalogy_protocol"}:
            raise AnalysisProtocolPackageError(
                "Protocol metadata must have one airalogy_protocol table"
            )
        metadata = _Metadata.model_validate(
            parsed_toml["airalogy_protocol"]
        ).model_dump(exclude_none=True)
        manifest = AnalysisProtocolManifest.model_validate(
            json.loads(
                copied["analysis-method.json"], object_pairs_hook=_unique_json_pairs
            )
        ).model_dump(mode="json", exclude_none=True, by_alias=True)
        manifest_digest = canonical_digest(manifest)
        if (
            expected_manifest_digest is not None
            and manifest_digest != expected_manifest_digest
        ):
            raise AnalysisProtocolPackageError(
                "Analysis manifest changed; publish a new method before changing its recipe"
            )
        _validate_aimd(copied["protocol.aimd"])
        digest = canonical_digest(
            {
                "schema": PACKAGE_SCHEMA,
                "files": [
                    {
                        "path": name,
                        "bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                    for name, content in encoded.items()
                ],
            }
        )
        return AnalysisProtocolPackage(
            copied, metadata, manifest, digest, manifest_digest
        )
    except AnalysisProtocolPackageError:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OverflowError,
        RecursionError,
        SyntaxError,
        AimdParseError,
    ) as error:
        raise AnalysisProtocolPackageError(
            "Invalid declarative analysis Protocol package"
        ) from error


def read_analysis_protocol_package_zip(
    data: bytes,
    *,
    expected_manifest_digest: str | None = None,
) -> AnalysisProtocolPackage:
    """Read bounded ZIP bytes in memory; never extract user-controlled paths."""
    try:
        if not isinstance(data, bytes) or not data or len(data) > MAX_ZIP_BYTES:
            raise AnalysisProtocolPackageError("Protocol ZIP exceeds its byte limit")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if (
                len(entries) != 3
                or {item.filename for item in entries} != PACKAGE_FILES
            ):
                raise AnalysisProtocolPackageError(
                    "ZIP must contain exactly three unique root-level files"
                )
            if sum(item.file_size for item in entries) > MAX_PACKAGE_BYTES:
                raise AnalysisProtocolPackageError(
                    "Expanded Protocol ZIP exceeds its byte limit"
                )
            files = {}
            for item in entries:
                mode = item.external_attr >> 16
                if (
                    item.orig_filename != item.filename
                    or item.is_dir()
                    or item.flag_bits & 1
                    or item.compress_type
                    not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    or stat.S_IFMT(mode) not in {0, stat.S_IFREG}
                    or item.file_size > MAX_FILE_BYTES
                ):
                    raise AnalysisProtocolPackageError(
                        "ZIP contains an unsupported file entry"
                    )
                with archive.open(item) as stream:
                    raw = stream.read(MAX_FILE_BYTES + 1)
                if len(raw) != item.file_size or len(raw) > MAX_FILE_BYTES:
                    raise AnalysisProtocolPackageError(
                        "Expanded ZIP entry exceeds its declared size"
                    )
                files[item.filename] = raw.decode("utf-8")
        return validate_analysis_protocol_package(
            files, expected_manifest_digest=expected_manifest_digest
        )
    except AnalysisProtocolPackageError:
        raise
    except (
        zipfile.BadZipFile,
        OSError,
        ValueError,
        RuntimeError,
        NotImplementedError,
        EOFError,
    ) as error:
        raise AnalysisProtocolPackageError("Invalid analysis Protocol ZIP") from error


def analysis_protocol_package_zip_bytes(package: AnalysisProtocolPackage) -> bytes:
    """Revalidate the exact package before deterministic ZIP serialization."""
    verified = validate_analysis_protocol_package(
        package.files, expected_manifest_digest=package.manifest_digest
    )
    if verified.content_digest != package.content_digest:
        raise AnalysisProtocolPackageError("Protocol package changed after validation")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, text in sorted(verified.files.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(entry, text.encode("utf-8"))
    return output.getvalue()
