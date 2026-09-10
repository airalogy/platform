import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from http_controlled_fixture import (
    EXAMPLE,
    PROJECT,
    TARGET,
    config,
    package,
    serve,
    spec,
)
from test_package_installation import sdk

from airalogy_instrument_gateway.authoring_contract import validate_spec
from airalogy_instrument_gateway.package_contract import inspect_package, sha256
from airalogy_instrument_gateway.package_installation import (
    install_inactive,
    installation_preview,
    verify_installation,
)
from airalogy_instrument_gateway.package_sandbox import test_package as isolated_test

SCRIPT = """
import json, sys, threading
from pathlib import Path
from types import SimpleNamespace
from airalogy_instrument_gateway import load_adapter
adapter = load_adapter('synthetic.http-controlled-reader', Path(sys.argv[1]))
job = SimpleNamespace(job_id=sys.argv[2], command_key='reader.measure', command_version='1.0.0', arguments={'sample_count':2})
target = adapter.identity()
assert adapter.confirm(job)
assert adapter.preflight(job)['interlocks']['reader.ready']
result = adapter.execute(job, threading.Event())
assert adapter.safe_stop(job, 'owned test')
assert adapter.safe_stop(job, 'receipt-only recovery')
print(json.dumps({'target':target, 'result':result}))
"""


class HttpControlledPackageTests(unittest.TestCase):
    def test_fixed_independent_tests_and_example_generation(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                str(EXAMPLE / "tests"),
            ],
            env={
                **os.environ,
                "PYTHONPATH": os.pathsep.join(
                    [str(EXAMPLE.parents[1] / "src"), str(EXAMPLE / "source")]
                ),
            },
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "spec.json"
            subprocess.run(
                [
                    "node",
                    str(PROJECT / "scripts/instrument-authoring-example.mjs"),
                    str(path),
                    "--http-controlled-reader",
                ],
                check=True,
                capture_output=True,
                timeout=10,
            )
            selected = validate_spec(json.loads(path.read_bytes()))
            for key in ("manifest", "factory", "materials", "tests", "licenses"):
                self.assertEqual(selected[key], spec()[key])
        manifest = inspect_package(package())["manifest"]
        self.assertEqual(manifest["commands"][0]["risk"], "medium")
        self.assertEqual(
            manifest["commands"][0]["output_schema"]["properties"]["simulation_only"],
            {"const": True},
        )
        self.assertFalse(manifest["compatibility"]["tested"])

    def test_two_exact_offline_installations_control_owned_services_without_rebuild(
        self,
    ):
        raw, wheel = package(), sdk()
        with tempfile.TemporaryDirectory() as directory:
            receipts = []
            for name in ("first", "second"):
                with serve() as (port, calls):
                    root = Path(directory).resolve() / name
                    root.mkdir(mode=0o700)
                    arguments = {
                        "root": root,
                        "sdk_wheel": wheel,
                        "trusted_sdk_digest": sha256(wheel),
                        "config": config(port),
                    }
                    preview = installation_preview(raw, **arguments)
                    receipt = install_inactive(
                        raw,
                        **arguments,
                        preview_digest=preview["preview_digest"],
                        source_reviewed=True,
                    )
                    self.assertFalse(calls)
                    destination = Path(receipt["destination"])
                    path = root / "control.json"
                    path.write_text(json.dumps(config(port)))
                    path.chmod(0o600)
                    identifier = str(uuid4())
                    result = subprocess.run(
                        [
                            str(destination / "bin/python"),
                            "-I",
                            "-B",
                            "-c",
                            SCRIPT,
                            str(path),
                            identifier,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=20,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(
                        json.loads(result.stdout),
                        {
                            "target": TARGET,
                            "result": {
                                "operation_id": identifier,
                                "sample_count": 2,
                                "value": 1.25,
                                "unit": "synthetic_unit",
                                "simulation_only": True,
                            },
                        },
                    )
                    self.assertEqual(calls.count(("POST", "/v1/start")), 1)
                    self.assertEqual(calls.count(("POST", "/v1/stop")), 1)
                    self.assertEqual(verify_installation(destination), receipt)
                    receipts.append(receipt)
            self.assertNotEqual(receipts[0]["destination"], receipts[1]["destination"])

    @unittest.skipUnless(
        os.getenv("RUN_ADAPTER_SANDBOX_TESTS") == "1",
        "Explicit isolated package acceptance",
    )
    def test_real_isolation_runs_fixed_tests_without_live_device_access(self):
        wheel = Path(os.environ["ADAPTER_TEST_SDK_WHEEL"]).read_bytes()
        result = isolated_test(
            package(),
            sdk_wheel=wheel,
            trusted_sdk_digest=sha256(wheel),
            image=os.environ["ADAPTER_TEST_IMAGE"],
            timeout_seconds=60,
        )
        self.assertTrue(result["passed"], result)
        self.assertFalse(result["hardware_authorized"])
