import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from airalogy_instrument_gateway.config import GatewayConfig
from airalogy_instrument_gateway.credentials import read_credentials, write_credentials
from airalogy_instrument_gateway.pairing_cli import claim


def content():
    return {
        "schema": "airalogy.gateway-credential.v1",
        "platform_url": "https://lab.example.edu/api",
        "gateway_id": str(uuid4()),
        "lab_id": str(uuid4()),
        "gateway_token": "aigw_" + "x" * 43,
        "client_name": "Synthetic local install",
    }


class PairingTests(unittest.TestCase):
    def test_private_exclusive_storage_and_transport_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credential.json"
            data = content()
            write_credentials(path, data)
            self.assertEqual(read_credentials(path), data)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                write_credentials(path, content())
            with patch.dict(
                os.environ,
                {
                    "AIRALOGY_GATEWAY_CREDENTIAL_FILE": str(path),
                    "AIRALOGY_GATEWAY_ADAPTER": "mock",
                },
                clear=True,
            ):
                config = GatewayConfig.from_env()
                self.assertEqual(config.gateway_token, data["gateway_token"])
                os.environ["AIRALOGY_PLATFORM_URL"] = "https://other.example.edu"
                with self.assertRaisesRegex(ValueError, "destination"):
                    GatewayConfig.from_env()
                os.environ["AIRALOGY_GATEWAY_TOKEN"] = data["gateway_token"]
                with self.assertRaisesRegex(ValueError, "not both"):
                    GatewayConfig.from_env()

    def test_rejects_shared_files_links_and_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "credential.json"
            write_credentials(path, content())
            link = root / "link"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                read_credentials(link)
            hard = root / "hard"
            os.link(path, hard)
            with self.assertRaises(ValueError):
                read_credentials(hard)
            hard.unlink()
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                read_credentials(path)
            root.chmod(0o755)
            with self.assertRaises(ValueError):
                write_credentials(root / "other", content())
            root.chmod(0o700)

    def test_claim_compares_independent_identity_without_sending_token(self):
        data = content()

        class Client:
            tamper = False

            def claim_pairing(self, payload):
                assert "gateway_token" not in payload
                identity = {
                    "pairing_id": str(uuid4()),
                    "gateway_id": payload["gateway_id"],
                    "client_name": payload["client_name"],
                    "credential_digest": payload["credential_digest"],
                }
                fingerprint = hashlib.sha256(
                    json.dumps(
                        identity,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                return {
                    "id": identity["pairing_id"],
                    "gateway_id": payload["gateway_id"],
                    "lab_id": payload["lab_id"],
                    "fingerprint": "0" * 64 if self.tamper else fingerprint,
                }

        client = Client()
        self.assertEqual(
            claim(data, "synthetic-code", client=client)["lab_id"], data["lab_id"]
        )
        client.tamper = True
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            claim(data, "synthetic-code", client=client)


if __name__ == "__main__":
    unittest.main()
