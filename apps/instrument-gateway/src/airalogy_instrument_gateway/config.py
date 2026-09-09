"""Local configuration with fail-closed transport defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .credentials import read_credentials


def _as_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def validate_platform_url(value: str, *, allow_insecure_http=False) -> str:
    normalized = value.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Platform requires an absolute HTTP(S) URL")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("Platform URL cannot contain credentials, a query or fragment")
    if parsed.scheme != "https" and not (
        (parsed.hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}
        or allow_insecure_http
    ):
        raise ValueError("Platform requires HTTPS outside loopback")
    return normalized


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
    output_root: Path | None = None

    def __post_init__(self) -> None:
        normalized_url = validate_platform_url(
            self.platform_url, allow_insecure_http=self.allow_insecure_http
        )
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
        if self.output_root is not None:
            root = Path(self.output_root)
            if not root.is_absolute() or ".." in root.parts or str(root) == "/":
                raise ValueError("Select an absolute non-root output directory")
            # Do not resolve aliases or require the original to survive delivery recovery.
            object.__setattr__(self, "output_root", root)

    @classmethod
    def from_env(cls) -> GatewayConfig:
        adapter_config = os.environ.get("AIRALOGY_GATEWAY_ADAPTER_CONFIG", "").strip()
        output_root = os.environ.get("AIRALOGY_GATEWAY_OUTPUT_ROOT", "").strip()
        credential_file = os.environ.get("AIRALOGY_GATEWAY_CREDENTIAL_FILE", "").strip()
        platform_url = os.environ.get("AIRALOGY_PLATFORM_URL", "").strip()
        token = os.environ.get("AIRALOGY_GATEWAY_TOKEN", "").strip()
        if credential_file:
            if token:
                raise ValueError("Use either a credential file or a token, not both")
            content = read_credentials(Path(credential_file))
            if platform_url and platform_url.rstrip("/") != content[
                "platform_url"
            ].rstrip("/"):
                raise ValueError("Platform URL does not match the paired destination")
            platform_url = content["platform_url"]
            token = content["gateway_token"]
        return cls(
            platform_url=platform_url,
            gateway_token=token,
            adapter_name=os.environ.get("AIRALOGY_GATEWAY_ADAPTER", "").strip(),
            adapter_config=Path(adapter_config) if adapter_config else None,
            output_root=Path(output_root) if output_root else None,
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
