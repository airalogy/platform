"""Fail-closed local configuration for an independently supervised Runner."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

IMAGE_DIGEST_RE = re.compile(
    r"^(?![^@]*://)[a-z0-9][a-z0-9._:/-]{0,1975}@sha256:[0-9a-f]{64}$"
)


def _as_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _network_map(raw: str) -> dict[str, str]:
    if not raw.strip():
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict) or not all(
        isinstance(key, str)
        and key.strip()
        and isinstance(network, str)
        and network.strip()
        for key, network in value.items()
    ):
        raise ValueError(
            "AIRALOGY_COMPUTE_EGRESS_NETWORKS_JSON must be a string-to-string object"
        )
    return {key.strip(): network.strip() for key, network in value.items()}


@dataclass(frozen=True)
class RunnerConfig:
    platform_url: str
    runner_token: str
    state_file: Path
    backend: str
    helper_image: str
    egress_networks: dict[str, str]
    poll_interval_seconds: float = 15.0
    heartbeat_interval_seconds: float = 20.0
    request_timeout_seconds: float = 15.0
    output_upload_timeout_seconds: float = 3600.0
    stop_timeout_seconds: float = 20.0
    max_workspace_bytes: int = 10 * 1024 * 1024 * 1024
    allow_insecure_http: bool = False

    def __post_init__(self) -> None:
        normalized_url = self.platform_url.rstrip("/")
        parsed = urlparse(normalized_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("AIRALOGY_PLATFORM_URL must be an absolute HTTP(S) URL")
        is_loopback = (parsed.hostname or "").lower() in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
        if parsed.scheme != "https" and not (is_loopback or self.allow_insecure_http):
            raise ValueError(
                "Compute Runner requires HTTPS outside loopback; set "
                "AIRALOGY_COMPUTE_ALLOW_INSECURE_HTTP only for an isolated test network"
            )
        if parsed.query or parsed.fragment:
            raise ValueError("AIRALOGY_PLATFORM_URL cannot contain a query or fragment")
        if not self.runner_token.startswith("aicr_") or len(self.runner_token) < 40:
            raise ValueError("AIRALOGY_COMPUTE_RUNNER_TOKEN is missing or invalid")
        if self.backend not in {"docker", "podman"}:
            raise ValueError("AIRALOGY_COMPUTE_BACKEND must be docker or podman")
        if not IMAGE_DIGEST_RE.fullmatch(self.helper_image):
            raise ValueError(
                "AIRALOGY_COMPUTE_HELPER_IMAGE must use an immutable sha256 digest"
            )
        if self.poll_interval_seconds <= 0:
            raise ValueError("Runner poll interval must be positive")
        if not 0 < self.heartbeat_interval_seconds <= 60:
            raise ValueError(
                "Runner heartbeat interval must be between 0 and 60 seconds"
            )
        if not 0 < self.request_timeout_seconds <= 120:
            raise ValueError("Runner request timeout must be between 0 and 120 seconds")
        if not 0 < self.output_upload_timeout_seconds <= 86_400:
            raise ValueError(
                "Runner output upload timeout must be between 0 and 86400 seconds"
            )
        if not 0 < self.stop_timeout_seconds <= 300:
            raise ValueError("Runner stop timeout must be between 0 and 300 seconds")
        if not 64 * 1024 * 1024 <= self.max_workspace_bytes <= 100 * 1024**3:
            raise ValueError(
                "Runner workspace limit must be between 64 MiB and 100 GiB"
            )
        object.__setattr__(self, "platform_url", normalized_url)
        object.__setattr__(self, "state_file", self.state_file.expanduser().resolve())

    @classmethod
    def from_env(cls) -> RunnerConfig:
        return cls(
            platform_url=os.environ.get("AIRALOGY_PLATFORM_URL", "").strip(),
            runner_token=os.environ.get("AIRALOGY_COMPUTE_RUNNER_TOKEN", "").strip(),
            state_file=Path(
                os.environ.get(
                    "AIRALOGY_COMPUTE_STATE_FILE",
                    ".airalogy-compute-runner-state.json",
                )
            ),
            backend=os.environ.get("AIRALOGY_COMPUTE_BACKEND", "docker")
            .strip()
            .lower(),
            helper_image=os.environ.get("AIRALOGY_COMPUTE_HELPER_IMAGE", "").strip(),
            egress_networks=_network_map(
                os.environ.get("AIRALOGY_COMPUTE_EGRESS_NETWORKS_JSON", "")
            ),
            poll_interval_seconds=float(
                os.environ.get("AIRALOGY_COMPUTE_POLL_SECONDS", "15")
            ),
            heartbeat_interval_seconds=float(
                os.environ.get("AIRALOGY_COMPUTE_HEARTBEAT_SECONDS", "20")
            ),
            request_timeout_seconds=float(
                os.environ.get("AIRALOGY_COMPUTE_REQUEST_TIMEOUT_SECONDS", "15")
            ),
            output_upload_timeout_seconds=float(
                os.environ.get("AIRALOGY_COMPUTE_OUTPUT_UPLOAD_TIMEOUT_SECONDS", "3600")
            ),
            stop_timeout_seconds=float(
                os.environ.get("AIRALOGY_COMPUTE_STOP_TIMEOUT_SECONDS", "20")
            ),
            max_workspace_bytes=int(
                os.environ.get(
                    "AIRALOGY_COMPUTE_MAX_WORKSPACE_BYTES",
                    str(10 * 1024 * 1024 * 1024),
                )
            ),
            allow_insecure_http=_as_bool(
                os.environ.get("AIRALOGY_COMPUTE_ALLOW_INSECURE_HTTP")
            ),
        )
