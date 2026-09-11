"""Fixed GUI adapter authoring inputs; no browser, desktop or model calls."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from test_package_authoring import FixtureClient
from test_packages import contents

from airalogy_instrument_gateway.authoring import prepare, read_request, run
from airalogy_instrument_gateway.authoring_contract import (
    generation_prompt,
    source_review,
    validate_spec,
)
from airalogy_instrument_gateway.package_contract import inspect_package, sha256
from airalogy_instrument_gateway.package_sandbox import test_package as isolated_test

PROJECT = Path(__file__).resolve().parents[3]
GATEWAY = PROJECT / "apps/instrument-gateway"
MODES = ("interface-workflow", "native-read")


def generate(root, mode):
    output = root / "spec.json"
    subprocess.run(
        [
            "node",
            str(PROJECT / "scripts/instrument-authoring-example.mjs"),
            str(output),
            "--" + mode,
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )
    return output, validate_spec(json.loads(output.read_bytes()))


def proposal(mode, *, broken=False):
    module = mode.replace("-", "_")
    source = (GATEWAY / "examples" / mode / "source" / f"{module}.py").read_text()
    if broken:
        before, after = (
            ('"value": result', '"value": 0.84')
            if mode == "interface-workflow"
            else (
                '"values": values',
                '"values": {"reader.status": "Complete", "reader.result": "0.84"}',
            )
        )
        if source.count(before) != 1:
            raise AssertionError(
                "The deliberately fabricated output must change exactly once"
            )
        source = source.replace(before, after)
    return {
        "sources": {f"source/{module}.py": source},
        "summary": "Synthetic source fixture; not a paid-model or hardware acceptance",
        "assumptions": [],
        "missing_information": [],
    }


@unittest.skipUnless(shutil.which("node"), "Node reference-spec generator")
class InterfaceAuthoringTests(unittest.TestCase):
    def test_selected_contract_tests_and_consent_remain_fixed_without_runtime_secrets(
        self,
    ):
        for mode in MODES:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                path, spec = generate(Path(directory).resolve(), mode)
                module = mode.replace("-", "_")
                example = GATEWAY / "examples" / mode
                expected = json.loads((example / "manifest.json").read_bytes())
                expected["provenance"]["kind"] = "aira"
                self.assertEqual(spec["manifest"], expected)
                self.assertEqual(spec["factory"], f"{module}:create_adapter")
                self.assertEqual(spec["initial_sources"], {})
                self.assertEqual(
                    spec["tests"],
                    {
                        f"tests/test_{module}.py": (
                            example / "tests" / f"test_{module}.py"
                        ).read_text(),
                    },
                )
                self.assertEqual(
                    spec["materials"],
                    [
                        {
                            "name": f"{mode}-api.txt",
                            "text": (example / "api-specification.md").read_text(),
                        }
                    ],
                )
                self.assertEqual(
                    spec["licenses"],
                    {
                        "licenses/LICENSE.txt": (PROJECT / "LICENSE").read_text(),
                    },
                )
                self.assertEqual(
                    source_review(spec)["requires_controlled_source_consent"],
                    mode == "interface-workflow",
                )
                self.assertFalse(expected["compatibility"]["tested"])
                prompt = generation_prompt(spec)
                client = (
                    "NativeReadProcessClient"
                    if mode == "native-read"
                    else "InterfaceProcessClient"
                )
                self.assertIn(client, prompt)
                self.assertIn("never retry a worker operation", prompt)
                self.assertIn("source/module.py", prompt)
                raw = path.read_bytes()
                self.assertNotIn(str(path.parent).encode(), raw)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                for extra in ([], ["--http-reader"]):
                    result = subprocess.run(
                        [
                            "node",
                            str(PROJECT / "scripts/instrument-authoring-example.mjs"),
                            str(path),
                            "--" + mode,
                            *extra,
                        ],
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(path.read_bytes(), raw)

    def test_reviewed_reference_tests_require_no_native_or_browser_runtime(self):
        # Only trusted repository references run here on the host. All candidate
        # source (including synthetic proposals below) uses the real container.
        for mode in MODES:
            with self.subTest(mode=mode):
                example = GATEWAY / "examples" / mode
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "unittest",
                        "discover",
                        "-s",
                        str(example / "tests"),
                    ],
                    env={
                        **os.environ,
                        "PYTHONPATH": os.pathsep.join(
                            [
                                str(GATEWAY / "src"),
                                str(example / "source"),
                            ]
                        ),
                    },
                    capture_output=True,
                    timeout=20,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode())

    @unittest.skipUnless(
        os.getenv("RUN_ADAPTER_SANDBOX_TESTS") == "1",
        "Explicit real network-disabled container acceptance",
    )
    def test_fixed_tests_reject_fabricated_ui_results_then_repair_and_resume_without_retesting(
        self,
    ):
        wheel = Path(os.environ["ADAPTER_TEST_SDK_WHEEL"]).read_bytes()
        for mode in MODES:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                path, spec = generate(root, mode)
                sdk = root / "sdk.whl"
                sdk.write_bytes(wheel)
                prepared = prepare(
                    workspace=root,
                    platform_url="http://127.0.0.1/api",
                    gateway_id=str(uuid4()),
                    resource_id=str(uuid4()),
                    spec=path,
                    sdk_wheel=sdk,
                    trusted_sdk_digest=sha256(wheel),
                    image=os.environ["ADAPTER_TEST_IMAGE"],
                )
                request = Path(prepared["request_file"])
                client = FixtureClient(
                    read_request(request)["request"],
                    [
                        proposal(mode, broken=True),
                        proposal(mode),
                    ],
                )
                tests = []

                def actual_test(raw, _tests=tests, **kwargs):
                    _tests.append(sha256(raw))
                    return isolated_test(raw, **kwargs)

                result = run(request, client=client, tester=actual_test)
                self.assertEqual(result["state"], "draft_tested", result)
                self.assertFalse(result["hardware_authorized"])
                self.assertEqual(len(client.turns), 2)
                self.assertFalse(client.turns[0]["report"]["passed"])
                self.assertTrue(client.turns[1]["report"]["passed"])
                self.assertEqual(len(set(tests)), 2)
                raw = Path(result["package"]).read_bytes()
                for name, text in spec["tests"].items():
                    self.assertEqual(contents(raw)[name].decode(), text)
                manifest = inspect_package(raw)["manifest"]
                self.assertEqual(manifest["commands"], spec["manifest"]["commands"])
                self.assertFalse(manifest["compatibility"]["tested"])
                self.assertEqual(
                    run(request, client=client, tester=actual_test), result
                )
                self.assertEqual(len(client.turns), 2)
                self.assertEqual(len(tests), 2)


if __name__ == "__main__":
    unittest.main()
