"""Owned service and exact source package for software acceptance, not hardware."""

import copy
import json
import runpy
import threading
from contextlib import contextmanager
from pathlib import Path

from airalogy_instrument_gateway.package_builder import build_package

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/http-controlled-reader"
PROJECT = Path(__file__).resolve().parents[3]
_service = runpy.run_path(str(EXAMPLE / "simulator.py"))
TARGET = _service["TARGET"]


def config(port):
    return {
        "schema": "airalogy.http-control-config.v1",
        "origin": f"http://127.0.0.1:{port}",
        "address": "127.0.0.1",
        "allow_plaintext": True,
        "headers": {},
        "enabled_operations": [
            "identity",
            "state",
            "configure",
            "start",
            "result",
            "stop",
        ],
    }


def spec():
    manifest = json.loads((EXAMPLE / "manifest.json").read_text())
    manifest["provenance"]["kind"] = "aira"
    return {
        "goal": "Implement only the owned HTTP control service, no vendor hardware",
        "manifest": manifest,
        "factory": "http_controlled_reader:create_adapter",
        "materials": [
            {
                "name": "http-controlled-reader-api.txt",
                "text": (EXAMPLE / "api-specification.md").read_text(),
            }
        ],
        "tests": {
            "tests/test_http_controlled_reader.py": (
                EXAMPLE / "tests/test_http_controlled_reader.py"
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
        # Disposable policy fixture ONLY, never published or physical evidence.
        manifest["id"] = "synthetic.http-controlled-policy-test"
        manifest["commands"][0]["output_schema"]["properties"]["simulation_only"] = {
            "type": "boolean"
        }
    payloads = {
        name: value.encode()
        for name, value in {**selected["tests"], **selected["licenses"]}.items()
    }
    payloads["source/http_controlled_reader.py"] = (
        EXAMPLE / "source/http_controlled_reader.py"
    ).read_bytes()
    return build_package(manifest, factory=selected["factory"], payloads=payloads)[0]


@contextmanager
def serve():
    calls = []

    class RecordedController(_service["Controller"]):
        def handle(self, method, path, body=None):
            calls.append((method, path))
            return super().handle(method, path, body)

    controller = RecordedController()
    service = _service["make_server"](controller=controller)
    worker = threading.Thread(target=service.serve_forever, daemon=True)
    worker.start()
    try:
        yield service.server_port, calls
    finally:
        service.shutdown()
        service.server_close()
        worker.join(timeout=2)
