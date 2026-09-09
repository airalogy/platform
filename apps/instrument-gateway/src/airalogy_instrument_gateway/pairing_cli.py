"""Interactive enrollment only: does not load adapters, poll jobs or touch hardware."""

import argparse
import getpass
import hashlib
import json
import secrets
import sys
from pathlib import Path
from uuid import UUID

from .client import GatewayAPIError, PlatformClient
from .config import GatewayConfig
from .credentials import read_credentials, write_credentials


def _client(content):
    # Apply runtime transport policy but do not permit the test-network HTTP override.
    config = GatewayConfig(
        platform_url=content["platform_url"],
        gateway_token=content["gateway_token"],
        adapter_name="pairing-only",
        adapter_config=None,
        state_file=Path("unused"),
    )
    return PlatformClient(config.platform_url, config.gateway_token)


def claim(content, code, *, client=None):
    client = client or _client(content)
    result = client.claim_pairing(
        {
            "code": code,
            "lab_id": content["lab_id"],
            "gateway_id": content["gateway_id"],
            "client_name": content["client_name"],
            "credential_digest": hashlib.sha256(
                content["gateway_token"].encode()
            ).hexdigest(),
            "credential_hint": content["gateway_token"][-8:],
        }
    )
    if (
        result["gateway_id"] != content["gateway_id"]
        or result["lab_id"] != content["lab_id"]
    ):
        raise ValueError("Platform returned a different Gateway/Lab; do not approve")
    identity = {
        "pairing_id": result["id"],
        "gateway_id": content["gateway_id"],
        "client_name": content["client_name"],
        "credential_digest": hashlib.sha256(
            content["gateway_token"].encode()
        ).hexdigest(),
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    if result["fingerprint"] != fingerprint:
        raise ValueError("Pairing fingerprint mismatch; do not approve")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--platform-url")
    parser.add_argument("--lab-id", type=UUID)
    parser.add_argument("--gateway-id", type=UUID)
    parser.add_argument("--client-name")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Retry the same claim using the already saved local identity",
    )
    parser.add_argument(
        "--status", type=UUID, help="Read a pairing status; does not enable the Gateway"
    )
    args = parser.parse_args(argv)
    try:
        if args.resume or args.status:
            content = read_credentials(args.credential_file)
        else:
            if not all(
                [args.platform_url, args.lab_id, args.gateway_id, args.client_name]
            ):
                parser.error(
                    "New enrollment requires platform URL, Lab ID, Gateway ID and client name"
                )
            content = {
                "schema": "airalogy.gateway-credential.v1",
                "platform_url": args.platform_url.rstrip("/"),
                "lab_id": str(args.lab_id),
                "gateway_id": str(args.gateway_id),
                "client_name": args.client_name,
                "gateway_token": "aigw_" + secrets.token_urlsafe(32),
            }
            _client(content)  # Validate destination before creating any secret.
            write_credentials(args.credential_file, content)
        client = _client(content)
        if args.status:
            result = client.pairing_status(str(args.status))
        else:
            print(
                f"Platform: {content['platform_url']}\nLab: {content['lab_id']}\nGateway: {content['gateway_id']}"
            )
            if not sys.stdin.isatty():
                raise ValueError(
                    "Pairing requires an interactive terminal; never pass the pairing code in command arguments"
                )
            code = getpass.getpass("Paste the short-lived pairing code: ").strip()
            result = claim(content, code, client=client)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        print(
            "Compare the full fingerprint with Platform before approval. No adapter or hardware was started."
        )
        return 0
    except (OSError, ValueError, KeyError, GatewayAPIError) as error:
        print(
            f"Pairing did not complete: {error}. Keep any saved credential file; use --resume after a network failure.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
