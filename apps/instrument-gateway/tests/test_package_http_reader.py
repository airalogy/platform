import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from airalogy_instrument_gateway.authoring_contract import (
    generation_prompt,
    validate_spec,
)
from airalogy_instrument_gateway.http_read import HttpReadClient, HttpReadOperation
from airalogy_instrument_gateway.package_contract import inspect_package, sha256
from airalogy_instrument_gateway.package_installation import (
    install_inactive,
    installation_preview,
    verify_installation,
)
from airalogy_instrument_gateway.package_sandbox import test_package as run_isolated
from http_reader_fixture import PROJECT, RESULT, TARGET, package, serve, spec
from test_http_read import config
from test_package_installation import sdk

SCRIPT = """
import json, sys, threading
from pathlib import Path
from types import SimpleNamespace
from airalogy_instrument_gateway import load_adapter
adapter = load_adapter('synthetic.http-reader', Path(sys.argv[1]))
job = SimpleNamespace(command_key='reader.result.read', command_version='1.0.0', arguments={'sample_id':'sample-A'})
print(json.dumps({'target': adapter.identity(), 'result': adapter.execute(job, threading.Event())}))
"""


class HttpReaderPackageTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "Owned POSIX simulator process")
    def test_standalone_simulator_uses_loopback_and_fixed_independent_expectations(
        self,
    ):
        child = subprocess.Popen(
            [
                sys.executable,
                str(
                    PROJECT
                    / "apps/instrument-gateway/examples/http-reader/simulator.py"
                ),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertTrue(select.select([child.stdout], [], [], 5)[0])
            startup = json.loads(child.stdout.readline())
            self.assertTrue(startup["simulation_only"])
            selected = urlsplit(startup["origin"])
            self.assertEqual(selected.hostname, "127.0.0.1")
            client = HttpReadClient(
                config(selected.port),
                {
                    "identity": HttpReadOperation("/v1/identity"),
                    "result": HttpReadOperation("/v1/result", ("sample_id",)),
                },
            )
            self.assertEqual(
                client.get("identity").data, {"target": TARGET, "simulation_only": True}
            )
            self.assertEqual(
                client.get("result", {"sample_id": "sample-A"}).data, RESULT
            )
        finally:
            if child.poll() is None:
                child.terminate()
            try:
                child.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate(timeout=5)

    @unittest.skipUnless(shutil.which("node"), "Node example generator")
    def test_authoring_example_uses_fixed_materials_tests_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve() / "spec.json"
            command = [
                "node",
                str(PROJECT / "scripts/instrument-authoring-example.mjs"),
                str(target),
                "--http-reader",
            ]
            subprocess.run(command, check=True, capture_output=True, timeout=10)
            raw = target.read_bytes()
            selected = validate_spec(json.loads(raw))
            for field in (
                "manifest",
                "materials",
                "tests",
                "licenses",
                "initial_sources",
                "factory",
            ):
                self.assertEqual(selected[field], spec()[field])
            self.assertNotEqual(
                subprocess.run(
                    command, capture_output=True, timeout=10, check=False
                ).returncode,
                0,
            )
            self.assertEqual(target.read_bytes(), raw)

    def test_package_is_source_included_deterministic_and_not_hardware_qualified(self):
        raw = package()
        self.assertEqual(raw, package())
        checked = inspect_package(raw)
        self.assertFalse(checked["hardware_authorized"])
        self.assertFalse(checked["manifest"]["compatibility"]["tested"])
        self.assertEqual(checked["manifest"]["commands"][0]["retry"], "never")
        self.assertEqual(
            checked["manifest"]["commands"][0]["output_schema"]["properties"][
                "simulation_only"
            ],
            {"const": True},
        )
        selected = validate_spec(spec())
        self.assertIn("HttpReadClient", generation_prompt(selected))
        self.assertFalse(selected["initial_sources"])

    @unittest.skipUnless(os.name == "posix", "POSIX offline installation")
    def test_two_independent_installed_packages_read_actual_http_without_rebuilding(
        self,
    ):
        raw, wheel = package(), sdk()
        with tempfile.TemporaryDirectory() as directory, serve() as (port, calls):
            root = Path(directory).resolve()
            receipts = []
            for name in ("first", "second"):
                station = root / name
                station.mkdir(mode=0o700)
                configuration = config(port)
                arguments = {
                    "sdk_wheel": wheel,
                    "trusted_sdk_digest": sha256(wheel),
                    "config": configuration,
                    "root": station,
                }
                preview = installation_preview(raw, **arguments)
                self.assertEqual(len(calls), 2 * len(receipts))
                receipt = install_inactive(
                    raw,
                    **arguments,
                    preview_digest=preview["preview_digest"],
                    source_reviewed=True,
                )
                self.assertFalse(receipt["activation_performed"])
                self.assertFalse(receipt["hardware_authorized"])
                target = Path(receipt["destination"])
                configuration_file = station / "private-http.json"
                configuration_file.write_text(json.dumps(configuration))
                configuration_file.chmod(0o600)
                result = subprocess.run(
                    [
                        str(target / "bin/python"),
                        "-I",
                        "-B",
                        "-c",
                        SCRIPT,
                        str(configuration_file),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                self.assertEqual(
                    json.loads(result.stdout), {"target": TARGET, "result": RESULT}
                )
                self.assertEqual(verify_installation(target), receipt)
                receipts.append(receipt)
            self.assertEqual(len(calls), 4)
            self.assertEqual(
                sum(path.startswith("/v1/result?") for path, _ in calls), 2
            )
            self.assertNotEqual(receipts[0]["destination"], receipts[1]["destination"])

    @unittest.skipUnless(
        os.environ.get("RUN_ADAPTER_SANDBOX_TESTS") == "1",
        "Opt-in isolated package test",
    )
    def test_real_offline_container_runs_fixed_tests_with_no_device_access(self):
        sdk_path = Path(os.environ["ADAPTER_TEST_SDK_WHEEL"])
        result = run_isolated(
            package(),
            sdk_wheel=sdk_path.read_bytes(),
            trusted_sdk_digest=sha256(sdk_path.read_bytes()),
            image=os.environ["ADAPTER_TEST_IMAGE"],
            timeout_seconds=60,
        )
        self.assertTrue(result["passed"], result)
        self.assertTrue(result["simulation_only"])
        self.assertFalse(result["hardware_authorized"])


if __name__ == "__main__":
    unittest.main()
