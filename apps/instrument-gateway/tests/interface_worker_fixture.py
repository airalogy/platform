"""Owned real Node/Chromium fixture; never a vendor or physical qualification."""

import json
import subprocess
from pathlib import Path

from airalogy_instrument_gateway.interface_process import InterfaceProcessClient
from airalogy_instrument_gateway.package_builder import build_package

PROJECT = Path(__file__).resolve().parents[3]
EXAMPLE = PROJECT / "apps/instrument-gateway/examples/interface-workflow"


def package(*, physical_policy=False):
    manifest = json.loads((EXAMPLE / "manifest.json").read_bytes())
    if physical_policy:
        # Disposable API policy fixture only, never a published or actual
        # qualification. Runtime output still declares simulation_only=True.
        manifest["id"] = "synthetic.interface-workflow-policy-test"
        manifest["commands"][0]["output_schema"]["properties"]["simulation_only"] = {
            "type": "boolean"
        }
    payloads = {
        "source/interface_workflow.py": (
            EXAMPLE / "source/interface_workflow.py"
        ).read_bytes(),
        "tests/test_interface_workflow.py": (
            EXAMPLE / "tests/test_interface_workflow.py"
        ).read_bytes(),
        "licenses/LICENSE.txt": (PROJECT / "LICENSE").read_bytes(),
    }
    return build_package(
        manifest, factory="interface_workflow:create_adapter", payloads=payloads
    )[0]


def prepare_worker():
    result = subprocess.run(
        ["node", str(PROJECT / "scripts/instrument-interface-worker-example.mjs")],
        check=True,
        capture_output=True,
        timeout=45,
    )
    example = json.loads(result.stdout)
    config = json.loads(Path(example["config_file"]).read_bytes())
    target = InterfaceProcessClient(config).call("probe")["data"]["target"]
    runtime = json.loads(Path(example["runtime_file"]).read_bytes())
    return {
        "config": config,
        "target": target,
        "workflow_digest": example["workflow_digest"],
        "evidence_root": runtime["evidence_root"],
    }


def invocations(fixture):
    values = []
    # The test owns this exact root. Do not enumerate workstation directories.
    for directory in Path(fixture["evidence_root"]).iterdir():
        path = directory / "preview.json"
        if directory.is_dir() and path.is_file():
            value = json.loads(path.read_bytes())
            if value.get("schema") in {
                "airalogy.interface-worker-request.v1",
                "airalogy.native-read-worker-request.v1",
            }:
                values.append((directory.name, value["operation"], value["job_id"]))
    return sorted(values)
