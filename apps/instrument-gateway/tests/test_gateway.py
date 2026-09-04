from __future__ import annotations

import stat
import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from airalogy_instrument_gateway.adapters import InstrumentAdapter, MockAdapter
from airalogy_instrument_gateway.client import GatewayAPIError
from airalogy_instrument_gateway.config import GatewayConfig
from airalogy_instrument_gateway.models import InstrumentJobEnvelope
from airalogy_instrument_gateway.runtime import GatewayRuntime
from airalogy_instrument_gateway.security import (
    expected_job_signature,
    verify_job_signature,
)
from airalogy_instrument_gateway.state import GatewayState, StateStore

TOKEN = f"aigw_{'a' * 48}"


def envelope(
    *,
    confirmation_required: bool = False,
    safety_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "schema": "airalogy.instrument-job.v1",
        "job_id": "00000000-0000-0000-0000-000000000001",
        "action_id": "00000000-0000-0000-0000-000000000002",
        "task_id": "00000000-0000-0000-0000-000000000003",
        "run_id": "00000000-0000-0000-0000-000000000004",
        "issued_at": now.isoformat(),
        "lease_expires_at": (now + timedelta(minutes=2)).isoformat(),
        "resource": {
            "id": "00000000-0000-0000-0000-000000000005",
            "revision_id": "00000000-0000-0000-0000-000000000006",
            "revision": 3,
        },
        "booking": {
            "id": "00000000-0000-0000-0000-000000000007",
            "starts_at": (now - timedelta(minutes=1)).isoformat(),
            "ends_at": (now + timedelta(minutes=10)).isoformat(),
        },
        "command": {
            "key": "mock.measure",
            "version": "1",
            "revision": 2,
            "arguments": {"sample": "A"},
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "risk": "medium" if confirmation_required else "low",
            "device_confirmation_required": confirmation_required,
            "safety_contract": safety_contract or {},
            "timeout_seconds": 300,
        },
    }


def config(state_file: Path) -> GatewayConfig:
    return GatewayConfig(
        platform_url="http://127.0.0.1:4000",
        gateway_token=TOKEN,
        adapter_name="mock",
        adapter_config=None,
        state_file=state_file,
        poll_interval_seconds=0.01,
        heartbeat_interval_seconds=0.01,
        request_timeout_seconds=1,
        stop_timeout_seconds=1,
    )


class FakeClient:
    def __init__(self, raw: dict[str, Any] | None = None):
        self.raw = raw
        self.calls: list[tuple[str, Any]] = []
        self.heartbeats: list[dict[str, Any]] = []
        self.heartbeat_error: GatewayAPIError | None = None

    def lease(self) -> dict[str, Any]:
        self.calls.append(("lease", None))
        if self.raw is None:
            return {"job": None, "retry_after_seconds": 15}
        return {
            "job": self.raw,
            "signature": expected_job_signature(self.raw, TOKEN),
            "lease_token": f"aijl_{'b' * 48}",
        }

    def start(self, job_id, lease_token, **payload):
        self.calls.append(("start", payload))
        return {
            "status": "running",
            "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
        }

    def heartbeat(self, job_id, lease_token):
        self.calls.append(("heartbeat", None))
        if self.heartbeat_error is not None:
            raise self.heartbeat_error
        if self.heartbeats:
            return self.heartbeats.pop(0)
        return {
            "status": "running",
            "stop_requested": False,
            "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
        }

    def complete(self, job_id, lease_token, result):
        self.calls.append(("complete", result))
        return {"status": "completed"}

    def fail(self, job_id, lease_token, error):
        self.calls.append(("fail", error))
        return {"status": "failed"}

    def stopped(self, job_id, lease_token, reason):
        self.calls.append(("stopped", reason))
        return {"status": "stopped"}


class BlockingAdapter(InstrumentAdapter):
    def __init__(self):
        self.stop_calls: list[str] = []

    def supports(self, job: InstrumentJobEnvelope) -> bool:
        return job.command_key == "mock.measure" and job.command_version == "1"

    def confirm(self, job: InstrumentJobEnvelope) -> str | None:
        return "device-panel:42"

    def execute(
        self, job: InstrumentJobEnvelope, stop_event: threading.Event
    ) -> dict[str, Any]:
        while not stop_event.wait(0.005):
            pass
        raise RuntimeError("stopped")

    def safe_stop(self, job: InstrumentJobEnvelope, reason: str) -> None:
        self.stop_calls.append(reason)


class GatewayTests(unittest.TestCase):
    def test_signature_verification_rejects_tampering(self):
        raw = envelope()
        signature = expected_job_signature(raw, TOKEN)

        verify_job_signature(raw, signature, TOKEN)
        raw["command"]["arguments"]["sample"] = "B"
        with self.assertRaisesRegex(ValueError, "signature"):
            verify_job_signature(raw, signature, TOKEN)

    def test_envelope_rejects_unsafe_risk_contract(self):
        raw = envelope()
        raw["command"]["risk"] = "high"

        with self.assertRaisesRegex(ValueError, "require device confirmation"):
            InstrumentJobEnvelope.parse(raw)

    def test_config_requires_https_outside_loopback(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "requires HTTPS"),
        ):
            GatewayConfig(
                platform_url="http://lab.example.edu/api",
                gateway_token=TOKEN,
                adapter_name="mock",
                adapter_config=None,
                state_file=Path(directory) / "state.json",
            )

    def test_state_store_is_private_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            store = StateStore(path)
            raw = envelope()
            state = GatewayState(
                phase="leased",
                envelope=raw,
                signature=expected_job_signature(raw, TOKEN),
                lease_token=f"aijl_{'b' * 48}",
            )

            store.save(state)

            self.assertEqual(store.load(), state)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            store.clear()
            self.assertFalse(path.exists())

    def test_mock_adapter_requires_exact_local_allowlist(self):
        raw = envelope()
        job = InstrumentJobEnvelope.parse(raw)
        adapter = MockAdapter(
            [
                {
                    "key": "mock.measure",
                    "version": "1",
                    "result": {"value": 42},
                }
            ]
        )

        self.assertTrue(adapter.supports(job))
        changed = dict(raw)
        changed["command"] = {**raw["command"], "version": "2"}
        self.assertFalse(adapter.supports(InstrumentJobEnvelope.parse(changed)))

    def test_runtime_completes_verified_job_and_clears_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            raw = envelope()
            client = FakeClient(raw)
            adapter = MockAdapter(
                [
                    {
                        "key": "mock.measure",
                        "version": "1",
                        "result": {"value": 42},
                        "confirmation_reference": "device-panel:42",
                    }
                ]
            )
            runtime = GatewayRuntime(
                config(state_file), client, adapter, StateStore(state_file)
            )

            self.assertTrue(runtime.run_once())

            self.assertEqual(
                [call[0] for call in client.calls], ["lease", "start", "complete"]
            )
            self.assertEqual(client.calls[-1][1], {"value": 42})
            self.assertFalse(state_file.exists())

    def test_runtime_attests_required_hardware_interlocks_before_start(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            contract = {
                "required_interlocks": ["lid.closed", "temperature.safe"],
                "operator_presence_required": True,
                "emergency_stop_required": True,
            }
            client = FakeClient(envelope(safety_contract=contract))
            adapter = MockAdapter(
                [
                    {
                        "key": "mock.measure",
                        "version": "1",
                        "result": {"value": 42},
                        "safety_attestation": {
                            "interlocks": {
                                "lid.closed": True,
                                "temperature.safe": True,
                            },
                            "operator_present": True,
                            "emergency_stop_available": True,
                            "reference": "mock-panel:preflight-42",
                        },
                    }
                ]
            )

            self.assertTrue(
                GatewayRuntime(
                    config(state_file), client, adapter, StateStore(state_file)
                ).run_once()
            )

            start_payload = next(
                value for name, value in client.calls if name == "start"
            )
            self.assertEqual(
                start_payload["safety_attestation"]["reference"],
                "mock-panel:preflight-42",
            )
            self.assertEqual(client.calls[-1][0], "complete")

    def test_runtime_fails_closed_when_one_hardware_interlock_is_open(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            client = FakeClient(
                envelope(
                    safety_contract={
                        "required_interlocks": ["lid.closed"],
                        "operator_presence_required": False,
                        "emergency_stop_required": False,
                    }
                )
            )
            adapter = MockAdapter(
                [
                    {
                        "key": "mock.measure",
                        "version": "1",
                        "result": {"value": 42},
                        "safety_attestation": {
                            "interlocks": {"lid.closed": False},
                            "reference": "mock-panel:preflight-43",
                        },
                    }
                ]
            )

            self.assertTrue(
                GatewayRuntime(
                    config(state_file), client, adapter, StateStore(state_file)
                ).run_once()
            )

            self.assertEqual([name for name, _value in client.calls], ["lease", "fail"])
            self.assertIn("lid.closed", client.calls[-1][1])

    def test_runtime_honors_stop_before_acknowledging(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            client = FakeClient(envelope(confirmation_required=True))
            client.heartbeats = [
                {
                    "status": "stop_requested",
                    "stop_requested": True,
                    "reason": "operator requested stop",
                }
            ]
            adapter = BlockingAdapter()
            runtime = GatewayRuntime(
                config(state_file), client, adapter, StateStore(state_file)
            )

            self.assertTrue(runtime.run_once())

            self.assertEqual(adapter.stop_calls, ["operator requested stop"])
            self.assertEqual(client.calls[-1], ("stopped", "operator requested stop"))
            self.assertFalse(state_file.exists())

    def test_runtime_safe_stops_when_control_connection_is_lost(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            client = FakeClient(envelope(confirmation_required=True))
            client.heartbeat_error = GatewayAPIError("offline")
            adapter = BlockingAdapter()
            runtime = GatewayRuntime(
                config(state_file), client, adapter, StateStore(state_file)
            )

            self.assertTrue(runtime.run_once())

            self.assertEqual(len(adapter.stop_calls), 1)
            self.assertIn("control connection lost", adapter.stop_calls[0])
            self.assertEqual(client.calls[-1][0], "stopped")
            self.assertFalse(state_file.exists())

    def test_recovery_replays_pending_completion_without_rerunning_device(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            raw = envelope()
            state = GatewayState(
                phase="completion_pending",
                envelope=raw,
                signature=expected_job_signature(raw, TOKEN),
                lease_token=f"aijl_{'b' * 48}",
                result={"value": 42},
            )
            StateStore(state_file).save(state)
            client = FakeClient()
            adapter = MockAdapter(
                [
                    {
                        "key": "mock.measure",
                        "version": "1",
                        "result": {"value": 0},
                    }
                ]
            )
            runtime = GatewayRuntime(
                config(state_file), client, adapter, StateStore(state_file)
            )

            self.assertTrue(runtime.recover_pending())

            self.assertEqual(client.calls, [("complete", {"value": 42})])
            self.assertFalse(state_file.exists())

    def test_mock_execution_can_be_stopped(self):
        raw = envelope()
        job = InstrumentJobEnvelope.parse(raw)
        adapter = MockAdapter(
            [
                {
                    "key": "mock.measure",
                    "version": "1",
                    "result": {"value": 42},
                    "delay_seconds": 1,
                }
            ]
        )
        stopped = threading.Event()
        stopped.set()

        with self.assertRaisesRegex(RuntimeError, "stopped"):
            adapter.execute(job, stopped)


if __name__ == "__main__":
    unittest.main()
