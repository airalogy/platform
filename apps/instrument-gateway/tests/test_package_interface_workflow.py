import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from interface_worker_fixture import package, prepare_worker
from test_package_installation import sdk

from airalogy_instrument_gateway.package_contract import inspect_package, sha256
from airalogy_instrument_gateway.package_installation import (
    install_inactive,
    installation_preview,
)
from airalogy_instrument_gateway.package_sandbox import test_package as isolated_test

SCRIPT = """
import json,sys,threading
from pathlib import Path
from types import SimpleNamespace
from airalogy_instrument_gateway import load_adapter
adapter=load_adapter('synthetic.interface-workflow',Path(sys.argv[1]))
job=SimpleNamespace(job_id=sys.argv[2],command_key='interface.workflow.run',command_version='1.0.0',arguments={},timeout_seconds=30)
assert adapter.preflight(job)['interlocks']['interface.initial']
print(json.dumps(adapter.execute(job,threading.Event())))
"""


class InterfacePackageTests(unittest.TestCase):
    def test_published_reference_is_simulation_only(self):
        manifest = inspect_package(package())["manifest"]
        self.assertEqual(
            manifest["commands"][0]["output_schema"]["properties"]["simulation_only"],
            {"const": True},
        )
        self.assertEqual(manifest["compatibility"]["tested"], [])

    @unittest.skipUnless(
        os.getenv("RUN_INTERFACE_PROCESS_TESTS") == "1",
        "Explicit real Node/Chromium acceptance",
    )
    def test_two_independent_installed_copies_use_same_adapter_without_source_checkout_imports(
        self,
    ):
        self._independent_copies(demonstration=False)

    @unittest.skipUnless(
        os.getenv("RUN_INTERFACE_PROCESS_TESTS") == "1",
        "Explicit real Node/Chromium demonstration acceptance",
    )
    def test_recorded_demonstration_reuses_same_adapter_in_two_independent_installs(
        self,
    ):
        self._independent_copies(demonstration=True)

    def _independent_copies(self, *, demonstration):
        fixture, raw, wheel = (
            prepare_worker(demonstration=demonstration),
            package(),
            sdk(),
        )
        with tempfile.TemporaryDirectory() as directory:
            for name in ("first", "second"):
                root = Path(directory).resolve() / name
                root.mkdir(mode=0o700)
                args = {
                    "root": root,
                    "sdk_wheel": wheel,
                    "trusted_sdk_digest": sha256(wheel),
                    "config": fixture["config"],
                }
                preview = installation_preview(raw, **args)
                receipt = install_inactive(
                    raw,
                    **args,
                    preview_digest=preview["preview_digest"],
                    source_reviewed=True,
                )
                path = root / "config.json"
                path.write_text(json.dumps(fixture["config"]))
                path.chmod(0o600)
                identifier = str(uuid4())
                output = subprocess.run(
                    [
                        str(Path(receipt["destination"]) / "bin/python"),
                        "-I",
                        "-B",
                        "-c",
                        SCRIPT,
                        str(path),
                        identifier,
                    ],
                    capture_output=True,
                    check=False,
                    timeout=30,
                )
                self.assertEqual(output.returncode, 0, output.stderr.decode())
                self.assertEqual(
                    json.loads(output.stdout),
                    {
                        "operation_id": identifier,
                        "workflow_digest": fixture["workflow_digest"],
                        "value": 0.84,
                        "unit": "synthetic_unit",
                        "simulation_only": True,
                    },
                )

    @unittest.skipUnless(
        os.getenv("RUN_ADAPTER_SANDBOX_TESTS") == "1",
        "Explicit isolated package acceptance",
    )
    def test_independent_fixed_tests_inside_real_no_network_container(self):
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
