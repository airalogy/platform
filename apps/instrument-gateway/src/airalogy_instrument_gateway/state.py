"""Crash-recovery journal for the single active local Instrument Job."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GatewayState:
    phase: str
    envelope: dict[str, Any]
    signature: str
    lease_token: str
    result: dict[str, Any] | None = None
    error: str | None = None
    stop_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> GatewayState:
        phase = value.get("phase")
        envelope = value.get("envelope")
        signature = value.get("signature")
        lease_token = value.get("lease_token")
        if not isinstance(phase, str) or not phase:
            raise ValueError("Gateway state phase is invalid")
        if not isinstance(envelope, dict):
            raise TypeError("Gateway state envelope is invalid")
        if not isinstance(signature, str) or not signature:
            raise ValueError("Gateway state signature is invalid")
        if not isinstance(lease_token, str) or not lease_token.startswith("aijl_"):
            raise ValueError("Gateway state lease token is invalid")
        result = value.get("result")
        metadata = value.get("metadata") or {}
        if result is not None and not isinstance(result, dict):
            raise TypeError("Gateway state result is invalid")
        if not isinstance(metadata, dict):
            raise TypeError("Gateway state metadata is invalid")
        return cls(
            phase=phase,
            envelope=envelope,
            signature=signature,
            lease_token=lease_token,
            result=result,
            error=value.get("error") if isinstance(value.get("error"), str) else None,
            stop_reason=(
                value.get("stop_reason")
                if isinstance(value.get("stop_reason"), str)
                else None
            ),
            metadata=metadata,
        )


class StateStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> GatewayState | None:
        if not self.path.exists():
            return None
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError("Gateway state file must contain an object")
        return GatewayState.from_dict(value)

    def save(self, state: GatewayState) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    asdict(state),
                    handle,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
            os.chmod(self.path, 0o600)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
