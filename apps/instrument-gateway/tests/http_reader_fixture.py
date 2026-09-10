"""Public synthetic source, exact package bytes and owned HTTP replies for tests."""

import copy
import json
import runpy
from pathlib import Path

from test_http_read import response, server

from airalogy_instrument_gateway.package_builder import build_package

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/http-reader"
PROJECT = Path(__file__).resolve().parents[3]
TARGET = {
    "identity_reference": "owned-http-reader-fixture",
    "firmware": "synthetic-1",
    "application": "owned-http-reader",
    "application_version": "1.0.0",
    "driver_version": "1.0.0",
    "os_version": "synthetic-service-v1",
}
RESULT = {
    "sample_id": "sample-A",
    "value": 1.25,
    "unit": "synthetic_unit",
    "simulation_only": True,
}
_simulator_payload = runpy.run_path(str(EXAMPLE / "simulator.py"))["payload"]


def spec():
    manifest = json.loads((EXAMPLE / "manifest.json").read_text())
    manifest["provenance"]["kind"] = "aira"
    return {
        "goal": "Implement only the documented owned HTTP fixture; no real equipment",
        "manifest": manifest,
        "factory": "http_reader:create_adapter",
        "materials": [
            {
                "name": "http-reader-api.txt",
                "text": (EXAMPLE / "api-specification.md").read_text(),
            }
        ],
        "tests": {
            "tests/test_http_reader.py": (
                EXAMPLE / "tests/test_http_reader.py"
            ).read_text()
        },
        "licenses": {"licenses/LICENSE.txt": (PROJECT / "LICENSE").read_text()},
        "initial_sources": {},
    }


def package(*, physical_policy=False):
    selected = spec()
    manifest = copy.deepcopy(selected["manifest"])
    manifest["provenance"]["kind"] = "manual"
    if physical_policy:
        # Exercise qualification policy on isolated synthetic data only. Never
        # publish this test alteration or treat it as real equipment evidence.
        manifest["id"] = "synthetic.http-reader-policy-test"
        manifest["commands"][0]["output_schema"]["properties"]["simulation_only"] = {
            "type": "boolean"
        }
    payloads = {
        name: value.encode()
        for name, value in {**selected["tests"], **selected["licenses"]}.items()
    }
    payloads["source/http_reader.py"] = (EXAMPLE / "source/http_reader.py").read_bytes()
    return build_package(manifest, factory=selected["factory"], payloads=payloads)[0]


def respond(handler):
    data = _simulator_payload(handler.path)
    if data is None:
        response(handler, b"{}", status=404)
        return
    response(handler, json.dumps(data).encode())


def serve():
    return server(respond)
