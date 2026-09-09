"""Minimal no-redirect HTTP client for the Instrument Gateway contract."""

from __future__ import annotations

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
    ):
        self.platform_url = f"{platform_url.rstrip('/')}/"
        self.gateway_token = gateway_token
        self.timeout_seconds = timeout_seconds
        handlers = [_RejectRedirects(), HTTPSHandler(context=ssl.create_default_context())]
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
        return self._request("POST", "/instrument-gateway/v1/jobs/lease")

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
