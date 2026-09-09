import copy
import io
import json
import os
import stat
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from airalogy_instrument_gateway.package_builder import build_package, source_wheel
from airalogy_instrument_gateway.package_cli import main, read_selected
from airalogy_instrument_gateway.package_contract import (
    inspect_package,
    pack,
    safe_path,
    sha256,
    strict_json,
    validate_manifest,
    wheel_identity,
)
from airalogy_instrument_gateway.package_sandbox import (
    sandbox_command,
)
from airalogy_instrument_gateway.package_sandbox import (
    test_package as run_package_tests,
)

EXAMPLE = Path(__file__).parents[1] / "examples/adapter-package"


def example():
    manifest = json.loads((EXAMPLE / "manifest.json").read_text())
    paths = [
        "source/synthetic_reader.py",
        "tests/test_reader.py",
        "licenses/LICENSE.txt",
    ]
    payloads = {path: (EXAMPLE / path).read_bytes() for path in paths}
    return build_package(
        manifest, factory="synthetic_reader:create_adapter", payloads=payloads
    )


def contents(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


class PackageTests(unittest.TestCase):
    def test_output_names_cannot_collide_on_case_insensitive_stations(self):
        _raw, result = example()
        first = {
            "name": "raw.csv",
            "media_type": "text/csv",
            "max_bytes": 1000,
            "required": True,
        }
        for outputs in (
            [first, {**first, "name": "RAW.csv"}],
            [{**first, "media_type": "текст/csv"}],
        ):
            manifest = copy.deepcopy(result["manifest"])
            manifest["commands"][0]["outputs"] = outputs
            with self.assertRaises(ValueError):
                validate_manifest(manifest)

    def test_selected_file_cli_build_inspect_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "adapter.zip"
            args = [
                "build",
                "--manifest",
                str(EXAMPLE / "manifest.json"),
                "--factory",
                "synthetic_reader:create_adapter",
                "--output",
                str(output),
            ]
            for name in [
                "source/synthetic_reader.py",
                "tests/test_reader.py",
                "licenses/LICENSE.txt",
            ]:
                args.extend(["--file", f"{name}={EXAMPLE / name}"])
            with redirect_stdout(io.StringIO()) as captured:
                self.assertEqual(main(args), 0)
            expected = json.loads(captured.getvalue())
            self.assertEqual(output.read_bytes(), example()[0])
            with redirect_stdout(io.StringIO()) as captured:
                self.assertEqual(main(["inspect", str(output)]), 0)
            self.assertEqual(json.loads(captured.getvalue()), expected)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 2)
            link = Path(directory) / "link.zip"
            link.symlink_to(output)
            with self.assertRaises(ValueError):
                read_selected(link)
            with self.assertRaises(ValueError):
                read_selected(output, limit=10)

    def test_wrong_json_shapes_have_a_bounded_validation_error(self):
        _raw, result = example()
        for key in result["manifest"]:
            for replacement in [None, [], 5]:
                manifest = copy.deepcopy(result["manifest"])
                manifest[key] = replacement
                with (
                    self.subTest(key=key, replacement=replacement),
                    self.assertRaises(ValueError),
                ):
                    validate_manifest(manifest)

    def test_archive_and_wheel_are_deterministic_and_independently_inspectable(self):
        raw, result = example()
        self.assertEqual(raw, example()[0])
        self.assertEqual(result["archive_digest"], sha256(raw))
        self.assertFalse(result["hardware_authorized"])
        self.assertEqual(result["manifest"]["entry_point"], "synthetic.reader")
        self.assertEqual(
            result["wheels"]["airalogy-synthetic-reader"]["version"], "1.0.0"
        )
        self.assertFalse(result["manifest"]["compatibility"]["tested"])

    def test_missing_or_modified_payload_and_entrypoint_are_rejected(self):
        raw, result = example()
        files = contents(raw)
        files.pop("manifest.json")
        files["source/synthetic_reader.py"] += b"\n# changed after preview\n"
        with self.assertRaisesRegex(ValueError, "integrity"):
            pack(result["manifest"], files)
        files = contents(raw)
        files.pop("manifest.json")
        manifest = copy.deepcopy(result["manifest"])
        manifest["entry_point"] = "another.adapter"
        with self.assertRaisesRegex(ValueError, "entry point"):
            pack(manifest, files)
        files["unexpected.py"] = b"raise RuntimeError('not executed')"
        with self.assertRaisesRegex(ValueError, "exactly"):
            pack(result["manifest"], files)

    def test_unsafe_paths_links_and_duplicate_json_are_rejected(self):
        for path in [
            "../escape",
            "/absolute",
            "c:/escape",
            "a\\b",
            "a/CON.txt",
            "foo./file",
            "a//b",
        ]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_path(path)
        with self.assertRaises(ValueError):
            strict_json(b'{"id": "one", "id": "two"}')
        with self.assertRaises(ValueError):
            strict_json(b'{"v": NaN}')
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            link = zipfile.ZipInfo("source/link.py")
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "../../secret")
        with self.assertRaisesRegex(ValueError, "special"):
            inspect_package(output.getvalue())

    def test_wheel_record_and_manifest_safety_contract_cannot_be_bypassed(self):
        raw, result = example()
        wheel_raw = next(
            value for name, value in contents(raw).items() if name.endswith(".whl")
        )
        files = contents(wheel_raw)
        files["synthetic_reader.py"] += b"# tampered"
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for name, value in files.items():
                archive.writestr(name, value)
        with self.assertRaisesRegex(ValueError, "RECORD"):
            wheel_identity(stream.getvalue())
        manifest = copy.deepcopy(result["manifest"])
        manifest["commands"][0]["risk"] = "high"
        with self.assertRaises(ValueError):
            validate_manifest(manifest)

    def test_dependency_cannot_replace_gateway_modules_under_another_name(self):
        raw, result = example()
        files = contents(raw)
        files.pop("manifest.json")
        name = "wheels/foreign-1.0.0-py3-none-any.whl"
        _wheel_name, files[name] = source_wheel(
            distribution="foreign",
            version="1.0.0",
            entry_name="foreign.adapter",
            factory="airalogy_instrument_gateway.runtime:create_adapter",
            sources={"airalogy_instrument_gateway/runtime.py": b"# not executed"},
        )
        manifest = copy.deepcopy(result["manifest"])
        manifest["files"].append(
            {
                "path": name,
                "sha256": sha256(files[name]),
                "size_bytes": len(files[name]),
                "role": "dependency_wheel",
            }
        )
        with self.assertRaisesRegex(ValueError, "Gateway replacement"):
            pack(manifest, files)
        manifest = copy.deepcopy(result["manifest"])
        manifest["hardware_authorized"] = True
        with self.assertRaises(ValueError):
            validate_manifest(manifest)

    def test_sandbox_has_no_host_mounts_network_or_floating_image(self):
        command = sandbox_command("docker", "sha256:" + "a" * 64, "synthetic-test")
        self.assertNotIn("--mount", command)
        self.assertNotIn("--volume", command)
        self.assertNotIn("--privileged", command)
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertEqual(command[command.index("--user") + 1], "65532:65532")
        self.assertEqual(command[command.index("--pull") + 1], "never")
        with self.assertRaises(ValueError):
            sandbox_command("docker", "python:latest", "synthetic-test")

    @unittest.skipUnless(
        os.getenv("RUN_ADAPTER_SANDBOX_TESTS") == "1",
        "Requires an explicitly selected local image and SDK wheel",
    )
    def test_real_container_passes_reference_and_blocks_host_network_and_timeout(self):
        sdk = Path(os.environ["ADAPTER_TEST_SDK_WHEEL"]).read_bytes()
        image = os.environ["ADAPTER_TEST_IMAGE"]
        options = {"sdk_wheel": sdk, "trusted_sdk_digest": sha256(sdk), "image": image}
        raw, _ = example()
        report = run_package_tests(raw, **options)
        self.assertTrue(report["passed"], report)
        self.assertFalse(report["hardware_authorized"])
        # Explicit negative/adversarial fixture, not assertions derived from a model's output.
        manifest = json.loads((EXAMPLE / "manifest.json").read_text())
        payloads = {
            name: (EXAMPLE / name).read_bytes()
            for name in ["source/synthetic_reader.py", "licenses/LICENSE.txt"]
        }
        payloads["tests/test_isolation.py"] = b"""import os, socket, unittest
class Isolation(unittest.TestCase):
 def test_boundary(self):
  self.assertFalse(os.path.exists('/var/run/docker.sock'))
  self.assertFalse(os.path.exists('/Users'))
  self.assertFalse(os.path.exists('/dev/ttyUSB0'))
  self.assertNotIn('AIRALOGY_GATEWAY_TOKEN', os.environ)
  with self.assertRaises(OSError): open('/escape', 'w')
  with self.assertRaises(OSError): socket.create_connection(('192.0.2.1', 80), timeout=1)
  self.assertNotEqual(os.getuid(), 0)
"""
        adversarial, _ = build_package(
            manifest, factory="synthetic_reader:create_adapter", payloads=payloads
        )
        report = run_package_tests(adversarial, **options)
        self.assertTrue(report["passed"], report)
        payloads["tests/test_isolation.py"] = b"import time; time.sleep(60)"
        stalled, _ = build_package(
            manifest, factory="synthetic_reader:create_adapter", payloads=payloads
        )
        report = run_package_tests(stalled, **options, timeout_seconds=4)
        self.assertTrue(report["timed_out"], report)
        self.assertFalse(report["passed"])

    def test_api_uses_identical_package_contract(self):
        source = (
            Path(__file__).parents[1]
            / "src/airalogy_instrument_gateway/package_contract.py"
        )
        target = (
            Path(__file__).parents[3]
            / "apps/api/app/services/instrument_package_contract.py"
        )
        self.assertEqual(source.read_bytes(), target.read_bytes())
