"""Local-only adapter interface and deterministic development adapter."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from importlib.metadata import entry_points
from pathlib import Path
from threading import Event
from typing import Any

from .models import InstrumentJobEnvelope


class InstrumentAdapter(ABC):
    """A locally installed allowlist. Implementations must make safe_stop idempotent."""

    @abstractmethod
    def supports(self, job: InstrumentJobEnvelope) -> bool:
        """Return true only for an exact, locally authorized command version."""

    @abstractmethod
    def confirm(self, job: InstrumentJobEnvelope) -> str | None:
        """Return a device-local confirmation reference, or None when unavailable."""

    def preflight(self, job: InstrumentJobEnvelope) -> dict[str, Any]:
        """Read local interlocks immediately before start.

        Existing adapters remain compatible for commands without a safety contract.
        Hardware adapters should return current interlock booleans, operator presence,
        emergency-stop availability, and a local audit reference.
        """

        return {}

    @abstractmethod
    def execute(self, job: InstrumentJobEnvelope, stop_event: Event) -> dict[str, Any]:
        """Execute one command and return a JSON object result."""

    @abstractmethod
    def safe_stop(self, job: InstrumentJobEnvelope, reason: str) -> None:
        """Confirm the device reached its hardware-specific safe state."""


class MockAdapter(InstrumentAdapter):
    """Deterministic adapter for local integration tests; never controls hardware."""

    def __init__(self, commands: list[dict[str, Any]]):
        self._commands: dict[tuple[str, str], dict[str, Any]] = {}
        self.stop_requests: list[tuple[str, str]] = []
        for item in commands:
            key = item.get("key")
            version = item.get("version")
            result = item.get("result")
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Mock command key is required")
            if not isinstance(version, str) or not version.strip():
                raise ValueError("Mock command version is required")
            if not isinstance(result, dict):
                raise TypeError("Mock command result must be an object")
            safety_attestation = item.get("safety_attestation") or {}
            if not isinstance(safety_attestation, dict):
                raise TypeError("Mock command safety_attestation must be an object")
            delay = item.get("delay_seconds", 0)
            if (
                isinstance(delay, bool)
                or not isinstance(delay, (int, float))
                or delay < 0
            ):
                raise ValueError("Mock command delay_seconds must be non-negative")
            identity = (key.strip(), version.strip())
            if identity in self._commands:
                raise ValueError(f"Duplicate mock command {identity[0]}@{identity[1]}")
            self._commands[identity] = {
                "result": result,
                "delay_seconds": float(delay),
                "confirmation_reference": str(
                    item.get("confirmation_reference") or ""
                ).strip(),
                "safety_attestation": safety_attestation,
            }

    @classmethod
    def from_file(cls, path: Path) -> MockAdapter:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("commands"), list):
            raise TypeError("Mock adapter config must contain a commands array")
        return cls(value["commands"])

    def _command(self, job: InstrumentJobEnvelope) -> dict[str, Any] | None:
        return self._commands.get((job.command_key, job.command_version))

    def supports(self, job: InstrumentJobEnvelope) -> bool:
        return self._command(job) is not None

    def confirm(self, job: InstrumentJobEnvelope) -> str | None:
        command = self._command(job)
        if command is None:
            return None
        return command["confirmation_reference"] or None

    def preflight(self, job: InstrumentJobEnvelope) -> dict[str, Any]:
        command = self._command(job)
        if command is None:
            return {}
        return dict(command["safety_attestation"])

    def execute(self, job: InstrumentJobEnvelope, stop_event: Event) -> dict[str, Any]:
        command = self._command(job)
        if command is None:
            raise RuntimeError("Mock command is not locally authorized")
        deadline = time.monotonic() + command["delay_seconds"]
        while time.monotonic() < deadline:
            if stop_event.wait(min(0.05, max(0.0, deadline - time.monotonic()))):
                raise RuntimeError("Mock command stopped")
        if stop_event.is_set():
            raise RuntimeError("Mock command stopped")
        return dict(command["result"])

    def safe_stop(self, job: InstrumentJobEnvelope, reason: str) -> None:
        self.stop_requests.append((job.job_id, reason))


def mock_adapter_factory(config_path: Path | None) -> InstrumentAdapter:
    if config_path is None:
        raise ValueError("The mock adapter requires AIRALOGY_GATEWAY_ADAPTER_CONFIG")
    return MockAdapter.from_file(config_path)


def load_adapter(name: str, config_path: Path | None) -> InstrumentAdapter:
    """Load only an explicitly installed entry point selected by the local operator."""

    matches = list(entry_points(group="airalogy.instrument_adapters", name=name))
    if len(matches) != 1:
        raise ValueError(
            f"Expected one locally installed airalogy.instrument_adapters entry point named {name!r}"
        )
    factory: Callable[[Path | None], InstrumentAdapter] = matches[0].load()
    adapter = factory(config_path)
    if not isinstance(adapter, InstrumentAdapter):
        raise TypeError(
            f"Instrument adapter {name!r} returned an invalid implementation"
        )
    return adapter
