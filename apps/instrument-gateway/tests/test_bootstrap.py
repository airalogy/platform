"""Bootstrap software acceptance; synthetic verifier is NOT a signed release."""

import argparse
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "gateway_bootstrap", Path(__file__).parents[1] / "bootstrap.py"
)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def wheel(extra=None):
    files = {
        f"airalogy_instrument_gateway/{name}.py": b"raise RuntimeError('SDK code must not run during installation')\n"
        for name in bootstrap.MODULES.values()
    }
    files["airalogy_instrument_gateway/__init__.py"] = b""
    files["airalogy_instrument_gateway/setup_cli.py"] = (
        b"import sys; print('SYNTHETIC SETUP', sys.argv[1:])\n"
    )
    prefix = "airalogy_instrument_gateway-0.1.0.dist-info/"
    files[prefix + "METADATA"] = (
        b"Metadata-Version: 2.3\nName: airalogy-instrument-gateway\nVersion: 0.1.0\n"
    )
    files[prefix + "WHEEL"] = (
        b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    files.update(extra or {})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    return buffer.getvalue()


def verifier_result(plan):
    return subprocess.CompletedProcess(
        [],
        0,
        json.dumps(
            [
                {
                    "verificationResult": {
                        "statement": {
                            "subject": [{"digest": {"sha256": plan["wheel_sha256"]}}]
                        }
                    }
                }
            ]
        ).encode(),
    )


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.wheel = self.root / "sdk.whl"
        self.wheel.write_bytes(wheel())
        self.args = argparse.Namespace(
            wheel=str(self.wheel),
            wheel_sha256=bootstrap.digest(self.wheel.read_bytes()),
            release_tag="v0.1.0",
            commit="a" * 40,
            destination=str(self.root / "sdk-0.1.0"),
            gh=sys.executable,
            online_verification=True,
            bundle=None,
            trusted_root=None,
            trusted_root_sha256=None,
            confirm_digest=None,
            install_authorized=False,
        )

    def approve(self):
        preview = bootstrap.preview(self.args)
        self.args.confirm_digest = preview["confirm_digest"]
        self.args.install_authorized = True
        return preview["impact"]

    def install(self):
        plan = self.approve()
        with patch.object(
            bootstrap, "run_verifier", return_value=verifier_result(plan)
        ) as verifier:
            result = bootstrap.install(self.args)
        return result, verifier

    def test_preview_is_read_only_and_unverified(self):
        before = list(self.root.iterdir())
        with patch.object(bootstrap, "run_verifier") as run:
            plan = bootstrap.preview(self.args)
            run.assert_not_called()
        self.assertFalse(plan["provenance_verified"])
        self.assertFalse(plan["impact"]["hardware_authorized"])
        self.assertEqual(list(self.root.iterdir()), before)
        with self.assertRaises(ValueError):
            bootstrap.install(self.args)

    def test_changed_inputs_and_unknown_release_fail_before_verification(self):
        self.approve()
        self.wheel.write_bytes(b"changed")
        with patch.object(bootstrap, "run_verifier") as run:
            with self.assertRaises(ValueError):
                bootstrap.install(self.args)
            run.assert_not_called()
        for tag in ("main", "latest", "v0.1.0/../../x", "v0.1.0-rc.1"):
            self.args.release_tag = tag
            with self.assertRaises(ValueError):
                bootstrap.preview(self.args)

    def test_exact_certificate_workflow_source_and_runner_policy(self):
        plan = self.approve()
        command = bootstrap.verification_command(plan, self.wheel, {})
        expected = {
            "--hostname": "github.com",
            "--repo": "airalogy/platform",
            "--source-ref": "refs/tags/v0.1.0",
            "--source-digest": "a" * 40,
            "--signer-digest": "a" * 40,
            "--cert-identity": "https://github.com/airalogy/platform/.github/workflows/release.yml@refs/tags/v0.1.0",
            "--cert-oidc-issuer": "https://token.actions.githubusercontent.com",
            "--predicate-type": "https://slsa.dev/provenance/v1",
        }
        for key, value in expected.items():
            self.assertEqual(command[command.index(key) + 1], value)
        self.assertIn("--deny-self-hosted-runners", command)
        self.assertNotIn("--owner", command)
        # Exact certificate identity already binds workflow + release ref. The
        # CLI rejects combining it with any other certificate identity selector.
        for flag in ("--signer-workflow", "--signer-repo", "--cert-identity-regex"):
            self.assertNotIn(flag, command)

    def test_verifier_failure_missing_subject_and_timeout_never_install(self):
        plan = self.approve()
        for result in (
            subprocess.CompletedProcess([], 1, b""),
            subprocess.CompletedProcess([], 0, b"[]"),
            verifier_result({**plan, "wheel_sha256": "0" * 64}),
        ):
            with patch.object(bootstrap, "run_verifier", return_value=result):
                with self.assertRaises(ValueError):
                    bootstrap.install(self.args)
                self.assertFalse(Path(self.args.destination).exists())
        with (
            patch.object(
                bootstrap,
                "run_verifier",
                side_effect=subprocess.TimeoutExpired("synthetic verifier", 90),
            ),
            self.assertRaises(subprocess.TimeoutExpired),
        ):
            bootstrap.install(self.args)
        self.assertEqual(list(self.root.iterdir()), [self.wheel])

    def test_offline_requires_independent_root_and_passes_exact_files(self):
        self.args.online_verification = False
        with self.assertRaises(ValueError):
            self.approve()
        bundle, root = self.root / "proof.jsonl", self.root / "trusted-root.jsonl"
        bundle.write_bytes(b'{"synthetic": "proof"}')
        root.write_bytes(b'{"synthetic": "root"}')
        self.args.bundle, self.args.trusted_root = str(bundle), str(root)
        self.args.trusted_root_sha256 = "0" * 64
        with self.assertRaises(ValueError):
            self.approve()
        self.args.trusted_root_sha256 = bootstrap.digest(root.read_bytes())
        plan = self.approve()

        def check(command, **kwargs):
            self.assertEqual(
                Path(command[command.index("--bundle") + 1]).read_bytes(),
                bundle.read_bytes(),
            )
            self.assertEqual(
                Path(command[command.index("--custom-trusted-root") + 1]).read_bytes(),
                root.read_bytes(),
            )
            return verifier_result(plan)

        with patch.object(bootstrap, "run_verifier", side_effect=check):
            self.assertEqual(bootstrap.install(self.args)["state"], "installed")

    def test_install_only_copies_sdk_retry_is_offline_and_launch_is_explicit(self):
        result, verifier = self.install()
        self.assertFalse(result["reused"])
        self.assertEqual(verifier.call_count, 1)
        receipt = bootstrap.inspect(self.args.destination)
        self.assertEqual(receipt["confirm_digest"], self.args.confirm_digest)
        with patch.object(bootstrap, "run_verifier") as run:
            self.assertTrue(bootstrap.install(self.args)["reused"])
            run.assert_not_called()
        # Real child process, isolated standard-library+SDK path. The fixture
        # fails if any driver/runtime module is imported during installation.
        child = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                str(Path(self.args.destination) / "airalogy-instrument-bootstrap.py"),
                "launch",
                "--destination",
                self.args.destination,
                "--",
                "setup",
                "--help",
            ],
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertIn(b"SYNTHETIC SETUP", child.stdout)
        bootstrap.inspect(self.args.destination)

    def test_tamper_partial_install_and_foreign_files_are_not_repaired(self):
        self.install()
        root = Path(self.args.destination)
        selected = root / "sdk/airalogy_instrument_gateway/setup_cli.py"
        selected.chmod(0o600)
        selected.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "changed"):
            bootstrap.inspect(root)
        with self.assertRaises(ValueError):
            bootstrap.install(self.args)
        self.args.destination = str(self.root / "partial")
        Path(self.args.destination).mkdir(mode=0o700)
        (Path(self.args.destination) / "device-data.txt").write_text("keep")
        with self.assertRaises(ValueError):
            bootstrap.preview(self.args)
        self.assertEqual(
            (Path(self.args.destination) / "device-data.txt").read_text(), "keep"
        )

    def test_symlinks_runtime_roots_and_unsafe_wheels_fail_closed(self):
        (self.root / "gateway.json").write_text("private runtime remains untouched")
        with self.assertRaisesRegex(ValueError, "separate"):
            bootstrap.preview(self.args)
        (self.root / "gateway.json").unlink()
        link = self.root / "linked.whl"
        link.symlink_to(self.wheel)
        self.args.wheel = str(link)
        with self.assertRaises(ValueError):
            bootstrap.preview(self.args)
        for extra in (
            {"../escape.py": b""},
            {"airalogy_instrument_gateway/" + "nested/" * 17 + "x.py": b""},
            {"airalogy_instrument_gateway/" + "x" * 241: b""},
            {"airalogy_instrument_gateway/setup_cli.py/child.py": b""},
            {"startup.pth": b""},
            {"airalogy_instrument_gateway/x.pth": b""},
            {
                "airalogy_instrument_gateway-0.1.0.dist-info/METADATA": b"Name: airalogy-instrument-gateway\nVersion: 0.1.0\nRequires-Dist: remote-code\n"
            },
        ):
            with self.assertRaises(ValueError):
                bootstrap.unpack(wheel(extra), "0.1.0")

    def test_modified_sdk_or_interpreter_cannot_launch(self):
        self.install()
        arguments = argparse.Namespace(
            destination=self.args.destination, arguments=["setup", "--help"]
        )
        original = bootstrap.executable(sys.executable)
        with (
            patch.object(
                bootstrap, "executable", return_value={**original, "sha256": "0" * 64}
            ),
            patch.object(bootstrap.os, "execve") as start,
        ):
            with self.assertRaisesRegex(ValueError, "Python changed"):
                bootstrap.launch(arguments)
            start.assert_not_called()
        (Path(self.args.destination) / "unexpected.py").write_text(
            "raise AssertionError('must not run')"
        )
        with patch.object(bootstrap.os, "execve") as start:
            with self.assertRaisesRegex(ValueError, "Unexpected"):
                bootstrap.launch(arguments)
            start.assert_not_called()

    def test_verifier_output_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "bounds"):
            bootstrap.run_verifier(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    f"import sys;sys.stdout.write('x'*{bootstrap.MAX_PROOF + 1})",
                ]
            )

    def test_interrupted_copy_is_not_installed_or_silently_repaired(self):
        plan = self.approve()
        with (
            patch.object(bootstrap, "run_verifier", return_value=verifier_result(plan)),
            patch.object(
                bootstrap.os, "fsync", side_effect=OSError("synthetic disk failure")
            ),
            self.assertRaises(OSError),
        ):
            bootstrap.install(self.args)
        self.assertTrue(Path(self.args.destination).exists())
        self.assertFalse((Path(self.args.destination) / "receipt.json").exists())
        with patch.object(bootstrap, "run_verifier") as verifier:
            with self.assertRaises(OSError):
                bootstrap.install(self.args)
            verifier.assert_not_called()

    def test_release_gate_attests_bootstrap_before_verifying_actual_install(self):
        root = Path(__file__).parents[3]
        release = (root / ".github/workflows/release.yml").read_text()
        self.assertLess(
            release.index("Include independently verifiable SDK bootstrap"),
            release.index("id: gateway_provenance"),
        )
        self.assertIn("steps.gateway_provenance.outputs.bundle-path", release)
        self.assertIn('--commit "$GITHUB_SHA" --verify-release', release)
        workflow = (root / ".github/workflows/instrument-gateway.yml").read_text()
        self.assertIn("node scripts/pre-push.mjs --check gateway-cli", workflow)
        self.assertIn("tests/check_bootstrap_install.py", workflow)

    @unittest.skipUnless(
        os.getenv("RUN_BOOTSTRAP_ATTESTATION_TESTS") == "1",
        "opt in to installed GitHub verifier",
    )
    def test_real_github_cli_rejects_unsigned_offline_fixture(self):
        self.args.gh = shutil.which("gh")
        self.assertIsNotNone(self.args.gh)
        self.args.online_verification = False
        bundle, root = self.root / "unsigned.jsonl", self.root / "untrusted.jsonl"
        bundle.write_text("{}")
        root.write_text("{}")
        self.args.bundle, self.args.trusted_root = str(bundle), str(root)
        self.args.trusted_root_sha256 = bootstrap.digest(root.read_bytes())
        self.approve()

        def real_verifier(command):
            # Capture diagnostics only for this owned, unsigned offline fixture.
            # A parser/flag error must not masquerade as cryptographic rejection.
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=30,
                env={**os.environ, "GH_HOST": "github.com", "GH_PROMPT_DISABLED": "1"},
            )
            self.assertNotEqual(result.returncode, 0)
            diagnostics = result.stderr.decode(errors="replace").lower()
            self.assertNotIn("unknown flag", diagnostics)
            self.assertNotIn("none of the others can be", diagnostics)
            self.assertRegex(
                diagnostics, r"trusted root|bundle version|unsupported media type"
            )
            return result

        with patch.object(bootstrap, "run_verifier", side_effect=real_verifier) as run:
            with self.assertRaisesRegex(ValueError, "provenance"):
                bootstrap.install(self.args)
            run.assert_called_once()
        self.assertFalse(Path(self.args.destination).exists())


if __name__ == "__main__":
    unittest.main()
