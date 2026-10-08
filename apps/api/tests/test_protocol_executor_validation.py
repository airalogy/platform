"""Exercise the real subprocess, generated AIMD model and custom model together."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = API_ROOT.parents[1] / "packages/components/src/monaco-editor/templates"
PACKAGE_NAME = "protocol_00000000-0000-0000-0000-000000000001"


def run_executor(
    tmp_path,
    action,
    values,
    *,
    locale="en",
    custom_model=None,
    name=PACKAGE_NAME,
    aimd=None,
):
    root = tmp_path / "isolated-storage"
    package = root / PACKAGE_NAME
    package.mkdir(parents=True, exist_ok=True)
    (package / "protocol.aimd").write_text(
        aimd or (TEMPLATES / f"first-record-{locale}.aimd").read_text(),
        encoding="utf-8",
    )
    (package / "protocol.toml").write_text(
        '[airalogy_protocol]\nid="practice"\nname="Practice"\nversion="0.1.0"\n'
    )
    if custom_model:
        (package / "model.py").write_text(custom_model)
    result = subprocess.run(
        [
            sys.executable,
            str(API_ROOT / "protocol_executor.py"),
            action,
            name,
            json.dumps(values),
        ],
        cwd=tmp_path,
        env={**os.environ, "PROTOCOL_DIR": str(root)},
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("locale", ["en", "zh"])
def test_teaching_template_is_executable_and_validated(tmp_path, locale):
    parsed = run_executor(
        tmp_path, "get_protocol_info", {"env_vars": {}}, locale=locale
    )
    assert parsed["success"], parsed
    assert set(parsed["data"]["json_schema"]["vars"]["required"]) == {
        "sample_label",
        "observation_count",
    }
    valid = run_executor(
        tmp_path,
        "var_validate",
        {"sample_label": "PRACTICE-001", "observation_count": 12},
        locale=locale,
    )
    assert valid["success"] and not valid["data"].get("errors"), valid
    invalid = run_executor(
        tmp_path, "var_validate", {"observation_count": -1}, locale=locale
    )
    assert {error["loc"][0] for error in invalid["data"]["errors"]} == {
        "sample_label",
        "observation_count",
    }


def test_custom_model_does_not_drop_aimd_only_fields(tmp_path):
    result = run_executor(
        tmp_path,
        "var_validate",
        {"observation_count": 1},
        custom_model="""
from pydantic import BaseModel, Field
class VarModel(BaseModel):
    observation_count: int = Field(ge=10)
""",
    )
    assert {error["loc"][0] for error in result["data"]["errors"]} == {
        "sample_label",
        "observation_count",
    }


CLIENT_AIMD = """# Synthetic client calculation
{{var|a: float, ge=0}}
{{var|b: float, ge=0}}
```assigner runtime=client
assigner(
  {mode: "auto", dependent_fields: ["a"], assigned_fields: ["b"]},
  function double_a({a}) { return {b: a * 2}; }
);
```
"""


def test_client_metadata_and_import_validation_use_real_executor(tmp_path):
    result = run_executor(
        tmp_path, "get_protocol_info", {"env_vars": {}}, aimd=CLIENT_AIMD
    )
    assert result["success"], result
    client = result["data"]["assigners"]["b"]
    assert client == {
        "id": "double_a",
        "runtime": "client",
        "mode": "auto",
        "dependent_fields": ["a"],
        "assigned_fields": ["b"],
    }
    assert ["a", "client:double_a"] in result["data"]["assigner_graph"]["edges"]
    assert not (tmp_path / "isolated-storage" / PACKAGE_NAME / "assigner.py").exists()
    missing = run_executor(tmp_path, "var_validate", {"a": 3}, aimd=CLIENT_AIMD)
    assert missing["data"]["errors"][0]["loc"] == ["b"]
    valid = run_executor(tmp_path, "var_validate", {"a": 3, "b": 6}, aimd=CLIENT_AIMD)
    assert valid["success"] and not valid["data"].get("errors"), valid


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.replace('["a"]', '["missing"]'),
        lambda s: s.replace('["a"]', '["b"]'),
        lambda s: s.replace('"auto"', '"auto_force"'),
        lambda s: s.replace("a * 2", 'fetch("https://example.invalid")'),
        lambda s: s + s[s.index("```assigner") :].replace("double_a", "duplicate"),
    ],
)
def test_invalid_client_contract_is_rejected_at_publication(tmp_path, change):
    result = run_executor(
        tmp_path, "get_protocol_info", {"env_vars": {}}, aimd=change(CLIENT_AIMD)
    )
    assert not result["success"], result


def test_mixed_runtime_dependency_graph_and_cycles(tmp_path):
    server = """
{{var|c: float}}
```assigner
from airalogy.assigner import assigner, AssignerResult
@assigner(assigned_fields=["c"], dependent_fields=["b"], mode="auto")
def triple_b(dep):
    return AssignerResult(assigned_fields={"c": dep["b"] * 3})
```
"""
    result = run_executor(
        tmp_path, "get_protocol_info", {"env_vars": {}}, aimd=CLIENT_AIMD + server
    )
    assert result["success"], result
    assert set(result["data"]["assigners"]) == {"b", "c"}
    assert ["b", "server:triple_b"] in result["data"]["assigner_graph"]["edges"]
    cycle = run_executor(
        tmp_path,
        "get_protocol_info",
        {"env_vars": {}},
        aimd=CLIENT_AIMD.replace('["a"]', '["c"]') + server,
    )
    assert not cycle["success"], cycle


def test_executor_rejects_package_traversal(tmp_path):
    result = run_executor(tmp_path, "var_validate", {}, name="../practice")
    assert not result["success"]
    assert "Invalid Protocol package name" in result["message"]


def test_custom_validator_errors_remain_json_serializable(tmp_path):
    result = run_executor(
        tmp_path,
        "var_validate",
        {"sample_label": "PRACTICE-001", "observation_count": 12},
        custom_model="""
from pydantic import BaseModel, field_validator
class VarModel(BaseModel):
    observation_count: int
    @field_validator("observation_count")
    @classmethod
    def reject_twelve(cls, value):
        if value == 12:
            raise ValueError("Needs review")
        return value
""",
    )
    assert result["success"], result
    assert result["data"]["errors"][0]["loc"] == ["observation_count"]
    assert "Needs review" in result["data"]["errors"][0]["msg"]


def test_configured_storage_does_not_fall_back_to_checkout_package(tmp_path):
    shadow = tmp_path / "protocols" / PACKAGE_NAME
    shadow.mkdir(parents=True)
    (shadow / "model.py").write_text('raise RuntimeError("WRONG PACKAGE")')
    result = run_executor(
        tmp_path,
        "var_validate",
        {"sample_label": "PRACTICE-001", "observation_count": 12},
    )
    assert result["success"] and not result["data"].get("errors"), result


@pytest.mark.skipif(
    os.environ.get("RUN_DOCKER_PROTOCOL_TESTS") != "1",
    reason="Requires the local Protocol executor image",
)
def test_docker_adapter_uses_configured_storage(tmp_path, monkeypatch):
    from app.libs import protocol_agent

    run_executor(tmp_path, "get_protocol_info", {"env_vars": {}})
    (tmp_path / "protocol_executor.py").write_bytes(
        (API_ROOT / "protocol_executor.py").read_bytes()
    )
    (tmp_path / "protocol_assigners.py").write_bytes(
        (API_ROOT / "protocol_assigners.py").read_bytes()
    )
    # Only this test's generated, synthetic files are shared with the image's
    # non-root user. Never alter permissions on the real API log or packages.
    (tmp_path / "protocol_executor.log").chmod(0o666)
    root = tmp_path / "isolated-storage"
    package = root / PACKAGE_NAME
    package.chmod(0o777)
    for file in package.iterdir():
        if file.is_file():
            file.chmod(0o666)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(protocol_agent.config, "PROTOCOL_DIR", str(root))
    monkeypatch.setattr(protocol_agent.config, "PROTOCOL_RUN_ENV", "docker")
    monkeypatch.setattr(
        protocol_agent.config,
        "AIRALOGY_PROTOCOL_EXECUTOR_IMAGE",
        "airalogy-platform-protocol-executor:local",
    )
    parsed = asyncio.run(
        protocol_agent.protocol_exec(
            "get_protocol_info", package.name, {"env_vars": {}}
        )
    )
    assert parsed["success"], parsed
    result = asyncio.run(
        protocol_agent.protocol_exec(
            "var_validate", package.name, {"observation_count": -1}
        )
    )
    assert result["success"], result
    assert {error["loc"][0] for error in result["data"]["errors"]} == {
        "sample_label",
        "observation_count",
    }
