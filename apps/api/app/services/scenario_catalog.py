"""Release-bundled scenario content. Catalog entries never execute client code."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from pydantic import BaseModel, ConfigDict, Field


class ModuleRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]+$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")


class KitManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]+$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    name: dict[str, str]
    description: dict[str, str]
    modules: tuple[ModuleRequirement, ...]
    license: str = "Apache-2.0"
    source: str = "airalogy/platform"
    platform_min: str = "0.3.1"
    platform_max_exclusive: str = "1.0.0"
    components: tuple[str, ...] = ("airalogy.sample.v1", "measurement")
    external_services: tuple[str, ...] = ()


MODULES = {
    "airalogy.samples": "1.0.0",
    "airalogy.records": "1.0.0",
    "airalogy.analysis": "1.0.0",
}
KIT_NAMES = {
    "airalogy.sample-results": {
        "zh-CN": "样品与数值结果",
        "en-US": "Samples and numerical results",
    },
    "airalogy.material-results": {
        "zh-CN": "材料样品与数值结果",
        "en-US": "Material samples and numerical results",
    },
}


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def manifest(kit_id: str, version: str) -> dict:
    if kit_id not in KIT_NAMES or version not in {"1.0.0", "1.1.0"}:
        raise ValueError("Unknown kit or version")
    value = KitManifest(
        id=kit_id,
        version=version,
        name=KIT_NAMES[kit_id],
        description={
            "zh-CN": "登记样品，关联实验记录，按模板导入数值结果并生成可追溯分析。不预设实验判定规则。",
            "en-US": "Register samples, link experiments, import numerical results and analyze their sources. No assay-specific decision rules.",
        },
        modules=tuple(
            ModuleRequirement(id=key, version=value) for key, value in MODULES.items()
        ),
    ).model_dump(mode="json")
    value["content_digest"] = digest(
        {
            "sample": template_files("sample", "scenario_sample", "1.0.0"),
            "measurement": template_files(
                "measurement", "scenario_measurement", version
            ),
        }
    )
    value["digest"] = digest(value)
    return value


def availability(
    value: dict, *, enabled_modules: set[str], platform_version: str
) -> list[str]:
    errors = []
    try:
        compatible = (
            version_tuple(value["platform_min"])
            <= version_tuple(platform_version)
            < version_tuple(value["platform_max_exclusive"])
        )
    except ValueError:
        compatible = False
    if not compatible:
        errors.append("platform_version")
    seen = set()
    for requirement in value["modules"]:
        key = requirement["id"]
        if key in seen:
            errors.append(f"duplicate_dependency:{key}")
        seen.add(key)
        if key not in enabled_modules:
            errors.append(f"module_disabled:{key}")
        elif MODULES.get(key) != requirement["version"]:
            errors.append(f"module_version:{key}")
    return errors


def catalog() -> list[dict]:
    return [
        manifest(key, version) for key in KIT_NAMES for version in ("1.0.0", "1.1.0")
    ]


def template_files(component: str, uid: str, version: str) -> dict[str, str]:
    """Only trusted, bundled source; no supplied Python or scientific inference."""
    if component == "sample":
        name, kind = "Sample / 样品", "resource_definition"
        aimd = "# Sample / 样品\n\nCategory / 类别: {{var|category: str}}\n\nSource / 来源: {{var|source: str | None}}\n\nStorage / 保存条件: {{var|storage: str | None}}\n"
        model = """from pydantic import BaseModel, ConfigDict, Field

class VarModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category: str = Field(min_length=1, max_length=128)
    source: str | None = Field(default=None, max_length=1000)
    storage: str | None = Field(default=None, max_length=1000)
"""
    elif component == "measurement":
        name, kind = "Sample measurement / 样品测量", "experiment"
        aimd = """# Sample measurement / 样品测量

Record the actual method, unit and result. No automatic scientific interpretation.
记录实际方法、单位和结果；本模板不自动作出科学判定。

Sample / 样品: {{var|sample: ResourceRef["airalogy_sample_v1"], resource_role="reference"}}

Method / 方法: {{var|method: str}}

Metric / 指标: {{var|metric: str}}

Value / 数值: {{var|value: float}}

Unit / 单位: {{var|unit: str}}

Measured at / 测量时间: {{var|measured_at: datetime}}
"""
        model = """from datetime import datetime
from airalogy.types import ResourceRef
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

class VarModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    sample: ResourceRef["airalogy_sample_v1"]
    method: str = Field(min_length=1, max_length=255)
    metric: str = Field(min_length=1, max_length=128)
    value: FiniteFloat
    unit: str = Field(min_length=1, max_length=64)
    measured_at: datetime
"""
        if version == "1.1.0":
            aimd += "\nNotes / 备注: {{var|notes: str | None}}\n"
            model += "    notes: str | None = Field(default=None, max_length=4000)\n"
    else:
        raise ValueError("Unknown bundled component")
    metadata = {
        "id": uid,
        "name": name,
        "version": version,
        "kind": kind,
        "license": "Apache-2.0",
    }
    toml = "[airalogy_protocol]\n" + "".join(
        f"{key} = {json.dumps(value, ensure_ascii=False)}\n"
        for key, value in metadata.items()
    )
    return {"protocol.aimd": aimd, "protocol.toml": toml, "model.py": model}


def analysis_recipe() -> dict:
    # Different methods, metrics and units must never be silently pooled.
    return deepcopy(
        {
            "numeric_fields": ["value"],
            "group_by": ["method", "metric", "unit"],
            "filters": [],
            "missing_policy": "error",
            "chart": "bar",
        }
    )
