"""No-redirect HTTP client for the Compute Runner runtime contract."""

from __future__ import annotations

import json
import ssl
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
)


class RunnerAPIError(RuntimeError):
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
        runner_token: str,
        *,
        timeout_seconds: float = 15.0,
    ):
        self.platform_url = f"{platform_url.rstrip('/')}/"
        self.runner_token = runner_token
        self.timeout_seconds = timeout_seconds
        self._opener = build_opener(
            _RejectRedirects(), HTTPSHandler(context=ssl.create_default_context())
        )

    def _url(self, path: str) -> str:
        if not path.startswith("/") or "://" in path:
            raise RunnerAPIError("Platform runtime path is unsafe")
        return urljoin(self.platform_url, path.lstrip("/"))

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        lease_token: str | None = None,
    ) -> dict[str, Any]:
        body = None
        headers = {
            "Accept": "application/json",
            "X-Airalogy-Compute-Runner-Token": self.runner_token,
        }
        if lease_token is not None:
            headers["X-Airalogy-Compute-Lease"] = lease_token
        if payload is not None:
            body = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self._url(path), data=body, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as error:
            raw = error.read()
            try:
                detail = json.loads(raw.decode("utf-8")).get("detail")
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                detail = None
            raise RunnerAPIError(
                str(detail or f"Platform returned HTTP {error.code}"),
                status=error.code,
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise RunnerAPIError(f"Platform connection failed: {error}") from error
        if not raw:
            return {}
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RunnerAPIError("Platform returned invalid JSON") from error
        if not isinstance(value, dict):
            raise RunnerAPIError("Platform response must be a JSON object")
        return value

    def report_status(self, backend: str, *, active: bool) -> dict[str, Any]:
        return self._request(
            "POST",
            "/compute-runner/v1/status",
            payload={
                "protocol_version": "airalogy.compute-runner.v1",
                "runner_version": "0.1.0",
                "executor_backend": backend,
                "active_jobs": 1 if active else 0,
                "available_slots": 0 if active else 1,
                "security": {
                    "non_root": True,
                    "read_only_root_filesystem": True,
                    "network_isolation": True,
                    "no_host_mounts": True,
                },
            },
        )

    def lease(self) -> dict[str, Any]:
        return self._request("POST", "/compute-runner/v1/jobs/lease")

    def download_input(
        self,
        path: str,
        lease_token: str,
        destination: Path,
        *,
        expected_size: int,
    ) -> None:
        request = Request(
            self._url(path),
            headers={
                "Accept": "application/octet-stream",
                "X-Airalogy-Compute-Runner-Token": self.runner_token,
                "X-Airalogy-Compute-Lease": lease_token,
            },
            method="GET",
        )
        received = 0
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                declared = response.headers.get("Content-Length")
                if declared is not None and int(declared) != expected_size:
                    raise RunnerAPIError("Compute input size changed before download")
                with destination.open("xb") as handle:
                    while True:
                        chunk = response.read(min(1024 * 1024, expected_size + 1))
                        if not chunk:
                            break
                        received += len(chunk)
                        if received > expected_size:
                            raise RunnerAPIError(
                                "Compute input exceeded its declared size"
                            )
                        handle.write(chunk)
        except HTTPError as error:
            raise RunnerAPIError(
                f"Platform rejected Compute input download with HTTP {error.code}",
                status=error.code,
            ) from error
        except (URLError, TimeoutError, OSError, ValueError) as error:
            raise RunnerAPIError(f"Compute input download failed: {error}") from error
        if received != expected_size:
            raise RunnerAPIError("Compute input size does not match its contract")

    def start(self, job_id: str, lease_token: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/compute-runner/v1/jobs/{job_id}/start",
            lease_token=lease_token,
        )

    def heartbeat(self, job_id: str, lease_token: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/compute-runner/v1/jobs/{job_id}/heartbeat",
            lease_token=lease_token,
        )

    def complete(
        self,
        job_id: str,
        lease_token: str,
        result: dict[str, Any],
        usage: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/compute-runner/v1/jobs/{job_id}/complete",
            lease_token=lease_token,
            payload={"result": result, "usage": usage},
        )

    def fail(
        self,
        job_id: str,
        lease_token: str,
        error: str,
        usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": error}
        if usage is not None:
            payload["usage"] = usage
        return self._request(
            "POST",
            f"/compute-runner/v1/jobs/{job_id}/fail",
            lease_token=lease_token,
            payload=payload,
        )

    def cancelled(
        self,
        job_id: str,
        lease_token: str,
        reason: str,
        usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"reason": reason}
        if usage is not None:
            payload["usage"] = usage
        return self._request(
            "POST",
            f"/compute-runner/v1/jobs/{job_id}/cancelled",
            lease_token=lease_token,
            payload=payload,
        )
