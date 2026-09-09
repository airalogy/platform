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
from .output_contract import digest
from .output_delivery import (
    OutputDelivery,
    authorize_source,
    bundle,
    completed_result,
    receipt_only,
)
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
        adapter: InstrumentAdapter | None,
        state_store: StateStore,
    ):
        self.config = config
        self.client = client
        self.adapter = adapter
        self.state_store = state_store
        self.shutdown_event = threading.Event()
        self._active_worker: threading.Thread | None = None
        self._stop_worker: threading.Thread | None = None
        self._capture_worker: threading.Thread | None = None

    def _confirm_safe_stop(self, job, reason):
        """A stalled vendor stop method must not erase the uncertain state."""
        outcome = queue.Queue(maxsize=1)

        def stop():
            try:
                self.adapter.safe_stop(job, reason)
                outcome.put(None)
            except Exception as error:  # noqa: BLE001 - adapter isolation boundary
                outcome.put(error)

        self._stop_worker = threading.Thread(
            target=stop, daemon=True, name=f"instrument-stop-{job.job_id}"
        )
        self._stop_worker.start()
        self._stop_worker.join(self.config.stop_timeout_seconds)
        if self._stop_worker.is_alive():
            raise GatewayHaltError(
                "Adapter safe-stop exceeded its local timeout; physical stop remains unconfirmed"
            )
        error = outcome.get_nowait()
        if error is not None:
            raise GatewayHaltError(
                f"Adapter could not confirm physical stop: {error}"
            ) from error

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
        if state.phase == "leased":
            state.metadata["safe_for_new_work"] = True
        if not state.metadata.get("safe_for_new_work"):
            # An exception does not establish that a physical process has stopped.
            self._save_pending(state, "stop_unconfirmed", error=error)
            try:
                self._confirm_safe_stop(job, error)
            except Exception as stop_error:
                raise GatewayHaltError(
                    f"Execution failed and safe stop is unconfirmed: {stop_error}"
                ) from stop_error
            state.metadata["safe_for_new_work"] = True
        self._save_pending(state, "failure_pending", error=error)
        receipt = self.client.fail(
            job.job_id,
            state.lease_token,
            error,
            safe_stop_confirmed=True,
        )
        if receipt.get("status") != "failed":
            raise GatewayHaltError("Platform has not acknowledged a safely failed job")
        self.state_store.clear()

    def _capture(self, delivery, job, state):
        if state.phase == "outputs_pending":
            return delivery.capture()
        outcomes = queue.Queue(maxsize=1)

        def capture():
            try:
                outcomes.put((True, delivery.capture()))
            except Exception as error:  # noqa: BLE001 - local I/O worker boundary
                outcomes.put((False, error))

        self._capture_worker = threading.Thread(
            target=capture, daemon=True, name="instrument-file-capture"
        )
        self._capture_worker.start()
        while True:
            try:
                passed, value = outcomes.get(
                    timeout=self.config.heartbeat_interval_seconds
                )
                if not passed:
                    raise value
                return value
            except queue.Empty:
                if self.shutdown_event.is_set():
                    raise GatewayHaltError(
                        "Acquisition finished; preserve its journal and snapshot for receipt recovery"
                    )
                try:
                    heartbeat = self.client.heartbeat(job.job_id, state.lease_token)
                except GatewayAPIError as error:
                    raise GatewayHaltError(
                        "Connection lost during capture; reconcile completed acquisition without repeating it"
                    ) from error
                if heartbeat.get("stop_requested") is True:
                    raise GatewayHaltError(
                        "Platform requested reconciliation during capture; do not repeat the completed acquisition"
                    )

    def _complete(self, job, state):
        delivery = (
            OutputDelivery(self.config, self.client, self.state_store, state, job)
            if bundle(job)
            else None
        )
        if state.phase == "outputs_pending" and delivery is None:
            raise GatewayHaltError(
                "Pending file delivery lost its signed receiving plan"
            )
        # Capture before releasing equipment occupancy. A future run may reuse
        # a vendor filename; neither recovery nor retries may repin those bytes.
        capture = None
        if (
            delivery
            and state.phase == "completion_pending"
            and not state.metadata.get("output_capture_digest")
        ):
            capture = self._capture(delivery, job, state)
            state.metadata["output_capture_digest"] = digest(capture)
            self.state_store.save(state)
        if state.phase == "completion_pending":
            receipt = self.client.complete(job.job_id, state.lease_token, state.result)
            if receipt.get("status") != "completed" or (
                delivery and type(receipt.get("files_pending")) is not bool
            ):
                raise GatewayHaltError(
                    "Platform has not acknowledged completed acquisition"
                )
            if delivery:
                self._save_pending(state, "outputs_pending", result=state.result)
        if delivery:
            capture = capture if capture is not None else delivery.capture()
            if digest(capture) != state.metadata.get("output_capture_digest"):
                raise GatewayHaltError(
                    "Captured files differ from the durable acquisition manifest"
                )
            delivery.deliver(capture)
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
            self._confirm_safe_stop(job, reason)
        except Exception as error:  # noqa: BLE001 - adapter is an isolation boundary
            message = f"Local safe-stop failed: {error}"
            self._save_pending(state, "stop_unconfirmed", error=message)
            try:
                self.client.fail(job.job_id, state.lease_token, message)
            finally:
                raise GatewayHaltError(message) from error
        worker.join(self.config.stop_timeout_seconds)
        if worker.is_alive():
            message = "Adapter did not stop within the configured local stop timeout"
            self._save_pending(state, "stop_unconfirmed", error=message)
            try:
                self.client.fail(job.job_id, state.lease_token, message)
            finally:
                raise GatewayHaltError(message)
        self._save_pending(state, "stop_ack_pending", stop_reason=reason)
        self.client.stopped(job.job_id, state.lease_token, reason)
        self.state_store.clear()

    def recover_pending(self) -> bool:
        if any(
            worker is not None and worker.is_alive()
            for worker in [self._active_worker, self._stop_worker, self._capture_worker]
        ):
            raise GatewayHaltError(
                "An earlier adapter worker is still alive; do not reconcile or accept new work"
            )
        state = self.state_store.load()
        if state is None:
            return False
        verify_job_signature(state.envelope, state.signature, self.config.gateway_token)
        job = InstrumentJobEnvelope.parse(state.envelope)
        if state.phase == "completion_unresolved":
            raise GatewayHaltError(
                "Acquisition returned an invalid completion record; reconcile without repeating the instrument command"
            )
        if receipt_only(state):
            if state.result is None:
                raise GatewayHaltError(
                    "Receipt recovery has lost its acquisition result"
                )
            self._complete(job, state)
            return True
        if self.adapter is None or not self.adapter.supports(job):
            raise GatewayHaltError(
                "Pending job has no matching local adapter; do not accept new work"
            )
        if state.phase == "completion_pending" and state.result is not None:
            self._complete(job, state)
            return True
        if state.phase in {"failure_pending", "stop_unconfirmed"} and state.error:
            if not state.metadata.get("safe_for_new_work"):
                try:
                    self._confirm_safe_stop(job, state.error)
                except Exception as error:
                    raise GatewayHaltError(
                        f"Recovery safe-stop remains unconfirmed: {error}"
                    ) from error
                state.metadata["safe_for_new_work"] = True
                self._save_pending(state, "failure_pending", error=state.error)
            receipt = self.client.fail(
                job.job_id,
                state.lease_token,
                state.error,
                safe_stop_confirmed=True,
            )
            if receipt.get("status") != "failed":
                raise GatewayHaltError(
                    "Platform has not acknowledged a safely failed job"
                )
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
            self._confirm_safe_stop(job, reason)
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
        if self.adapter is None:
            raise GatewayHaltError("Receipt-only recovery cannot lease or execute work")
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
        try:
            if bundle(job):
                if self.config.output_root is None:
                    raise ValueError(
                        "File-producing jobs require an explicitly authorized output root"
                    )
                state.metadata["output_root"] = authorize_source(
                    self.config.output_root, self.state_store.path
                )
                self.state_store.save(state)
        except (ValueError, TypeError, OSError) as error:
            self._report_failure(
                job, state, f"Local file receiving preflight failed: {error}"
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
        except GatewayHaltError:
            # A bounded managed preflight may leave a probe thread alive. Keep
            # the journal and process lock until the process exits; do not poll
            # another job after claiming that this controller is idle.
            raise
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
                outcomes.put(("completed", result))
            except Exception as error:  # noqa: BLE001 - worker must report adapter faults
                outcomes.put(("failed", error))

        worker = threading.Thread(
            target=execute,
            name=f"instrument-job-{job.job_id}",
            daemon=True,
        )
        self._active_worker = worker
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
                try:
                    result, files = completed_result(job, value)
                except Exception as error:
                    self._save_pending(
                        state,
                        "completion_unresolved",
                        error=f"Invalid acquisition completion: {error}"[:2000],
                    )
                    raise GatewayHaltError(
                        "Acquisition completion needs reconciliation; physical work will not be repeated"
                    ) from error
                state.metadata["output_sources"] = files
                self._save_pending(state, "completion_pending", result=result)
                self._complete(job, state)
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
