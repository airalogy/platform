import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from airalogy_instrument_gateway.client import GatewayAPIError
from airalogy_instrument_gateway.installation_contract import validate_request
from airalogy_instrument_gateway.installation_manager import (
    InstallationClient,
    apply,
    prepare,
    read_request,
)
from airalogy_instrument_gateway.package_contract import sha256
from airalogy_instrument_gateway.state import StateStore
from test_package_installation import sdk
from test_packages import example


class FakePlatform:
    def __init__(self, request, raw):
        self.status = {
            "state": "authorized",
            "descriptor": request["descriptor"],
            "installer_fingerprint": request["fingerprint"],
        }
        self.raw, self.calls, self.lose_response = raw, [], False

    def call(self, operation, payload=None):
        self.calls.append(operation)
        if operation == "claim":
            self.status["state"] = "installing"
        elif operation == "package":
            return self.raw
        elif operation == "receipt":
            self.status.update(state="installed", receipt=payload["receipt"])
            if self.lose_response:
                self.lose_response = False
                raise GatewayAPIError("Injected lost response")
        return self.status.copy()


@unittest.skipUnless(os.name == "posix", "POSIX installation support")
class ManagerTests(unittest.TestCase):
    def test_shared_installation_contract_matches_api_copy(self):
        from airalogy_instrument_gateway import installation_contract

        root = Path(__file__).resolve().parents[3]
        api = root / "apps/api/app/services/instrument_installation_contract.py"
        self.assertEqual(
            api.read_bytes(), Path(installation_contract.__file__).read_bytes()
        )

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.raw, self.sdk = example()[0], sdk()
        for name, value in [
            ("package.zip", self.raw),
            ("sdk.whl", self.sdk),
            ("config.json", b'{"local_private_value":"not-for-platform"}'),
        ]:
            (self.root / name).write_bytes(value)
        self.path = self.root / "private.json"
        self.request = prepare(
            destination=self.path,
            platform_url="https://platform.example",
            lab_id=str(uuid4()),
            gateway_id=str(uuid4()),
            package=self.root / "package.zip",
            sdk_wheel=self.root / "sdk.whl",
            trusted_sdk_digest=sha256(self.sdk),
            config=self.root / "config.json",
            root=self.root,
        )
        self.client = FakePlatform(self.request, self.raw)

    def test_private_identity_never_enters_public_request_and_is_exclusive(self):
        content = read_request(self.path)
        public = json.dumps(self.request)
        self.assertNotIn(content["installation_token"], public)
        self.assertNotIn(str(self.root), public)
        self.assertNotIn("not-for-platform", public)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            validate_request(
                {**self.request, "installation_token": content["installation_token"]}
            )
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            read_request(self.path)

    def test_real_inactive_install_and_lost_receipt_response_retry_without_download(
        self,
    ):
        self.client.lose_response = True
        with self.assertRaises(GatewayAPIError):
            apply(self.path, source_reviewed=True, client=self.client)
        self.assertEqual(self.client.calls, ["status", "claim", "package", "receipt"])
        self.assertNotIn(str(self.root), json.dumps(self.client.status["receipt"]))
        self.client.calls.clear()
        result = apply(self.path, source_reviewed=True, client=self.client)
        self.assertEqual(self.client.calls, ["status", "receipt"])
        self.assertFalse(result["activation_performed"])
        self.assertFalse(result["hardware_authorized"])

    def test_authority_changed_download_and_local_config_fail_closed(self):
        self.client.status["state"] = "revoked"
        with self.assertRaisesRegex(ValueError, "not current"):
            apply(self.path, source_reviewed=True, client=self.client)
        self.client.status["state"] = "authorized"
        self.client.raw = b"tampered"
        with self.assertRaisesRegex(ValueError, "Downloaded archive"):
            apply(self.path, source_reviewed=True, client=self.client)
        self.assertFalse(
            (self.root / self.request["descriptor"]["installation_id"]).exists()
        )
        (self.root / "config.json").write_text("{}")
        self.client.calls.clear()
        with self.assertRaisesRegex(ValueError, "changed"):
            apply(self.path, source_reviewed=True, client=self.client)
        self.assertEqual(self.client.calls, [])

    def test_runtime_lock_blocks_before_network_and_explicit_consent_is_required(self):
        with self.assertRaises(ValueError):
            apply(self.path, client=self.client)
        with (
            StateStore(self.root / "state.json").exclusive(),
            self.assertRaises(BlockingIOError),
        ):
            apply(self.path, source_reviewed=True, client=self.client)
        self.assertEqual(self.client.calls, [])

    def test_missing_installed_snapshot_requires_reconciliation_not_reinstallation(
        self,
    ):
        self.client.status["state"] = "installed"
        with self.assertRaisesRegex(ValueError, "missing"):
            apply(self.path, source_reviewed=True, client=self.client)
        self.assertEqual(self.client.calls, ["status"])

    def test_http_transport_never_sends_runtime_identity_or_follows_redirects(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                received.append((self.path, dict(self.headers)))
                if self.path.endswith("/claim"):
                    self.send_response(302)
                    self.send_header("Location", "/must-not-follow")
                    self.end_headers()
                    self.wfile.write(b"private remote error body")
                    return
                raw = b"{}" if self.path.endswith("/status") else b"x" * 65537
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            content = read_request(self.path)
            content["platform_url"] = f"http://127.0.0.1:{server.server_port}/api"
            client = InstallationClient(content)
            self.assertEqual(client.call("status"), {})
            with self.assertRaises(GatewayAPIError) as error:
                client.call("claim")
            self.assertNotIn("private remote error body", str(error.exception))
            with self.assertRaisesRegex(GatewayAPIError, "limit"):
                client.call("receipt", {})
            self.assertEqual(len(received), 3)
            for route, headers in received:
                self.assertTrue(route.startswith("/api/instrument-installations/"))
                self.assertEqual(
                    headers["X-Airalogy-Installation-Token"],
                    content["installation_token"],
                )
                self.assertNotIn("X-Airalogy-Gateway-Token", headers)
                self.assertNotIn("Auth-Token", headers)
            for target in [
                "http://lab.example",
                "https://user:password@lab.example",
                "https://lab.example/?token=secret",
            ]:
                with self.assertRaises(ValueError):
                    InstallationClient({**content, "platform_url": target})
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
