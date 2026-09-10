import io
import json
import os
import subprocess
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from managed_fixture import TARGET, package
from test_gateway import envelope
from test_installation_manager import FakePlatform
from test_output_delivery import ReceivingClient, file_job
from test_package_installation import sdk

from airalogy_instrument_gateway.activation_cli import launch_command, main
from airalogy_instrument_gateway.activation_contract import SCHEMA, activation_digest
from airalogy_instrument_gateway.client import GatewayAPIError
from airalogy_instrument_gateway.credentials import write_credentials
from airalogy_instrument_gateway.installation_contract import receipt_summary
from airalogy_instrument_gateway.installation_manager import apply, prepare
from airalogy_instrument_gateway.managed_runtime import (
    ManagedAdapter,
    inspect_start,
    run_installed,
)
from airalogy_instrument_gateway.package_contract import sha256
from airalogy_instrument_gateway.security import expected_job_signature
from airalogy_instrument_gateway.state import GatewayState, StateStore


@unittest.skipUnless(os.name == "posix", "POSIX installation support")
class ManagedRuntimeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.calls, self.result, self.revoked = [], None, False
        test = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.respond()

            def do_POST(self):
                self.respond()

            def do_PUT(self):
                self.respond()

            def respond(self):
                data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                payload = json.loads(data or b"{}") if self.command != "PUT" else {}
                test.calls.append((self.path, payload))
                if (
                    self.headers.get("X-Airalogy-Gateway-Token")
                    != test.credentials["gateway_token"]
                ):
                    self.send_error(401)
                    return
                if "/outputs/" in self.path:
                    try:
                        if self.path.endswith("/capture"):
                            value = test.receiving.report_capture(
                                test.raw["job_id"], "unused", payload["capture"]
                            )
                        elif self.path.endswith("/finalize"):
                            value = test.receiving.finalize_outputs(
                                test.raw["job_id"], "unused", payload["capture"]
                            )
                        else:
                            capture = test.receiving.capture["files"][0]
                            if (
                                self.headers.get("X-Airalogy-Content-SHA256")
                                != capture["sha256"]
                                or self.headers.get("Content-Type")
                                != capture["media_type"]
                            ):
                                self.send_error(409)
                                return
                            value = test.receiving.upload_output(
                                test.raw["job_id"],
                                "unused",
                                self.path.rsplit("/", 1)[1],
                                capture,
                                io.BytesIO(data),
                            )
                    except GatewayAPIError:
                        self.send_error(503, "Synthetic lost upload acknowledgment")
                        return
                elif self.path.endswith("/activation"):
                    value = {"activation": None} if test.revoked else test.response
                elif self.path.endswith("/lease"):
                    if test.raw is None:
                        value = {"job": None}
                    else:
                        value = {
                            "job": test.raw,
                            "signature": expected_job_signature(
                                test.raw, test.credentials["gateway_token"]
                            ),
                            "lease_token": "aijl_" + "a" * 43,
                        }
                elif self.path.endswith("/complete"):
                    test.result = payload
                    value = {"status": "completed"}
                    if getattr(test, "output_mode", False):
                        value["files_pending"] = test.receiving.finalized is None
                else:
                    value = {"status": "running"}
                body = json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        output_mode = getattr(self, "output_mode", False)
        self.output_root = self.root / "synthetic-exports" if output_mode else None
        if self.output_root:
            self.output_root.mkdir(mode=0o700)
        raw, wheel = package(file_outputs=output_mode), sdk()
        for name, content in (
            ("package.zip", raw),
            ("sdk.whl", wheel),
            (
                "config.json",
                json.dumps({"output_root": str(self.output_root)}).encode()
                if output_mode
                else b"{}",
            ),
        ):
            (self.root / name).write_bytes(content)
        self.path, self.credential_path = (
            self.root / "request.json",
            self.root / "credential.json",
        )
        self.credentials = {
            "schema": "airalogy.gateway-credential.v1",
            "platform_url": f"http://127.0.0.1:{server.server_port}",
            "lab_id": str(uuid4()),
            "gateway_id": str(uuid4()),
            "gateway_token": "aigw_" + "a" * 43,
        }
        write_credentials(self.credential_path, self.credentials)
        self.request = prepare(
            destination=self.path,
            platform_url=self.credentials["platform_url"],
            lab_id=self.credentials["lab_id"],
            gateway_id=self.credentials["gateway_id"],
            package=self.root / "package.zip",
            sdk_wheel=self.root / "sdk.whl",
            trusted_sdk_digest=sha256(wheel),
            config=self.root / "config.json",
            root=self.root,
        )
        installed = FakePlatform(self.request, raw)
        apply(self.path, source_reviewed=True, client=installed)
        self.id = str(uuid4())
        self.raw = envelope()
        self.raw["command"].update(
            key="reader.measure", version="1.0.0", arguments={"sample_count": 2}
        )
        pin = {
            "schema": SCHEMA,
            "id": self.id,
            "binding_id": self.request["id"],
            "qualification_id": str(uuid4()),
            "authorization_digest": "a" * 64,
            "installation_id": self.request["descriptor"]["installation_id"],
            "target_digest": activation_digest(TARGET),
        }
        self.raw["activation"] = pin
        if output_mode:
            receiving = file_job()["file_outputs"]
            receiving["plan"].update(
                job_id=self.raw["job_id"],
                outputs=[
                    {
                        "name": "synthetic.csv",
                        "media_type": "text/csv",
                        "max_bytes": 4096,
                        "required": True,
                    }
                ],
            )
            receiving["destination"].update(
                activation_id=self.id, task_id=self.raw["task_id"]
            )
            self.raw["file_outputs"] = receiving
            self.receiving = ReceivingClient(self.raw)
        command = {
            key: value
            for key, value in self.raw["command"].items()
            if key != "arguments"
        }
        command.update(
            id=str(uuid4()),
            resource_revision_id=self.raw["resource"]["revision_id"],
            resource_revision=self.raw["resource"]["revision"],
        )
        activation = {
            "pin": pin,
            "lab_id": self.credentials["lab_id"],
            "gateway_id": self.credentials["gateway_id"],
            "resource_id": self.raw["resource"]["id"],
            "descriptor": self.request["descriptor"],
            "receipt": installed.status["receipt"],
            "target": TARGET,
            "commands": [command],
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }
        self.response = {
            "activation": activation,
            "signature": expected_job_signature(
                activation, self.credentials["gateway_token"]
            ),
        }

    def preview(self, **kwargs):
        return inspect_start(
            self.path,
            self.credential_path,
            self.id,
            output_root=self.output_root,
            **kwargs,
        )

    def run_child(self, *, recover=False):
        preview, _, local, _ = self.preview(recover=recover)
        args = [
            "--request",
            str(self.path),
            "--credentials",
            str(self.credential_path),
            "--activation",
            self.id,
            "--confirm-digest",
            preview["preview_digest"],
            "--once",
        ]
        if recover:
            args.append("--recover")
        if self.output_root is not None:
            args.extend(["--output-root", str(self.output_root)])
        return subprocess.run(
            launch_command(local, args),
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
            cwd=self.root,
        )

    def test_actual_verified_child_executes_pinned_job_and_keeps_snapshot_unchanged(
        self,
    ):
        before = self.preview()[2][4]
        result = self.run_child()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.result["result"]["value"], 0.84)
        self.assertTrue(self.result["result"]["simulation_only"])
        self.assertEqual(receipt_summary(before), receipt_summary(self.preview()[2][4]))
        self.assertIsNone(StateStore(self.root / "state.json").load())
        for path, payload in self.calls:
            if path.endswith(("/lease", "/start")):
                self.assertEqual(payload["activation"], self.raw["activation"])

    def test_preview_never_imports_driver_and_start_requires_consent(self):
        with (
            patch("subprocess.call") as process,
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            common = [
                "--request",
                str(self.path),
                "--credentials",
                str(self.credential_path),
                "--activation",
                self.id,
            ]
            self.assertEqual(main(["preview", *common]), 0)
            self.assertEqual(main(["run", *common]), 2)
            process.assert_not_called()
        with self.assertRaisesRegex(ValueError, "isolated"):
            run_installed(
                self.path,
                self.credential_path,
                self.id,
                confirm_digest=self.preview()[0]["preview_digest"],
                once=True,
            )

    def test_installed_file_producer_and_receipt_only_child_recovery(self):
        self.output_mode = True
        self.setUp()
        self.receiving.lose = "upload"
        with self.assertRaisesRegex(ValueError, "output-root"):
            inspect_start(self.path, self.credential_path, self.id)
        first = self.run_child()
        self.assertEqual(first.returncode, 2, first.stderr)
        store = StateStore(self.root / "state.json")
        self.assertEqual(store.load().phase, "outputs_pending")
        self.assertTrue((self.root / "synthetic-driver-initialized").is_file())
        (self.output_root / "synthetic.csv").unlink()
        self.output_root.rmdir()
        self.revoked = True
        self.assertFalse(
            self.preview(recover=True)[0]["startup_may_initialize_equipment"]
        )
        second = self.run_child(recover=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIsNone(store.load())
        self.assertIsNotNone(self.receiving.finalized)
        self.assertEqual(sum(path.endswith("/start") for path, _ in self.calls), 1)
        self.assertEqual(sum(call[0] == "upload" for call in self.receiving.calls), 1)
        lease = next(payload for path, payload in self.calls if path.endswith("/lease"))
        self.assertEqual(
            lease["file_delivery_version"], "airalogy.instrument-output-plan.v1"
        )

    def test_revocation_blocks_new_start_but_saved_result_recovery_still_works(self):
        _, response, _, saved = self.preview()
        write_credentials(saved, response)
        result = {"value": 0.84, "unit": "synthetic_unit", "simulation_only": True}
        store = StateStore(self.root / "state.json")
        store.save(
            GatewayState(
                phase="completion_pending",
                envelope=self.raw,
                signature=expected_job_signature(
                    self.raw, self.credentials["gateway_token"]
                ),
                lease_token="aijl_" + "a" * 43,
                result=result,
            )
        )
        self.revoked = True
        self.assertFalse(
            self.preview(recover=True)[0]["startup_may_initialize_equipment"]
        )
        run = self.run_child(recover=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.result["result"], result)
        self.assertFalse(
            any(path.endswith(("/lease", "/start")) for path, _ in self.calls)
        )
        with self.assertRaisesRegex(ValueError, "No currently"):
            self.preview()

    def test_changed_inputs_signature_expiry_and_identity_fail_closed(self):
        original = self.response["signature"]
        self.response["signature"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "signature"):
            self.preview()
        self.response["signature"] = original
        (self.root / "config.json").write_text('{"changed": true}')
        with self.assertRaisesRegex(ValueError, "changed"):
            self.preview()
        (self.root / "config.json").write_text("{}")
        self.response["activation"]["expires_at"] = (
            datetime.now(UTC) - timedelta(seconds=1)
        ).isoformat()
        self.response["signature"] = expected_job_signature(
            self.response["activation"], self.credentials["gateway_token"]
        )
        with self.assertRaisesRegex(ValueError, "expired"):
            self.preview()
        driver = type(
            "Driver",
            (),
            {
                "identity": lambda _: {**TARGET, "firmware": "changed"},
                "safe_stop": lambda *_: "stopped",
            },
        )()
        adapter = ManagedAdapter(driver, self.response["activation"], lambda: None)
        with self.assertRaisesRegex(ValueError, "identity changed"):
            adapter.check_identity()
        self.assertEqual(adapter.safe_stop(None, "revoked"), "stopped")

    def test_shared_activation_contract_matches_api(self):
        from airalogy_instrument_gateway import activation_contract

        api = (
            Path(__file__).resolve().parents[3]
            / "apps/api/app/services/instrument_activation_contract.py"
        )
        self.assertEqual(
            api.read_bytes(), Path(activation_contract.__file__).read_bytes()
        )
