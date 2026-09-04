"""Single-job Gateway runtime with heartbeat, stop, and crash recovery."""

from __future__ import annotations

import logging
import queue
import signal
import threading
from datetime import UTC, datetime
from typing import Any

from .adapters import InstrumentAdapter
from .client import GatewayAPIError, PlatformClient
from .config import GatewayConfig
from .models import InstrumentJobEnvelope, validate_safety_attestation
from .security import verify_job_signature
from .state import GatewayState, StateStore

LOGGER = logging.getLogger("airalogy.instrument_gateway")


class GatewayHaltError(RuntimeError):
    """The process must stop before accepting another physical operation."""


class GatewayRuntime:
    def __init__(
        self,
        config: GatewayConfig,
        client: PlatformClient,
        adapter: InstrumentAdapter,
        state_store: StateStore,
    ):
        self.config = config
        self.client = client
        self.adapter = adapter
        self.state_store = state_store
        self.shutdown_event = threading.Event()

    def request_shutdown(self) -> None:
        self.shutdown_event.set()

    def _verified_job(
        self, envelope: dict[str, Any], signature: str
    ) -> InstrumentJobEnvelope:
        verify_job_signature(envelope, signature, self.config.gateway_token)
        job = InstrumentJobEnvelope.parse(envelope)
        if job.lease_expires_at <= datetime.now(UTC):
            raise ValueError("Instrument Job lease is already expired")
        return job

    def _save_pending(
        self,
        state: GatewayState,
        phase: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        stop_reason: str | None = None,
    ) -> None:
        state.phase = phase
        state.result = result
        state.error = error
        state.stop_reason = stop_reason
        self.state_store.save(state)

    def _report_failure(
        self, job: InstrumentJobEnvelope, state: GatewayState, error: str
    ) -> None:
        self._save_pending(state, "failure_pending", error=error)
        self.client.fail(job.job_id, state.lease_token, error)
        self.state_store.clear()

    def _stop_and_acknowledge(
        self,
        job: InstrumentJobEnvelope,
        state: GatewayState,
        stop_event: threading.Event,
        worker: threading.Thread,
        reason: str,
    ) -> None:
        stop_event.set()
        try:
            self.adapter.safe_stop(job, reason)
        except Exception as error:  # noqa: BLE001 - adapter is an isolation boundary
            message = f"Local safe-stop failed: {error}"
            self._save_pending(state, "failure_pending", error=message)
            try:
                self.client.fail(job.job_id, state.lease_token, message)
            finally:
                raise GatewayHaltError(message) from error
        worker.join(self.config.stop_timeout_seconds)
        if worker.is_alive():
            message = "Adapter did not stop within the configured local stop timeout"
            self._save_pending(state, "failure_pending", error=message)
            try:
                self.client.fail(job.job_id, state.lease_token, message)
            finally:
                raise GatewayHaltError(message)
        self._save_pending(state, "stop_ack_pending", stop_reason=reason)
        self.client.stopped(job.job_id, state.lease_token, reason)
        self.state_store.clear()

    def recover_pending(self) -> bool:
        state = self.state_store.load()
        if state is None:
            return False
        verify_job_signature(state.envelope, state.signature, self.config.gateway_token)
        job = InstrumentJobEnvelope.parse(state.envelope)
        if not self.adapter.supports(job):
            raise GatewayHaltError(
                "Pending job has no matching local adapter; do not accept new work"
            )
        if state.phase == "completion_pending" and state.result is not None:
            self.client.complete(job.job_id, state.lease_token, state.result)
            self.state_store.clear()
            return True
        if state.phase == "failure_pending" and state.error:
            self.client.fail(job.job_id, state.lease_token, state.error)
            self.state_store.clear()
            return True
        if state.phase == "stop_ack_pending" and state.stop_reason:
            self.client.stopped(job.job_id, state.lease_token, state.stop_reason)
            self.state_store.clear()
            return True
        if state.phase == "leased":
            self._report_failure(
                job,
                state,
                "Gateway restarted after lease and before confirmed device start",
            )
            return True

        reason = "Gateway restarted while a physical operation might still be active"
        try:
            self.adapter.safe_stop(job, reason)
        except Exception as error:
            raise GatewayHaltError(
                f"Restart recovery safe-stop failed: {error}"
            ) from error
        self._save_pending(state, "stop_ack_pending", stop_reason=reason)
        self.client.stopped(job.job_id, state.lease_token, reason)
        self.state_store.clear()
        return True

    def run_once(self) -> bool:
        if self.state_store.load() is not None:
            return self.recover_pending()
        leased = self.client.lease()
        raw_job = leased.get("job")
        if raw_job is None:
            return False
        signature = leased.get("signature")
        lease_token = leased.get("lease_token")
        if not isinstance(raw_job, dict):
            raise TypeError("Platform lease response job must be an object")
        if (
            not isinstance(signature, str)
            or not isinstance(lease_token, str)
            or not lease_token.startswith("aijl_")
            or len(lease_token) < 40
        ):
            raise ValueError(
                "Platform lease response is missing signature or lease token"
            )
        job = self._verified_job(raw_job, signature)
        state = GatewayState(
            phase="leased",
            envelope=raw_job,
            signature=signature,
            lease_token=lease_token,
        )
        self.state_store.save(state)
        if not self.adapter.supports(job):
            self._report_failure(
                job,
                state,
                f"No local adapter allows {job.command_key}@{job.command_version}",
            )
            return True
        confirmation_reference = self.adapter.confirm(job) or ""
        if job.device_confirmation_required and not confirmation_reference:
            self._report_failure(
                job,
                state,
                "Required device-local confirmation was not provided",
            )
            return True
        try:
            safety_attestation = validate_safety_attestation(
                job.safety_contract,
                self.adapter.preflight(job),
            )
        except Exception as error:  # noqa: BLE001 - adapter is an isolation boundary
            self._report_failure(job, state, f"Local safety preflight failed: {error}")
            return True
        start_response = self.client.start(
            job.job_id,
            lease_token,
            device_confirmed=bool(confirmation_reference),
            confirmation_reference=confirmation_reference,
            safety_attestation=safety_attestation,
        )
        self._save_pending(
            state,
            "started",
            stop_reason=None,
        )
        if isinstance(start_response.get("lease_expires_at"), str):
            state.metadata["lease_expires_at"] = start_response["lease_expires_at"]
            self.state_store.save(state)

        stop_event = threading.Event()
        outcomes: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

        def execute() -> None:
            try:
                result = self.adapter.execute(job, stop_event)
                if not isinstance(result, dict):
                    raise TypeError("Instrument adapter result must be a JSON object")
                outcomes.put(("completed", result))
            except Exception as error:  # noqa: BLE001 - worker must report adapter faults
                outcomes.put(("failed", error))

        worker = threading.Thread(
            target=execute,
            name=f"instrument-job-{job.job_id}",
            daemon=True,
        )
        worker.start()
        while True:
            try:
                outcome, value = outcomes.get(
                    timeout=self.config.heartbeat_interval_seconds
                )
            except queue.Empty:
                if self.shutdown_event.is_set():
                    self._stop_and_acknowledge(
                        job,
                        state,
                        stop_event,
                        worker,
                        "Instrument Gateway process is shutting down",
                    )
                    return True
                try:
                    heartbeat = self.client.heartbeat(job.job_id, lease_token)
                except GatewayAPIError as error:
                    reason = f"Platform control connection lost: {error}"
                    self._stop_and_acknowledge(job, state, stop_event, worker, reason)
                    return True
                if heartbeat.get("stop_requested") is True:
                    reason = str(heartbeat.get("reason") or "Platform requested stop")
                    self._stop_and_acknowledge(job, state, stop_event, worker, reason)
                    return True
                if isinstance(heartbeat.get("lease_expires_at"), str):
                    state.metadata["lease_expires_at"] = heartbeat["lease_expires_at"]
                    self.state_store.save(state)
                continue
            if outcome == "completed":
                self._save_pending(state, "completion_pending", result=value)
                self.client.complete(job.job_id, lease_token, value)
                self.state_store.clear()
                return True
            error = f"Local instrument execution failed: {value}"
            self._report_failure(job, state, error)
            return True

    def run_forever(self) -> None:
        def stop_handler(_signum, _frame) -> None:
            self.request_shutdown()

        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, stop_handler)
            signal.signal(signal.SIGTERM, stop_handler)
        LOGGER.info("Instrument Gateway started")
        while not self.shutdown_event.is_set():
            try:
                handled = self.run_once()
            except GatewayHaltError:
                raise
            except (GatewayAPIError, OSError, ValueError) as error:
                LOGGER.error("Gateway cycle failed: %s", error)
                handled = False
            if not handled:
                self.shutdown_event.wait(self.config.poll_interval_seconds)
        LOGGER.info("Instrument Gateway stopped")
