"""Source-only controlled development, with actual isolated state-machine tests."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from controlled_reader_fixture import EXAMPLE, PROJECT, proposal, spec
from test_package_authoring import FixtureClient
from test_packages import contents

from airalogy_instrument_gateway.authoring import prepare, read_request, run
from airalogy_instrument_gateway.authoring_contract import source_review, validate_spec
from airalogy_instrument_gateway.package_contract import inspect_package, sha256
from airalogy_instrument_gateway.package_sandbox import test_package as isolated_test


class ControlledSourceTests(unittest.TestCase):
    def test_reference_uses_an_independent_stateful_fake_and_no_production_config(self):
        # Trusted repository fixture only. Generated candidates never use this
        # host path; they run exclusively in the isolated test below.
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

    def test_example_preserves_fixed_control_contract_tests_and_no_tested_hardware(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory).resolve() / "spec.json"
            result = subprocess.run(
                [
                    "node",
                    str(PROJECT / "scripts/instrument-authoring-example.mjs"),
                    str(selected),
                    "--controlled-reader",
                ],
                capture_output=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            value = validate_spec(json.loads(selected.read_bytes()))
            for key in (
                "factory",
                "manifest",
                "tests",
                "materials",
                "licenses",
                "initial_sources",
            ):
                self.assertEqual(value[key], spec()[key])
            self.assertTrue(source_review(value)["requires_controlled_source_consent"])
            self.assertFalse(value["manifest"]["compatibility"]["tested"])

    @unittest.skipUnless(
        os.getenv("RUN_ADAPTER_SANDBOX_TESTS") == "1",
        "explicit disposable Docker acceptance",
    )
    def test_actual_sandbox_catches_duplicate_start_then_repairs_without_changing_tests(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            wheel = Path(os.environ["ADAPTER_TEST_SDK_WHEEL"]).read_bytes()
            (root / "sdk.whl").write_bytes(wheel)
            (root / "spec.json").write_text(json.dumps(spec()))
            prepared = prepare(
                workspace=root,
                platform_url="http://127.0.0.1/api",
                gateway_id=str(uuid4()),
                resource_id=str(uuid4()),
                spec=root / "spec.json",
                sdk_wheel=root / "sdk.whl",
                trusted_sdk_digest=sha256(wheel),
                image=os.environ["ADAPTER_TEST_IMAGE"],
            )
            path = Path(prepared["request_file"])
            client = FixtureClient(
                read_request(path)["request"], [proposal(broken=True), proposal()]
            )
            tested = []

            def actual_test(raw, **kwargs):
                tested.append(sha256(raw))
                return isolated_test(raw, **kwargs)

            result = run(path, client=client, tester=actual_test)
            self.assertEqual(result["state"], "draft_tested")
            self.assertFalse(result["hardware_authorized"])
            self.assertFalse(client.turns[0]["report"]["passed"])
            self.assertTrue(client.turns[1]["report"]["passed"])
            raw = Path(result["package"]).read_bytes()
            self.assertEqual(
                contents(raw)["tests/test_controlled_reader.py"].decode(),
                spec()["tests"]["tests/test_controlled_reader.py"],
            )
            manifest = inspect_package(raw)["manifest"]
            self.assertEqual(manifest["commands"][0]["risk"], "medium")
            self.assertTrue(manifest["commands"][0]["device_confirmation_required"])
            self.assertEqual(
                manifest["commands"][0]["output_schema"]["properties"][
                    "simulation_only"
                ],
                {"const": True},
            )
            self.assertEqual(len(tested), 2)
            self.assertEqual(run(path, client=client, tester=actual_test), result)
            self.assertEqual(len(client.turns), 2)
            self.assertEqual(len(tested), 2)
