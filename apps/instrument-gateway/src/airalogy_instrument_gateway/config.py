"""Local configuration with fail-closed transport defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


def _as_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class GatewayConfig:
    platform_url: str
    gateway_token: str
    adapter_name: str
    adapter_config: Path | None
    state_file: Path
    poll_interval_seconds: float = 15.0
    heartbeat_interval_seconds: float = 30.0
    request_timeout_seconds: float = 10.0
    stop_timeout_seconds: float = 30.0
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
                "Instrument Gateway requires HTTPS outside loopback; "
                "set AIRALOGY_GATEWAY_ALLOW_INSECURE_HTTP only for an isolated test network"
            )
        if parsed.query or parsed.fragment:
            raise ValueError("AIRALOGY_PLATFORM_URL cannot contain a query or fragment")
        if not self.gateway_token.startswith("aigw_") or len(self.gateway_token) < 40:
            raise ValueError("AIRALOGY_GATEWAY_TOKEN is missing or invalid")
        if not self.adapter_name.strip():
            raise ValueError("AIRALOGY_GATEWAY_ADAPTER is required")
        if self.poll_interval_seconds <= 0:
            raise ValueError("Gateway poll interval must be positive")
        if not 0 < self.heartbeat_interval_seconds <= 60:
            raise ValueError(
                "Gateway heartbeat interval must be between 0 and 60 seconds"
            )
        if not 0 < self.request_timeout_seconds <= 60:
            raise ValueError("Gateway request timeout must be between 0 and 60 seconds")
        if not 0 < self.stop_timeout_seconds <= 300:
            raise ValueError("Gateway stop timeout must be between 0 and 300 seconds")
        object.__setattr__(self, "platform_url", normalized_url)
        object.__setattr__(self, "adapter_name", self.adapter_name.strip())
        object.__setattr__(self, "state_file", self.state_file.expanduser().resolve())
        if self.adapter_config is not None:
            object.__setattr__(
                self, "adapter_config", self.adapter_config.expanduser().resolve()
            )

    @classmethod
    def from_env(cls) -> GatewayConfig:
        adapter_config = os.environ.get("AIRALOGY_GATEWAY_ADAPTER_CONFIG", "").strip()
        return cls(
            platform_url=os.environ.get("AIRALOGY_PLATFORM_URL", "").strip(),
            gateway_token=os.environ.get("AIRALOGY_GATEWAY_TOKEN", "").strip(),
            adapter_name=os.environ.get("AIRALOGY_GATEWAY_ADAPTER", "").strip(),
            adapter_config=Path(adapter_config) if adapter_config else None,
            state_file=Path(
                os.environ.get(
                    "AIRALOGY_GATEWAY_STATE_FILE",
                    ".airalogy-instrument-gateway-state.json",
                )
            ),
            poll_interval_seconds=float(
                os.environ.get("AIRALOGY_GATEWAY_POLL_SECONDS", "15")
            ),
            heartbeat_interval_seconds=float(
                os.environ.get("AIRALOGY_GATEWAY_HEARTBEAT_SECONDS", "30")
            ),
            request_timeout_seconds=float(
                os.environ.get("AIRALOGY_GATEWAY_REQUEST_TIMEOUT_SECONDS", "10")
            ),
            stop_timeout_seconds=float(
                os.environ.get("AIRALOGY_GATEWAY_STOP_TIMEOUT_SECONDS", "30")
            ),
            allow_insecure_http=_as_bool(
                os.environ.get("AIRALOGY_GATEWAY_ALLOW_INSECURE_HTTP")
            ),
        )
