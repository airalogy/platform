"""Explicitly opted-in owned AppKit fixture; no vendor/physical qualification."""

import json
import os
from pathlib import Path

from airalogy_instrument_gateway.interface_process import NativeReadProcessClient
from airalogy_instrument_gateway.package_builder import build_package

PROJECT = Path(__file__).resolve().parents[3]
EXAMPLE = PROJECT / "apps/instrument-gateway/examples/native-read"


def package(*, physical_policy=False):
    manifest = json.loads((EXAMPLE / "manifest.json").read_bytes())
    if physical_policy:
        # Disposable API policy acceptance only. The actual readback continues
        # to say simulation_only=True; never publish this test-only variant.
        manifest["id"] = "synthetic.native-read-policy-test"
        manifest["commands"][0]["output_schema"]["properties"]["simulation_only"] = {
            "type": "boolean"
        }
    payloads = {
        name: (EXAMPLE / name).read_bytes()
        for name in ("source/native_read.py", "tests/test_native_read.py")
    }
    payloads["licenses/LICENSE.txt"] = (PROJECT / "LICENSE").read_bytes()
    return build_package(
        manifest, factory="native_read:create_adapter", payloads=payloads
    )[0]


def prepare_native_reader():
    if os.getenv("RUN_INSTRUMENT_NATIVE_JOB_TESTS") != "1":
        raise RuntimeError(
            "Explicit operator-authorized native job acceptance required"
        )
    path = Path(os.environ["INSTRUMENT_NATIVE_READ_CONFIG"])
    client = NativeReadProcessClient.from_file(path)
    probe = client.call("probe")["data"]
    if probe["owned_simulator"] is not True or probe["read_access"] is not True:
        raise RuntimeError("Expected the owned, authorized AppKit fixture")
    runtime = json.loads(Path(client.config["runtime_file"]).read_bytes())
    return {
        "config": client.config,
        "target": probe["target"],
        "definition_digest": runtime["definition"]["definition_digest"],
        "evidence_root": runtime["evidence_root"],
    }
