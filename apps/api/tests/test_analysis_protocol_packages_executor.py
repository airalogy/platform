"""Generated portable drafts are parsed and validated by the real executor."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.analysis_protocol_packages import (
    analysis_protocol_package_zip_bytes,
    read_analysis_protocol_package_zip,
)
from tests.test_analysis_protocol_packages import build, builtin_method, project_method

API_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "protocol_00000000-0000-0000-0000-000000000001"


def execute(tmp_path, package, action, values):
    root = tmp_path / "isolated-storage"
    directory = root / PACKAGE_NAME
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in package.files.items():
        (directory / name).write_text(text, encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(API_ROOT / "protocol_executor.py"),
            action,
            PACKAGE_NAME,
            json.dumps(values),
        ],
        cwd=tmp_path,
        env={**os.environ, "PROTOCOL_DIR": str(root)},
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stdout), directory


@pytest.mark.parametrize(
    "factory",
    [builtin_method, project_method, lambda: project_method("evidence_synthesis")],
)
@pytest.mark.parametrize("locale", ["zh", "en"])
def test_compiled_draft_parses_and_validates_ordinary_record_without_executing_analysis(
    tmp_path, factory, locale
):
    package = read_analysis_protocol_package_zip(
        analysis_protocol_package_zip_bytes(build(factory(), locale=locale))
    )
    parsed, directory = execute(
        tmp_path, package, "get_protocol_info", {"env_vars": {}}
    )
    assert parsed["success"], parsed
    schema = parsed["data"]["json_schema"]["vars"]
    assert set(schema["required"]) == {"analysis_run_reference", "execution_notes"}
    assert set(schema["properties"]) == {
        "analysis_run_reference",
        "execution_notes",
        "limitations",
    }
    assert not (directory / "assigner.py").exists()
    assert not (directory / "model.py").exists()
    assert (directory / "analysis-method.json").read_text() == package.files[
        "analysis-method.json"
    ]
    valid, _ = execute(
        tmp_path,
        package,
        "var_validate",
        {
            "analysis_run_reference": "Reviewed real run reference supplied by user",
            "execution_notes": "A human checks the separately calculated output.",
        },
    )
    assert valid["success"] and not valid["data"].get("errors"), valid
    invalid, _ = execute(
        tmp_path, package, "var_validate", {"analysis_run_reference": ""}
    )
    assert invalid["success"], invalid
    assert {error["loc"][0] for error in invalid["data"]["errors"]} == {
        "analysis_run_reference",
        "execution_notes",
    }
