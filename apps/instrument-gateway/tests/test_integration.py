import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from airalogy_instrument_gateway.integration_contract import (
    canonical,
    digest,
    example_bundle,
    rehearse,
    validate_package,
)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.bundle = example_bundle()
        self.package = self.bundle["package"]
        self.scenarios = self.bundle["scenarios"]

    def test_example_is_simulation_not_authority(self):
        report = rehearse(self.package, self.scenarios)
        self.assertTrue(report["passed"])
        self.assertTrue(report["simulation_only"])
        self.assertFalse(report["hardware_authorized"])
        self.assertEqual(report["cases"][0]["output"], {"value": 0.42})

    def test_digest_is_canonical_and_changes_with_content(self):
        self.assertEqual(digest({"b": 1, "a": 2}), digest({"a": 2, "b": 1}))
        self.assertNotEqual(
            digest(self.package), digest({**self.package, "version": "v2"})
        )

    def test_api_contract_is_generated_from_gateway_source(self):
        root = Path(__file__).resolve().parents[3]
        self.assertEqual(
            (
                root / "apps/api/app/services/instrument_adapter_contract.py"
            ).read_bytes(),
            (
                root
                / "apps/instrument-gateway/src/airalogy_instrument_gateway/integration_contract.py"
            ).read_bytes(),
        )

    def test_unsafe_or_changed_session_fails_before_processing(self):
        for field, value in [
            ("window_id", "other"),
            ("session", "locked"),
            ("session", "disconnected"),
            ("control_owner", "human"),
            ("blocking_dialog", True),
            ("state", "running"),
            ("target", {**self.package["target"], "version": "2.0"}),
        ]:
            for position in (0, 1):
                with self.subTest(field=field, position=position):
                    cases = copy.deepcopy(self.scenarios)
                    cases[0]["observations"][position][field] = value
                    report = rehearse(self.package, cases)
                    self.assertFalse(report["passed"])
                    self.assertEqual(report["cases"][0]["trace"], [])

    def test_missing_or_ambiguous_control_fails_closed(self):
        for controls in (
            [],
            [{"id": "other", "value": 0.42, "enabled": True}],
            self.scenarios[0]["observations"][0]["controls"] * 2,
        ):
            cases = copy.deepcopy(self.scenarios)
            cases[0]["observations"][0]["controls"] = controls
            self.assertFalse(rehearse(self.package, cases)["passed"])

    def test_wrong_output_and_uncovered_commands_fail(self):
        self.scenarios[0]["expected_output"] = {"value": 1}
        report = rehearse(self.package, self.scenarios)
        self.assertFalse(report["passed"])
        self.assertEqual(report["uncovered_commands"], ["read.result@v1"])

    def test_set_value_requires_exact_typed_readback(self):
        step = self.package["commands"][0]["steps"][0]
        step.update(operation="set_value", value=1)
        del step["output_key"]
        self.scenarios[0]["expected_output"] = {}
        for actual, passed in [(1, True), (True, False), ("1", False), (2, False)]:
            self.scenarios[0]["observations"][1]["controls"][0]["value"] = actual
            self.assertEqual(rehearse(self.package, self.scenarios)["passed"], passed)

    def test_unknown_fields_and_executable_actions_rejected(self):
        for operation in ("shell", "eval", "launch", "click_coordinates", "download"):
            package = copy.deepcopy(self.package)
            package["commands"][0]["steps"][0]["operation"] = operation
            with self.assertRaises(ValueError):
                validate_package(package)
        with self.assertRaises(ValueError):
            validate_package({**self.package, "hardware_authorized": True})

    def test_no_implicit_loop_or_retry(self):
        self.package["commands"][0]["steps"].append(
            {
                "operation": "invoke",
                "control_id": "start",
                "before": "ready",
                "after": "running",
            }
        )
        with self.assertRaisesRegex(ValueError, "continuous"):
            validate_package(self.package)

    def test_bounds_and_nonfinite_numbers(self):
        for value in (float("nan"), float("inf"), "x" * 262145):
            with self.assertRaises(ValueError):
                canonical(value)

    def test_cli_example_without_credentials_or_ai(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "airalogy_instrument_gateway.integration_cli",
                "--example",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout), self.bundle)

    def test_cli_reads_only_selected_bounded_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory) / "bundle.json"
            selected.write_text(json.dumps(self.bundle))
            command = [
                sys.executable,
                "-m",
                "airalogy_instrument_gateway.integration_cli",
            ]
            valid = subprocess.run(
                [*command, str(selected)], capture_output=True, text=True, check=False
            )
            self.assertEqual(valid.returncode, 0)
            self.assertFalse(json.loads(valid.stdout)["hardware_authorized"])
            link = Path(directory) / "link.json"
            link.symlink_to(selected)
            rejected = subprocess.run(
                [*command, str(link)], capture_output=True, text=True, check=False
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("regular file", rejected.stderr)
            selected.write_text("x" * 262145)
            rejected = subprocess.run(
                [*command, str(selected)], capture_output=True, text=True, check=False
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("256 KiB", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
