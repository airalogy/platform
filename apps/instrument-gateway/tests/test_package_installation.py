import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from test_gateway import envelope
from test_packages import EXAMPLE, example

from airalogy_instrument_gateway.installation_cli import main
from airalogy_instrument_gateway.package_builder import build_package, source_wheel
from airalogy_instrument_gateway.package_contract import canonical, sha256
from airalogy_instrument_gateway.package_installation import (
    _exact_requirements,
    install_inactive,
    installation_preview,
    verify_installation,
)
from airalogy_instrument_gateway.state import GatewayState, StateStore


def sdk():
    root = Path(__file__).parents[1] / "src"
    sources = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in (root / "airalogy_instrument_gateway").glob("*.py")
    }
    return source_wheel(
        distribution="airalogy_instrument_gateway",
        version="0.1.0",
        entry_name="mock",
        factory="airalogy_instrument_gateway.adapters:mock_adapter_factory",
        sources=sources,
    )[1]


@unittest.skipUnless(os.name == "posix", "POSIX inactive installation support")
class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.raw = example()[0]
        self.sdk = sdk()
        self.inputs = {
            "sdk_wheel": self.sdk,
            "trusted_sdk_digest": sha256(self.sdk),
            "config": {"private_local_setting": "never print me"},
            "root": self.root,
        }

    def install(self, **extra):
        plan = installation_preview(self.raw, **self.inputs)
        return install_inactive(
            self.raw,
            **self.inputs,
            preview_digest=plan["preview_digest"],
            source_reviewed=True,
            **extra,
        )

    def test_real_offline_environment_can_load_only_explicitly_executed_synthetic_example(
        self,
    ):
        result = self.install()
        target = Path(result["destination"])
        self.assertFalse(result["activation_performed"])
        self.assertFalse(result["platform_authorized"])
        self.assertFalse(result["hardware_authorized"])
        self.assertEqual(verify_installation(target), result)
        self.assertEqual(self.install(), result)
        script = "from importlib.metadata import version, entry_points; assert version('airalogy-instrument-gateway') == '0.1.0'; point = next(iter(entry_points(group='airalogy.instrument_adapters', name='synthetic.reader'))); factory = point.load(); print(factory.__module__)"
        # Explicit test-only execution of this repository's synthetic adapter.
        # The installer itself never launches the installed environment or driver.
        run = subprocess.run(
            [str(target / "bin/python"), "-I", "-B", "-c", script],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "synthetic_reader")
        self.assertEqual(verify_installation(target), result)

    def test_installation_never_imports_adapter_source(self):
        manifest = json.loads((EXAMPLE / "manifest.json").read_text())
        manifest["id"] = "synthetic.unimportable"
        payloads = {
            name: (EXAMPLE / name).read_bytes()
            for name in ["tests/test_reader.py", "licenses/LICENSE.txt"]
        }
        payloads["source/synthetic_reader.py"] = (
            b"raise RuntimeError('never import during installation')\n"
        )
        self.raw = build_package(
            manifest, factory="synthetic_reader:create_adapter", payloads=payloads
        )[0]
        self.assertFalse(self.install()["activation_performed"])

    def test_wheel_shaped_document_does_not_become_an_undeclared_dependency(self):
        manifest = json.loads((EXAMPLE / "manifest.json").read_text())
        payloads = {
            name: (EXAMPLE / name).read_bytes()
            for name in [
                "source/synthetic_reader.py",
                "tests/test_reader.py",
                "licenses/LICENSE.txt",
            ]
        }
        payloads["licenses/hidden.whl"] = source_wheel(
            distribution="hidden_adapter",
            version="1.0.0",
            entry_name="hidden",
            factory="hidden:create_adapter",
            sources={"hidden.py": b"def create_adapter(config): return None\n"},
        )[1]
        self.raw = build_package(
            manifest, factory="synthetic_reader:create_adapter", payloads=payloads
        )[0]
        self.assertNotIn("hidden.py", self.install()["files"])

    def test_config_change_sdk_change_and_missing_consent_fail_before_install(self):
        plan = installation_preview(self.raw, **self.inputs)
        self.assertNotIn("never print me", json.dumps(plan))
        for changes in [{"config": {}}, {"trusted_sdk_digest": "0" * 64}]:
            with self.assertRaises(ValueError):
                install_inactive(
                    self.raw,
                    **{**self.inputs, **changes},
                    preview_digest=plan["preview_digest"],
                    source_reviewed=True,
                )
        with self.assertRaises(ValueError):
            install_inactive(
                self.raw, **self.inputs, preview_digest=plan["preview_digest"]
            )
        self.assertFalse(Path(plan["destination"]).exists())

    def test_runtime_lock_and_pending_receipt_block_installation(self):
        store = StateStore(self.root / "state.json")
        with store.exclusive(), self.assertRaises(BlockingIOError):
            self.install()
        store.save(
            GatewayState(
                phase="stop_unconfirmed",
                envelope=envelope(),
                signature="a" * 64,
                lease_token="aijl_" + "a" * 48,
            )
        )
        with self.assertRaisesRegex(ValueError, "pending job"):
            self.install()
        self.assertFalse(any(self.root.glob(".pending-install-*")))

    def test_tampered_snapshot_or_receipt_is_not_accepted_on_retry(self):
        result = self.install()
        target = Path(result["destination"])
        source = target / result["site_packages"] / "synthetic_reader.py"
        source.write_bytes(b"# changed\n")
        with self.assertRaisesRegex(ValueError, "differs"):
            self.install()
        result["files"]["synthetic_reader.py"] = sha256(source.read_bytes())
        (target / "receipt.json").write_bytes(canonical(result))
        with self.assertRaisesRegex(ValueError, "independently"):
            self.install()

    def test_modified_interpreter_and_failed_publish_do_not_look_installed(self):
        plan = installation_preview(self.raw, **self.inputs)
        with (
            patch(
                "airalogy_instrument_gateway.package_installation._sync_snapshot",
                side_effect=OSError("synthetic disk failure"),
            ),
            self.assertRaises(OSError),
        ):
            self.install()
        self.assertFalse(Path(plan["destination"]).exists())
        self.assertEqual(len(list(self.root.glob(".pending-install-*"))), 1)
        receipt = self.install()
        (Path(receipt["destination"]) / "bin/python").write_bytes(b"not an interpreter")
        with self.assertRaisesRegex(ValueError, "interpreter"):
            self.install()

    def test_root_and_installed_payload_cannot_be_symlinked(self):
        link = self.root / "alias"
        link.symlink_to(self.root)
        with self.assertRaises(ValueError):
            installation_preview(self.raw, **{**self.inputs, "root": link})
        result = self.install()
        source = (
            Path(result["destination"])
            / result["site_packages"]
            / "synthetic_reader.py"
        )
        source.unlink()
        source.symlink_to(__file__)
        with self.assertRaises(ValueError):
            self.install()

    def test_offline_dependency_resolution_rejects_ranges_and_missing_versions(self):
        for requirements in [
            ["missing==1.0.0"],
            ["present>=1.0.0"],
            ["present==2.0.0"],
            ["present==1.0.0; python_version >= '3'"],
        ]:
            with self.assertRaises(ValueError):
                _exact_requirements(
                    [
                        {
                            "name": "present",
                            "version": "1.0.0",
                            "requirements": requirements,
                        }
                    ]
                )
        _exact_requirements(
            [
                {
                    "name": "present",
                    "version": "1.0.0",
                    "requirements": ["present==1.0.0"],
                }
            ]
        )

    def test_installed_payload_cannot_acquire_external_hard_links(self):
        result = self.install()
        source = (
            Path(result["destination"])
            / result["site_packages"]
            / "synthetic_reader.py"
        )
        os.link(source, self.root / "linked-source.py")
        with self.assertRaisesRegex(ValueError, "hard links"):
            self.install()

    def test_cli_preview_then_confirm_does_not_expose_local_configuration(self):
        package, wheel, config = [
            self.root / name for name in ["input.zip", "sdk.whl", "local.json"]
        ]
        package.write_bytes(self.raw)
        wheel.write_bytes(self.sdk)
        config.write_bytes(canonical(self.inputs["config"]))
        args = [
            str(package),
            "--sdk-wheel",
            str(wheel),
            "--trusted-sdk-sha256",
            sha256(self.sdk),
            "--root",
            str(self.root),
            "--config",
            str(config),
        ]
        with redirect_stdout(io.StringIO()) as captured:
            self.assertEqual(main(["preview", *args]), 0)
        self.assertNotIn("never print me", captured.getvalue())
        digest = json.loads(captured.getvalue())["preview_digest"]
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["install", *args]), 2)
        with redirect_stdout(io.StringIO()) as captured:
            self.assertEqual(
                main(
                    ["install", *args, "--source-reviewed", "--confirm-digest", digest]
                ),
                0,
            )
        self.assertFalse(json.loads(captured.getvalue())["platform_authorized"])

    @unittest.skipUnless(
        os.getenv("RUN_ADAPTER_SANDBOX_TESTS") == "1",
        "Opt-in real Docker installation test",
    )
    def test_actual_built_sdk_installs_in_network_disabled_linux_container(self):
        from airalogy_instrument_gateway.package_sandbox import test_package

        manifest = json.loads((EXAMPLE / "manifest.json").read_text())
        payloads = {
            name: (EXAMPLE / name).read_bytes()
            for name in ["source/synthetic_reader.py", "licenses/LICENSE.txt"]
        }
        payloads["tests/test_reader.py"] = b"""
import json, pathlib, subprocess, sys, tempfile, unittest
from airalogy_instrument_gateway.package_contract import pack, sha256
from airalogy_instrument_gateway.package_installation import installation_preview, install_inactive, verify_installation
class LinuxInstallation(unittest.TestCase):
    def test_inactive_installation(self):
        bundle = pathlib.Path('/work/bundle')
        manifest = json.loads((bundle / 'manifest.json').read_bytes())
        raw = pack(manifest, {item['path']: (bundle / item['path']).read_bytes() for item in manifest['files']})
        sdk = next(pathlib.Path('/work').glob('airalogy_instrument_gateway-*.whl')).read_bytes()
        with tempfile.TemporaryDirectory(dir='/work') as directory:
            inputs = dict(root=pathlib.Path(directory), sdk_wheel=sdk, trusted_sdk_digest=sha256(sdk), config={})
            preview = installation_preview(raw, **inputs)
            receipt = install_inactive(raw, **inputs, preview_digest=preview['preview_digest'], source_reviewed=True)
            assert not receipt['activation_performed'] and not receipt['hardware_authorized']
            installed = pathlib.Path(receipt['destination'])
            assert verify_installation(installed) == receipt
            # /work deliberately disallows native execution. Keep that sandbox
            # protection and explicitly load only synthetic installed Python code
            # using the independently trusted system interpreter.
            script = "import sys; sys.path.insert(0, " + repr(str(installed / receipt['site_packages'])) + "); from importlib.metadata import entry_points; factory = next(iter(entry_points(group='airalogy.instrument_adapters', name='synthetic.reader'))).load(); assert factory(None).__class__.__name__ == 'SyntheticReader'"
            result = subprocess.run([sys.executable, '-I', '-B', '-c', script], capture_output=True, timeout=15)
            assert result.returncode == 0, result.stderr
"""
        raw = build_package(
            manifest, factory="synthetic_reader:create_adapter", payloads=payloads
        )[0]
        sdk_wheel = Path(os.environ["ADAPTER_TEST_SDK_WHEEL"]).read_bytes()
        result = test_package(
            raw,
            sdk_wheel=sdk_wheel,
            trusted_sdk_digest=sha256(sdk_wheel),
            image=os.environ["ADAPTER_TEST_IMAGE"],
            timeout_seconds=60,
        )
        self.assertTrue(result["passed"], result)
        self.assertFalse(result["hardware_authorized"])


if __name__ == "__main__":
    unittest.main()
