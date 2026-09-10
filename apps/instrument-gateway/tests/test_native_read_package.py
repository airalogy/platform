import os
import unittest
from pathlib import Path

from native_read_fixture import package

from airalogy_instrument_gateway.package_contract import inspect_package
from airalogy_instrument_gateway.package_sandbox import test_package as isolated_test


class NativeReadPackageTests(unittest.TestCase):
    def test_reference_is_read_only_and_not_hardware_qualified(self):
        manifest = inspect_package(package())["manifest"]
        command = manifest["commands"][0]
        self.assertEqual(command["risk"], "read_only")
        self.assertEqual(
            command["output_schema"]["properties"]["simulation_only"], {"const": True}
        )
        self.assertEqual(
            command["output_schema"]["properties"]["observation_only"], {"const": True}
        )
        self.assertEqual(manifest["compatibility"]["tested"], [])

    @unittest.skipUnless(
        os.getenv("RUN_ADAPTER_SANDBOX_TESTS") == "1",
        "Explicit real isolated package tests",
    )
    def test_independent_fixed_tests_in_actual_network_disabled_container(self):
        from airalogy_instrument_gateway.package_contract import sha256

        wheel = Path(os.environ["ADAPTER_TEST_SDK_WHEEL"]).read_bytes()
        report = isolated_test(
            package(),
            sdk_wheel=wheel,
            trusted_sdk_digest=sha256(wheel),
            image=os.environ["ADAPTER_TEST_IMAGE"],
            timeout_seconds=60,
        )
        self.assertTrue(report["passed"], report)
        self.assertFalse(report["hardware_authorized"])
