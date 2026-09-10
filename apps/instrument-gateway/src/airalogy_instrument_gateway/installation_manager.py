"""Installation-only credentials, exact package delivery and replayable receipts.

Never imports adapter code, reads runtime credentials or activates an adapter.
The complete local transaction holds the same journal lock as the Gateway.
"""

import hashlib
import json
import re
import secrets
import ssl
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener
from uuid import UUID, uuid4

from .client import GatewayAPIError, _RejectRedirects
from .config import validate_platform_url
from .credentials import read_private_json, write_credentials
from .installation_contract import (
    descriptor_from_preview,
    receipt_summary,
    request_fingerprint,
    validate_request,
)
from .package_cli import read_selected
from .package_contract import MAX_ARCHIVE_BYTES, strict_json
from .package_installation import _install_inactive_locked, installation_preview
from .state import StateStore


def _inputs(content):
    return {
        "sdk_wheel": read_selected(Path(content["sdk_wheel"])),
        "trusted_sdk_digest": content["trusted_sdk_digest"],
        "config": strict_json(read_selected(Path(content["config"]), limit=16384)),
        "root": Path(content["root"]),
    }


def prepare(
    *,
    destination,
    platform_url,
    lab_id,
    gateway_id,
    package,
    sdk_wheel,
    trusted_sdk_digest,
    config,
    root,
    expected_preview_digest=None,
):
    # No network, driver imports or credential-file lookup during preparation.
    content = {
        "schema": "airalogy.private-installation.v1",
        "platform_url": validate_platform_url(platform_url),
        "package": str(Path(package).absolute()),
        "sdk_wheel": str(Path(sdk_wheel).absolute()),
        "trusted_sdk_digest": trusted_sdk_digest,
        "config": str(Path(config).absolute()),
        "root": str(Path(root).absolute()),
        "installation_token": "aiinstall_" + secrets.token_urlsafe(32),
    }
    preview = installation_preview(read_selected(Path(package)), **_inputs(content))
    if (
        expected_preview_digest is not None
        and preview["preview_digest"] != expected_preview_digest
    ):
        raise ValueError("Installation inputs changed after preview; review them again")
    request = {
        "schema": "airalogy.installation-request.v1",
        "id": str(uuid4()),
        "lab_id": str(UUID(lab_id)),
        "gateway_id": str(UUID(gateway_id)),
        "credential_digest": hashlib.sha256(
            content["installation_token"].encode()
        ).hexdigest(),
        "descriptor": descriptor_from_preview(preview),
    }
    request["fingerprint"] = request_fingerprint(request)
    content["request"] = validate_request(request)
    write_credentials(Path(destination), content)
    return request


def read_request(path):
    content = read_private_json(Path(path))
    if content.get("schema") != "airalogy.private-installation.v1":
        raise ValueError(
            "Use an installation request, not a Gateway runtime credential"
        )
    request = validate_request(content["request"])
    token = content.get("installation_token", "")
    if not re.fullmatch(r"aiinstall_[A-Za-z0-9_-]{43}", token) or (
        hashlib.sha256(token.encode()).hexdigest() != request["credential_digest"]
    ):
        raise ValueError("Installation credential does not match its public request")
    validate_platform_url(content["platform_url"])
    return content


class InstallationClient:
    def __init__(self, content):
        self.url = validate_platform_url(content["platform_url"])
        self.token = content["installation_token"]
        self.id = str(UUID(content["request"]["id"]))
        handlers = [
            _RejectRedirects(),
            HTTPSHandler(context=ssl.create_default_context()),
        ]
        if urlparse(self.url).hostname in {"localhost", "127.0.0.1", "::1"}:
            # Local API credentials must never be forwarded to an environment proxy.
            handlers.append(ProxyHandler({}))
        self.opener = build_opener(*handlers)

    def call(self, operation, payload=None):
        if operation not in {"status", "claim", "package", "receipt"}:
            raise ValueError("Unsupported installation operation")
        request = Request(
            f"{self.url}/instrument-installations/{self.id}/{operation}",
            data=json.dumps(payload or {}).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Airalogy-Installation-Token": self.token,
            },
        )
        limit = MAX_ARCHIVE_BYTES if operation == "package" else 65536
        deadline = time.monotonic() + 60
        raw = bytearray()
        try:
            with self.opener.open(request, timeout=10) as response:
                while True:
                    chunk = response.read1(min(65536, limit + 1 - len(raw)))
                    raw.extend(chunk)
                    if len(raw) > limit or time.monotonic() > deadline:
                        raise GatewayAPIError(
                            "Installation response exceeded its limit"
                        )
                    if not chunk:
                        break
        except HTTPError as error:
            # Never print arbitrary remote bodies or credential-bearing requests.
            error.close()
            raise GatewayAPIError(
                f"Installation request rejected (HTTP {error.code}); refresh its Platform status",
                status=error.code,
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise GatewayAPIError(
                "Installation connection failed; preserve the local request and retry"
            ) from error
        if operation == "package":
            return bytes(raw)
        result = strict_json(bytes(raw))
        if not isinstance(result, dict):
            raise GatewayAPIError("Installation response must be an object")
        return result


def apply(path, *, source_reviewed=False, client=None):
    if source_reviewed is not True:
        raise ValueError("Explicit local source/dependency review is required")
    content = read_request(path)
    client = client or InstallationClient(content)
    inputs = _inputs(content)
    raw = read_selected(Path(content["package"]))
    preview = installation_preview(raw, **inputs)
    descriptor = descriptor_from_preview(preview)
    if descriptor != content["request"]["descriptor"]:
        raise ValueError(
            "Local package, configuration or environment changed; prepare a new request"
        )
    with StateStore(inputs["root"] / "state.json").exclusive():
        StateStore(inputs["root"] / "state.json").assert_installable()
        status = client.call("status")
        if (
            status.get("descriptor") != descriptor
            or status.get("installer_fingerprint") != content["request"]["fingerprint"]
        ):
            raise ValueError("Platform authorization differs from the local request")
        if status.get("state") not in {"authorized", "installing", "installed"}:
            raise ValueError("Installation authorization is not current")
        exists = (inputs["root"] / descriptor["installation_id"]).exists()
        if not exists:
            if status["state"] == "installed":
                raise ValueError(
                    "Platform receipt exists but the local installation is missing; reconcile manually"
                )
            client.call("claim")
            delivered = client.call("package")
            if hashlib.sha256(delivered).hexdigest() != descriptor["archive_digest"]:
                raise ValueError("Downloaded archive differs from the approved package")
            raw = delivered
        elif status["state"] == "authorized":
            # A pre-existing offline copy still needs this independent grant.
            client.call("claim")
        # The atomic local receipt is durable before any receipt request. On a
        # lost response, verify against original wheel bytes and resend only it.
        receipt = _install_inactive_locked(
            raw, **inputs, preview_digest=preview["preview_digest"]
        )
        result = client.call("receipt", {"receipt": receipt_summary(receipt)})
        if result.get("state") != "installed" or result.get(
            "receipt"
        ) != receipt_summary(receipt):
            raise GatewayAPIError(
                "Installation receipt is not confirmed; retain the local request for reconciliation"
            )
        return {
            "id": content["request"]["id"],
            "state": "installed",
            "installation_id": descriptor["installation_id"],
            "activation_performed": False,
            "hardware_authorized": False,
        }
