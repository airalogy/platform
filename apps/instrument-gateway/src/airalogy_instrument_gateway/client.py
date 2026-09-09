"""Minimal no-redirect HTTP client for the Instrument Gateway contract."""

from __future__ import annotations

import hashlib
import json
import ssl
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)
from uuid import UUID

from .output_contract import MAX_FILE_BYTES, MEDIA_TYPE, PLAN_SCHEMA, SHA256


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("A canonical output/job UUID is required")
    return value


def _file_body(stream, size, checksum):
    """Fixed-size streaming upload; never follow a server-selected source URL."""
    deadline = time.monotonic() + 900
    remaining = size
    hasher = hashlib.sha256()
    while remaining:
        chunk = stream.read(min(65536, remaining))
        if not isinstance(chunk, bytes) or not chunk or len(chunk) > remaining:
            raise ValueError("Captured upload length changed")
        if time.monotonic() > deadline:
            raise GatewayAPIError("Instrument upload exceeded its time limit")
        hasher.update(chunk)
        remaining -= len(chunk)
        yield chunk
    if stream.read(1) or hasher.hexdigest() != checksum:
        raise ValueError("Captured upload content changed")


class GatewayAPIError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PlatformClient:
    def __init__(
        self,
        platform_url: str,
        gateway_token: str,
        *,
        timeout_seconds: float = 10.0,
        file_delivery_enabled: bool = False,
    ):
        self.platform_url = f"{platform_url.rstrip('/')}/"
        self.gateway_token = gateway_token
        self.timeout_seconds = timeout_seconds
        self.file_delivery_enabled = file_delivery_enabled
        handlers = [
            _RejectRedirects(),
            HTTPSHandler(context=ssl.create_default_context()),
        ]
        if urlparse(self.platform_url).hostname in {"localhost", "127.0.0.1", "::1"}:
            handlers.append(ProxyHandler({}))
        self._opener = build_opener(*handlers)

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        lease_token: str | None = None,
        binary: tuple | None = None,
    ) -> dict[str, Any]:
        url = urljoin(self.platform_url, path.lstrip("/"))
        body = None
        headers = {
            "Accept": "application/json",
            "X-Airalogy-Gateway-Token": self.gateway_token,
        }
        if lease_token is not None:
            headers["X-Airalogy-Instrument-Lease"] = lease_token
        if payload is not None:
            body = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if binary is not None:
            if payload is not None or method != "PUT":
                raise ValueError(
                    "Binary upload cannot include JSON or use another method"
                )
            stream, size, media_type, checksum = binary
            if (
                type(size) is not int
                or not 0 <= size <= MAX_FILE_BYTES
                or not isinstance(media_type, str)
                or not MEDIA_TYPE.fullmatch(media_type)
                or not isinstance(checksum, str)
                or not SHA256.fullmatch(checksum)
            ):
                raise ValueError("Invalid instrument upload metadata")
            headers.update(
                {
                    "Content-Length": str(size),
                    "Content-Type": media_type,
                    "X-Airalogy-Content-SHA256": checksum,
                }
            )
            body = _file_body(stream, size, checksum)
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                raw = bytearray()
                deadline = time.monotonic() + 60
                limit = 4 * 1024 * 1024
                while True:
                    chunk = response.read1(min(65536, limit + 1 - len(raw)))
                    raw.extend(chunk)
                    if len(raw) > limit or time.monotonic() > deadline:
                        raise GatewayAPIError("Platform response exceeded its limit")
                    if not chunk:
                        break
        except HTTPError as error:
            raw = error.read(8192)
            error.close()
            try:
                detail = json.loads(raw.decode("utf-8")).get("detail")
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                detail = None
            raise GatewayAPIError(
                str(detail or f"Platform returned HTTP {error.code}"),
                status=error.code,
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise GatewayAPIError(f"Platform connection failed: {error}") from error
        if not raw:
            return {}
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GatewayAPIError("Platform returned invalid JSON") from error
        if not isinstance(value, dict):
            raise GatewayAPIError("Platform response must be a JSON object")
        return value

    def lease(self) -> dict[str, Any]:
        return self._request(
            "POST",
            "/instrument-gateway/v1/jobs/lease",
            payload=self.lease_capabilities() or None,
        )

    def lease_capabilities(self):
        return (
            {"file_delivery_version": PLAN_SCHEMA} if self.file_delivery_enabled else {}
        )

    def report_capture(self, job_id, lease_token, capture):
        return self._request(
            "POST",
            f"/instrument-gateway/v1/jobs/{_uuid(job_id)}/outputs/capture",
            lease_token=lease_token,
            payload={"capture": capture},
        )

    def upload_output(self, job_id, lease_token, output_id, receipt, stream):
        return self._request(
            "PUT",
            f"/instrument-gateway/v1/jobs/{_uuid(job_id)}/outputs/{_uuid(output_id)}",
            lease_token=lease_token,
            binary=(
                stream,
                receipt["byte_size"],
                receipt["media_type"],
                receipt["sha256"],
            ),
        )

    def finalize_outputs(self, job_id, lease_token, capture):
        return self._request(
            "POST",
            f"/instrument-gateway/v1/jobs/{_uuid(job_id)}/outputs/finalize",
            lease_token=lease_token,
            payload={"capture": capture},
        )

    def claim_pairing(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/instrument-pairings/claim", payload=payload)

    def pairing_status(self, pairing_id: str) -> dict[str, Any]:
        return self._request("POST", f"/instrument-pairings/{pairing_id}/status")

    def start(
        self,
        job_id: str,
        lease_token: str,
        *,
        device_confirmed: bool,
        confirmation_reference: str,
        safety_attestation: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/instrument-gateway/v1/jobs/{job_id}/start",
            lease_token=lease_token,
            payload={
                "device_confirmed": device_confirmed,
                "confirmation_reference": confirmation_reference,
                "safety_attestation": safety_attestation,
            },
        )

    def heartbeat(self, job_id: str, lease_token: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/instrument-gateway/v1/jobs/{job_id}/heartbeat",
            lease_token=lease_token,
        )

    def complete(
        self, job_id: str, lease_token: str, result: dict[str, Any]
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/instrument-gateway/v1/jobs/{job_id}/complete",
            lease_token=lease_token,
            payload={"result": result},
        )

    def fail(
        self,
        job_id: str,
        lease_token: str,
        error: str,
        *,
        safe_stop_confirmed: bool = False,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/instrument-gateway/v1/jobs/{job_id}/fail",
            lease_token=lease_token,
            payload={"error": error, "safe_stop_confirmed": safe_stop_confirmed},
        )

    def stopped(self, job_id: str, lease_token: str, reason: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/instrument-gateway/v1/jobs/{job_id}/stopped",
            lease_token=lease_token,
            payload={"reason": reason},
        )
