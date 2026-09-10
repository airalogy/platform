"""Package/reference parity and actual container tests for owned export fixtures."""

import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from export_reader_fixture import EXAMPLE, PROJECT, package

from airalogy_instrument_gateway.authoring_contract import (
    generation_prompt,
    validate_spec,
)
from airalogy_instrument_gateway.package_contract import inspect_package, sha256
from airalogy_instrument_gateway.package_sandbox import test_package


class ExportPackageTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node example generator")
    def test_authoring_uses_fixed_tests_and_selected_backend_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / "spec.json"
            command = [
                "node",
                str(PROJECT / "scripts/instrument-authoring-example.mjs"),
                str(destination),
                "--export-reader",
            ]
            subprocess.run(command, check=True, capture_output=True, timeout=10)
            raw = destination.read_bytes()
            spec = validate_spec(json.loads(raw))
            self.assertEqual(spec["factory"], "export_reader:create_adapter")
            self.assertEqual(spec["initial_sources"], {})
            self.assertEqual(
                spec["tests"],
                {
                    "tests/test_export_reader.py": (
                        EXAMPLE / "tests/test_export_reader.py"
                    ).read_text()
                },
            )
            self.assertEqual(
                spec["materials"][0]["text"],
                (EXAMPLE / "api-specification.md").read_text(),
            )
            self.assertIn("ExportReadClient", generation_prompt(spec))
            self.assertEqual(spec["manifest"]["compatibility"]["tested"], [])
            self.assertEqual(spec["manifest"]["provenance"]["kind"], "aira")
            for extra in ([], ["--http-reader"]):
                result = subprocess.run(
                    command + extra, capture_output=True, timeout=10, check=False
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(destination.read_bytes(), raw)

    def test_source_included_package_and_fixed_output_declarations_agree(self):
        manifest = json.loads((EXAMPLE / "manifest.json").read_text())
        source = runpy.run_path(str(EXAMPLE / "source/export_reader.py"))
        self.assertEqual(source["OUTPUTS"], manifest["commands"][0]["outputs"])
        inspection = inspect_package(package())
        self.assertEqual(inspection["manifest"]["commands"][0]["risk"], "read_only")
        self.assertEqual(
            inspection["manifest"]["commands"][0]["output_schema"]["properties"][
                "scientific_validation"
            ],
            {"const": False},
        )
        self.assertEqual(manifest["compatibility"]["tested"], [])

    def test_fixed_package_tests_run_with_owned_files_only(self):
        # A reviewed repository reference, not untrusted model output. Production
        # candidate code uses the separate Docker-only package test path below.
        environment = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                [str(EXAMPLE.parents[1] / "src"), str(EXAMPLE / "source")]
            ),
        }
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                str(EXAMPLE / "tests"),
            ],
            env=environment,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    @unittest.skipUnless(
        os.getenv("RUN_ADAPTER_SANDBOX_TESTS") == "1",
        "explicit disposable Docker acceptance",
    )
    def test_actual_container_runs_the_export_reader_against_fixed_files(self):
        wheel = Path(os.environ["ADAPTER_TEST_SDK_WHEEL"]).read_bytes()
        result = test_package(
            package(),
            sdk_wheel=wheel,
            trusted_sdk_digest=sha256(wheel),
            image=os.environ["ADAPTER_TEST_IMAGE"],
            timeout_seconds=60,
        )
        self.assertTrue(result["passed"], result)


if __name__ == "__main__":
    unittest.main()
