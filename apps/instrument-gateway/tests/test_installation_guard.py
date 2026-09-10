import subprocess
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path

from test_gateway import TOKEN, BlockingAdapter, FakeClient, config, envelope

from airalogy_instrument_gateway.runtime import GatewayHaltError, GatewayRuntime
from airalogy_instrument_gateway.security import expected_job_signature
from airalogy_instrument_gateway.state import GatewayState, StateStore


class InstallationGuardTests(unittest.TestCase):
    def test_hung_vendor_stop_is_bounded_and_latched_in_process(self):
        release = threading.Event()

        class HungStop(BlockingAdapter):
            def safe_stop(self, job, reason):
                release.wait(10)

        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            raw = envelope()
            store.save(
                GatewayState(
                    phase="stop_unconfirmed",
                    envelope=raw,
                    signature=expected_job_signature(raw, TOKEN),
                    lease_token="aijl_" + "b" * 48,
                    error="stop lost",
                )
            )
            runtime = GatewayRuntime(
                replace(config(store.path), stop_timeout_seconds=0.02),
                FakeClient(),
                HungStop(),
                store,
            )
            try:
                with self.assertRaisesRegex(GatewayHaltError, "timeout"):
                    runtime.run_once()
                with self.assertRaisesRegex(GatewayHaltError, "still alive"):
                    runtime.run_once()
                self.assertIsNotNone(store.load())
            finally:
                release.set()
                runtime._stop_worker.join(1)

    def test_lock_is_cross_process_and_releases_without_unlinking(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            script = "from pathlib import Path; from airalogy_instrument_gateway.state import StateStore; import sys;\nwith StateStore(Path(sys.argv[1])).exclusive(): pass"
            with store.exclusive():
                other = subprocess.run(
                    [sys.executable, "-c", script, str(store.path)],
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(other.returncode, 0)
            other = subprocess.run(
                [sys.executable, "-c", script, str(store.path)],
                capture_output=True,
                check=False,
            )
            self.assertEqual(other.returncode, 0, other.stderr)
            self.assertTrue(store.path.with_name(".state.json.lock").exists())

    def test_failed_stop_survives_restart_and_blocks_installation(self):
        class UnsafeAdapter(BlockingAdapter):
            safe = False

            def safe_stop(self, job, reason):
                self.stop_calls.append(reason)
                if not self.safe:
                    raise RuntimeError("physical stop not confirmed")

        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            raw = envelope()
            store.save(
                GatewayState(
                    phase="stop_unconfirmed",
                    envelope=raw,
                    signature=expected_job_signature(raw, TOKEN),
                    lease_token="aijl_" + "b" * 48,
                    error="physical stop not confirmed",
                )
            )
            adapter, client = UnsafeAdapter(), FakeClient()
            for _ in range(2):
                runtime = GatewayRuntime(config(store.path), client, adapter, store)
                with self.assertRaises(GatewayHaltError):
                    runtime.run_once()
                self.assertEqual(store.load().phase, "stop_unconfirmed")
                with store.exclusive(), self.assertRaises(ValueError):
                    store.assert_installable()
            self.assertEqual(client.calls, [])
            adapter.safe = True
            self.assertTrue(runtime.run_once())
            self.assertEqual(client.calls, [("fail", "physical stop not confirmed")])
            with store.exclusive():
                store.assert_installable()

    def test_execution_exception_requires_safe_stop_before_failure_receipt(self):
        class FailingAdapter(BlockingAdapter):
            def execute(self, job, stop_event):
                raise RuntimeError("controller connection lost after start")

        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            adapter, client = FailingAdapter(), FakeClient(envelope())
            runtime = GatewayRuntime(config(store.path), client, adapter, store)
            self.assertTrue(runtime.run_once())
            self.assertEqual(len(adapter.stop_calls), 1)
            self.assertEqual(client.calls[-1][0], "fail")
            self.assertEqual(client.failure_confirmations, [True])
            self.assertIsNone(store.load())

    def test_nonterminal_failure_receipt_cannot_clear_local_hold(self):
        class HoldingClient(FakeClient):
            def fail(self, *args, **kwargs):
                return {"status": "stop_requested"}

        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            raw = envelope()
            store.save(
                GatewayState(
                    phase="stop_unconfirmed",
                    envelope=raw,
                    signature=expected_job_signature(raw, TOKEN),
                    lease_token="aijl_" + "b" * 48,
                    error="connection lost",
                )
            )
            runtime = GatewayRuntime(
                config(store.path), HoldingClient(), BlockingAdapter(), store
            )
            with self.assertRaisesRegex(GatewayHaltError, "not acknowledged"):
                runtime.run_once()
            self.assertEqual(store.load().phase, "failure_pending")
            with self.assertRaises(ValueError):
                store.assert_installable()

    def test_legacy_failure_receipt_does_not_prove_physical_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            raw = envelope()
            store.save(
                GatewayState(
                    phase="failure_pending",
                    envelope=raw,
                    signature=expected_job_signature(raw, TOKEN),
                    lease_token="aijl_" + "b" * 48,
                    error="legacy failure",
                )
            )
            adapter, client = BlockingAdapter(), FakeClient()
            GatewayRuntime(config(store.path), client, adapter, store).run_once()
            self.assertEqual(adapter.stop_calls, ["legacy failure"])
            self.assertEqual(client.calls, [("fail", "legacy failure")])
