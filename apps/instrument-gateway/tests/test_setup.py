import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from test_installation_manager import FakePlatform
from test_package_installation import sdk
from test_packages import example

from airalogy_instrument_gateway.client import GatewayAPIError
from airalogy_instrument_gateway.credentials import read_credentials
from airalogy_instrument_gateway.package_contract import sha256
from airalogy_instrument_gateway.setup_cli import SetupServer
from airalogy_instrument_gateway.setup_workspace import SetupWorkspace
from airalogy_instrument_gateway.state import GatewayState, StateStore


@unittest.skipUnless(os.name == "posix", "POSIX local setup support")
class SetupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.workspace = SetupWorkspace(self.root)
        self.scope = {
            "platform_url": "https://lab.example.edu/api",
            "lab_id": str(uuid4()),
            "gateway_id": str(uuid4()),
            "client_name": "Synthetic station",
        }

    def initialize(self):
        preview = self.workspace.dispatch("identity-preview", self.scope)
        return self.workspace.dispatch(
            "identity-confirm", {"confirmation": preview["confirmation"]}
        )

    def files(self):
        self.raw, wheel = example()[0], sdk()
        data = {}
        for kind, raw in (
            ("package", self.raw),
            ("sdk_wheel", wheel),
            ("config", b'{"private":"do-not-transmit"}'),
        ):
            data[kind] = self.workspace.upload(kind, raw)["path"]
        data["trusted_sdk_digest"] = sha256(wheel)
        return data

    def request(self):
        self.initialize()
        inputs = self.files()
        preview = self.workspace.dispatch("installation-preview", inputs)
        return self.workspace.dispatch(
            "installation-confirm", {"confirmation": preview["confirmation"]}
        )

    def test_preview_does_not_create_identity_and_confirmation_is_exclusive(self):
        preview = self.workspace.dispatch("identity-preview", self.scope)
        self.assertFalse((self.root / "gateway.json").exists())
        state = self.workspace.dispatch(
            "identity-confirm", {"confirmation": preview["confirmation"]}
        )
        credentials = read_credentials(self.root / "gateway.json")
        self.assertEqual(state["scope"], self.scope)
        self.assertNotIn(credentials["gateway_token"], json.dumps(state))
        self.assertEqual((self.root / "gateway.json").stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            self.workspace.dispatch(
                "identity-confirm", {"confirmation": preview["confirmation"]}
            )
        with self.assertRaises(ValueError):
            self.workspace.dispatch(
                "identity-preview", {**self.scope, "gateway_id": str(uuid4())}
            )
        self.assertEqual(read_credentials(self.root / "gateway.json"), credentials)

    def test_bad_scope_unexpected_fields_and_expired_preview_are_rejected(self):
        for change in (
            {"platform_url": "http://192.0.2.1/api"},
            {"lab_id": "bad"},
            {"gateway_token": "not-accepted"},
        ):
            with self.assertRaises(ValueError):
                self.workspace.dispatch("identity-preview", {**self.scope, **change})
        preview = self.workspace.dispatch("identity-preview", self.scope)
        with (
            patch(
                "airalogy_instrument_gateway.setup_workspace.time.monotonic",
                return_value=float("inf"),
            ),
            self.assertRaises(ValueError),
        ):
            self.workspace.dispatch(
                "identity-confirm", {"confirmation": preview["confirmation"]}
            )
        self.assertFalse((self.root / "gateway.json").exists())

    def test_file_copies_are_private_bounded_and_not_overwritten(self):
        first = self.workspace.upload("config", b'{"secret":"private"}')
        second = self.workspace.upload("config", b"{}")
        self.assertNotEqual(first["path"], second["path"])
        self.assertEqual(Path(first["path"]).stat().st_mode & 0o777, 0o600)
        self.assertNotIn("secret", json.dumps(first))
        for kind, raw in (("other", b"{}"), ("config", b"x" * 16385), ("config", b"")):
            with self.assertRaises(ValueError):
                self.workspace.upload(kind, raw)

    def test_linked_copy_directory_and_shared_root_are_refused(self):
        target = self.root / "elsewhere"
        target.mkdir(mode=0o700)
        (self.root / "setup-inputs").symlink_to(target)
        with self.assertRaises(ValueError):
            self.workspace.upload("config", b"{}")
        self.root.chmod(0o755)
        try:
            with self.assertRaises(ValueError):
                self.workspace.dispatch("state", {})
        finally:
            self.root.chmod(0o700)

    def test_copy_quota_and_busy_workspace_do_not_write_more_files(self):
        for _ in range(64):
            self.workspace.upload("config", b"{}")
        with self.assertRaisesRegex(ValueError, "quota"):
            self.workspace.upload("config", b"{}")
        self.assertEqual(len(list((self.root / "setup-inputs").iterdir())), 64)
        with self.workspace.lock:
            with self.assertRaises(RuntimeError):
                self.workspace.dispatch("identity-preview", self.scope)
            with self.assertRaises(RuntimeError):
                self.workspace.upload("config", b"{}")
        self.assertFalse((self.root / "gateway.json").exists())

    def test_changed_installation_inputs_fail_before_creating_private_request(self):
        self.initialize()
        inputs = self.files()
        preview = self.workspace.dispatch("installation-preview", inputs)
        self.assertNotIn("do-not-transmit", json.dumps(preview))
        Path(inputs["config"]).write_bytes(b'{"changed":true}')
        with self.assertRaisesRegex(ValueError, "changed after preview"):
            self.workspace.dispatch(
                "installation-confirm", {"confirmation": preview["confirmation"]}
            )
        self.assertEqual(list(self.root.glob("installation-*.json")), [])

    def test_saved_public_request_survives_restart_but_preview_does_not(self):
        result = self.request()
        restored = SetupWorkspace(self.root)
        state = restored.dispatch("state", {})
        self.assertEqual(
            state["requests"],
            [{"local_id": result["local_id"], "request": result["request"]}],
        )
        serialized = json.dumps(state)
        self.assertNotIn("installation_token", serialized)
        self.assertNotIn("gateway_token", serialized)
        self.assertNotIn("do-not-transmit", serialized)
        self.assertFalse(state["hardware_authorized"])
        with self.assertRaises(ValueError):
            restored.dispatch(
                "installation-confirm", {"confirmation": "previous-session"}
            )

    def test_identity_replacement_invalidates_installation_confirmation(self):
        self.initialize()
        preview = self.workspace.dispatch("installation-preview", self.files())
        path = self.root / "gateway.json"
        credentials = read_credentials(path)
        credentials["gateway_token"] = "aigw_" + "b" * 43
        path.write_text(json.dumps(credentials))
        with self.assertRaisesRegex(ValueError, "identity changed"):
            self.workspace.dispatch(
                "installation-confirm", {"confirmation": preview["confirmation"]}
            )
        self.assertEqual(list(self.root.glob("installation-*.json")), [])

    def test_real_installation_lost_receipt_recovers_without_redownload(self):
        result = self.request()
        platform = FakePlatform(result["request"], self.raw)
        with (
            patch(
                "airalogy_instrument_gateway.setup_workspace.InstallationClient",
                return_value=platform,
            ),
            patch(
                "airalogy_instrument_gateway.installation_manager.InstallationClient",
                return_value=platform,
            ),
        ):
            offered = self.workspace.dispatch(
                "installation-status", {"local_id": result["local_id"]}
            )
            with self.assertRaises(ValueError):
                self.workspace.dispatch(
                    "installation-apply",
                    {"confirmation": offered["confirmation"], "source_reviewed": False},
                )
            self.assertEqual(platform.calls, ["status"])
            platform.lose_response = True
            with self.assertRaises(GatewayAPIError):
                self.workspace.dispatch(
                    "installation-apply",
                    {"confirmation": offered["confirmation"], "source_reviewed": True},
                )
            self.assertEqual(
                platform.calls, ["status", "status", "claim", "package", "receipt"]
            )
            platform.calls.clear()
            restored = SetupWorkspace(self.root)
            offered = restored.dispatch(
                "installation-status", {"local_id": result["local_id"]}
            )
            installed = restored.dispatch(
                "installation-apply",
                {"confirmation": offered["confirmation"], "source_reviewed": True},
            )
            self.assertEqual(platform.calls, ["status", "status", "receipt"])
            self.assertEqual(installed["state"], "installed")
            self.assertFalse(installed["activation_performed"])

    def test_pending_job_and_foreign_request_cannot_be_bypassed(self):
        result = self.request()
        platform = FakePlatform(result["request"], self.raw)
        with (
            patch(
                "airalogy_instrument_gateway.setup_workspace.InstallationClient",
                return_value=platform,
            ),
            patch(
                "airalogy_instrument_gateway.installation_manager.InstallationClient",
                return_value=platform,
            ),
        ):
            offered = self.workspace.dispatch(
                "installation-status", {"local_id": result["local_id"]}
            )
            journal = StateStore(self.root / "state.json")
            journal.save(
                GatewayState("stop_unconfirmed", {}, "signature", "aijl_fixture")
            )
            with self.assertRaisesRegex(ValueError, "Reconcile"):
                self.workspace.dispatch(
                    "installation-apply",
                    {"confirmation": offered["confirmation"], "source_reviewed": True},
                )
            self.assertEqual(platform.calls, ["status"])
            self.assertEqual(journal.load().phase, "stop_unconfirmed")
        path = self.root / f"installation-{result['local_id']}.json"
        value = json.loads(path.read_text())
        value["platform_url"] = "https://other.example.edu/api"
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "another"):
            self.workspace.dispatch("state", {})

    def test_http_requires_exact_host_origin_token_and_bounded_requests(self):
        server = SetupServer(self.workspace)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:

            def call(path="/api", method="POST", headers=None, raw=None):
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=10
                )
                actual = {
                    "Origin": server.origin,
                    "Content-Type": "application/json",
                    "X-Airalogy-Setup": server.token,
                    **(headers or {}),
                }
                connection.request(
                    method,
                    path,
                    body=raw
                    if raw is not None
                    else json.dumps({"operation": "state", "data": {}}),
                    headers=actual,
                )
                response = connection.getresponse()
                body, status, returned = (
                    response.read(),
                    response.status,
                    dict(response.getheaders()),
                )
                connection.close()
                return status, body, returned

            self.assertEqual(call()[0], 200)
            for override, status in (
                ({"Host": "evil.example"}, 403),
                ({"Origin": "https://evil.example"}, 403),
                ({"X-Airalogy-Setup": "bad"}, 401),
            ):
                self.assertEqual(call(headers=override)[0], status)
            status, body, headers = call("/", "GET")
            self.assertEqual(status, 200)
            self.assertNotIn(server.token.encode(), body)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
            self.assertEqual(call("/../gateway.json", "GET")[0], 404)
            self.assertEqual(call(raw=b"{" * 32769)[0], 409)
            self.assertEqual(call(raw=b'{"operation":"run","data":{}}')[0], 409)
            self.assertEqual(
                call(
                    "/upload/config",
                    headers={"Content-Type": "application/octet-stream"},
                    raw=b"{}",
                )[0],
                200,
            )
            self.assertEqual(
                call(
                    "/upload/config",
                    headers={"Content-Type": "application/octet-stream"},
                    raw=b"x" * 16385,
                )[0],
                409,
            )
            with patch.object(
                self.workspace,
                "dispatch",
                side_effect=GatewayAPIError("PRIVATE-REMOTE-ERROR"),
            ):
                status, body, _ = call()
                self.assertEqual(status, 409)
                self.assertNotIn(b"PRIVATE-REMOTE-ERROR", body)
                self.assertEqual(json.loads(body)["code"], "platformFailed")
            server.expires_at = 0
            self.assertEqual(call()[0], 401)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
