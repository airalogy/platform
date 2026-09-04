"""Minimal no-redirect HTTP client for the Instrument Gateway contract."""

from __future__ import annotations

import json
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
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
        self._opener = build_opener(
            _RejectRedirects(), HTTPSHandler(context=ssl.create_default_context())
        )

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
                raw = response.read()
        except HTTPError as error:
            raw = error.read()
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

    def fail(self, job_id: str, lease_token: str, error: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/instrument-gateway/v1/jobs/{job_id}/fail",
            lease_token=lease_token,
            payload={"error": error},
        )

    def stopped(self, job_id: str, lease_token: str, reason: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/instrument-gateway/v1/jobs/{job_id}/stopped",
            lease_token=lease_token,
            payload={"reason": reason},
        )
