"""Single-job Runner lifecycle with heartbeats, cancellation, and recovery."""

from __future__ import annotations

import logging
import math
import signal
import subprocess
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .client import PlatformClient, RunnerAPIError
from .config import RunnerConfig
from .engine import ContainerEngine, EngineError, JobProcess
from .models import ComputeJobEnvelope
from .security import sha256_file, verify_job_signature
from .state import RunnerState, StateStore

LOGGER = logging.getLogger("airalogy.compute_runner")


class RunnerHaltError(RuntimeError):
    """Local isolation may be compromised; supervision must restart the process."""


class RunnerRuntime:
    def __init__(
        self,
        config: RunnerConfig,
        client: PlatformClient,
        engine: ContainerEngine,
        state_store: StateStore,
    ):
        self.config = config
        self.client = client
        self.engine = engine
        self.state_store = state_store
        self.shutdown_event = threading.Event()

    def request_shutdown(self) -> None:
        self.shutdown_event.set()

    def _verified_job(
        self, envelope: dict[str, Any], signature: str
    ) -> ComputeJobEnvelope:
        verify_job_signature(envelope, signature, self.config.runner_token)
        job = ComputeJobEnvelope.parse(envelope)
        if job.lease_expires_at <= datetime.now(UTC):
            raise ValueError("Compute Job lease is already expired")
        if job.workspace_bytes > self.config.max_workspace_bytes:
            raise ValueError("Compute Job exceeds this Runner's workspace limit")
        self.engine.network_for(job)
        return job

    def _save_pending(
        self,
        state: RunnerState,
        phase: str,
        *,
        result: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
        error: str | None = None,
        cancel_reason: str | None = None,
    ) -> None:
        state.phase = phase
        state.result = result
        state.usage = usage
        state.error = error
        state.cancel_reason = cancel_reason
        self.state_store.save(state)

    def _cleanup_state(self, state: RunnerState) -> None:
        self.engine.cleanup(state.container_name, state.volume_name)
        self.state_store.clear()

    def _usage(self, started: float, output_bytes: int = 0) -> dict[str, Any]:
        return {
            "wall_seconds": max(0, math.ceil(time.monotonic() - started)),
            "cpu_seconds": 0,
            "max_memory_mb": 0,
            "gpu_seconds": 0,
            "output_bytes": output_bytes,
        }

    def _report_failure(
        self,
        job: ComputeJobEnvelope,
        state: RunnerState,
        error: str,
        usage: dict[str, Any] | None = None,
    ) -> None:
        message = error[:20_000]
        self._save_pending(state, "failure_pending", error=message, usage=usage)
        self.client.fail(job.job_id, state.lease_token, message, usage)
        self._cleanup_state(state)

    def _report_cancelled(
        self,
        job: ComputeJobEnvelope,
        state: RunnerState,
        reason: str,
        usage: dict[str, Any],
    ) -> None:
        message = reason[:2_000]
        self._save_pending(
            state,
            "cancellation_pending",
            cancel_reason=message,
            usage=usage,
        )
        self.client.cancelled(job.job_id, state.lease_token, message, usage)
        self._cleanup_state(state)

    def recover_pending(self) -> bool:
        state = self.state_store.load()
        if state is None:
            return False
        verify_job_signature(state.envelope, state.signature, self.config.runner_token)
        job = ComputeJobEnvelope.parse(state.envelope)
        try:
            if state.phase == "completion_pending" and state.result is not None:
                output_receipts = state.metadata.get("output_receipts") or []
                if not isinstance(output_receipts, list):
                    raise ValueError("Runner output receipt journal is invalid")
                self.client.complete(
                    job.job_id,
                    state.lease_token,
                    state.result,
                    state.usage or self._usage(time.monotonic()),
                    output_receipts,
                )
                self._cleanup_state(state)
                return True
            if state.phase == "output_pending":
                try:
                    self._deliver_success(job, state)
                except EngineError as error:
                    self._report_failure(
                        job,
                        state,
                        f"Compute output collection failed: {error}",
                        state.usage,
                    )
                return True
            if state.phase == "failure_pending" and state.error:
                self.client.fail(
                    job.job_id, state.lease_token, state.error, state.usage
                )
                self._cleanup_state(state)
                return True
            if state.phase == "cancellation_pending" and state.cancel_reason:
                self.client.cancelled(
                    job.job_id,
                    state.lease_token,
                    state.cancel_reason,
                    state.usage,
                )
                self._cleanup_state(state)
                return True
            if state.phase in {"started", "running"}:
                try:
                    self.engine.stop(state.container_name)
                except EngineError as error:
                    raise RunnerHaltError(
                        f"Could not stop uncertain Compute container: {error}"
                    ) from error
                self._report_failure(
                    job,
                    state,
                    "Compute Runner restarted while execution outcome was uncertain",
                )
                return True
            self._report_failure(
                job,
                state,
                "Compute Runner restarted before confirmed container execution",
            )
            return True
        except RunnerAPIError as error:
            if error.status in {413, 415, 422} and state.phase in {
                "output_pending",
                "completion_pending",
            }:
                self._report_failure(
                    job,
                    state,
                    f"Platform rejected Compute output: {error}",
                    state.usage,
                )
                return True
            if error.status == 409:
                if state.phase in {"output_pending", "completion_pending"}:
                    try:
                        heartbeat = self.client.heartbeat(job.job_id, state.lease_token)
                    except RunnerAPIError:
                        heartbeat = {}
                    if heartbeat.get("cancel_requested") is True:
                        self._report_cancelled(
                            job,
                            state,
                            str(
                                heartbeat.get("reason")
                                or "Platform requested cancellation"
                            ),
                            state.usage or self._usage(time.monotonic()),
                        )
                        return True
                LOGGER.error(
                    "Pending callback can no longer be accepted; preserving fail-closed "
                    "Platform state and cleaning local resources: %s",
                    error,
                )
                self._cleanup_state(state)
                return True
            raise

    def _download_inputs(
        self,
        job: ComputeJobEnvelope,
        lease_token: str,
        directory: Path,
    ) -> dict[str, Path]:
        paths: dict[str, Path] = {}
        for item in job.inputs:
            destination = directory / item.id
            self.client.download_input(
                item.download_path,
                lease_token,
                destination,
                expected_size=item.byte_size,
            )
            if sha256_file(destination) != item.checksum_sha256:
                raise ValueError(
                    f"Compute input {item.id} checksum does not match its contract"
                )
            paths[item.id] = destination
        return paths

    def _deliver_success(
        self,
        job: ComputeJobEnvelope,
        state: RunnerState,
    ) -> None:
        usage = dict(state.usage or self._usage(time.monotonic()))
        if state.result is None:
            result, result_bytes = self.engine.read_result(job, state.volume_name)
            usage["output_bytes"] = result_bytes
            self._save_pending(
                state,
                "output_pending",
                result=result,
                usage=usage,
            )
        else:
            result = state.result
        receipts: list[dict[str, Any]] = []
        output_bytes = int(usage.get("output_bytes") or 0)
        for output in job.outputs:
            metadata = self.engine.output_metadata(output, state.volume_name)
            if metadata is None:
                if output.required:
                    raise EngineError(
                        f"Required Compute output {output.mount_name} is missing"
                    )
                continue
            byte_size, checksum = metadata
            output_bytes += byte_size
            if output_bytes > job.max_output_bytes:
                raise EngineError("Combined Compute outputs exceed the approved limit")
            output_process = self.engine.open_output(output, state.volume_name)
            try:
                response = self.client.upload_output(
                    output.upload_path,
                    state.lease_token,
                    output_process.stream,
                    expected_size=byte_size,
                    checksum_sha256=checksum,
                    media_type=output.media_type,
                )
            except Exception:
                self.engine.abort_output(output_process)
                raise
            self.engine.finish_output(output_process)
            lease_expiry = response.get("lease_expires_at")
            if isinstance(lease_expiry, str):
                state.metadata["lease_expires_at"] = lease_expiry
            receipts.append(
                {
                    "output_id": output.id,
                    "checksum_sha256": checksum,
                    "byte_size": byte_size,
                }
            )
            state.metadata["output_receipts"] = list(receipts)
            self.state_store.save(state)
        usage["output_bytes"] = output_bytes
        state.metadata["output_receipts"] = receipts
        self._save_pending(
            state,
            "completion_pending",
            result=result,
            usage=usage,
        )
        self.client.complete(
            job.job_id,
            state.lease_token,
            result,
            usage,
            receipts,
        )
        self._cleanup_state(state)

    def _stop_process(self, process: JobProcess) -> None:
        try:
            self.engine.stop(process.container_name)
        except EngineError as error:
            raise RunnerHaltError(
                "Compute container could not be stopped safely"
            ) from error
        try:
            process.process.wait(timeout=self.config.stop_timeout_seconds + 5)
        except subprocess.TimeoutExpired as error:
            raise RunnerHaltError(
                "Container CLI did not exit after the Compute container stopped"
            ) from error

    def _monitor(
        self,
        job: ComputeJobEnvelope,
        state: RunnerState,
        process: JobProcess,
    ) -> bool:
        started = time.monotonic()
        next_heartbeat = started + self.config.heartbeat_interval_seconds
        while process.process.poll() is None:
            if self.shutdown_event.wait(0.2):
                self._stop_process(process)
                usage = self._usage(started)
                self._report_failure(
                    job,
                    state,
                    "Compute Runner process is shutting down",
                    usage,
                )
                return True
            now = time.monotonic()
            if now - started >= job.timeout_seconds:
                self._stop_process(process)
                usage = self._usage(started)
                self._report_failure(
                    job,
                    state,
                    "Local Compute Job timeout reached",
                    usage,
                )
                return True
            if now < next_heartbeat:
                continue
            try:
                heartbeat = self.client.heartbeat(job.job_id, state.lease_token)
            except RunnerAPIError as error:
                self._stop_process(process)
                usage = self._usage(started)
                self._save_pending(
                    state,
                    "failure_pending",
                    error=f"Platform control connection lost: {error}",
                    usage=usage,
                )
                raise
            if heartbeat.get("cancel_requested") is True:
                reason = str(
                    heartbeat.get("reason") or "Platform requested cancellation"
                )
                self._stop_process(process)
                usage = self._usage(started)
                self._report_cancelled(job, state, reason, usage)
                return True
            lease_expiry = heartbeat.get("lease_expires_at")
            if isinstance(lease_expiry, str):
                state.metadata["lease_expires_at"] = lease_expiry
                self.state_store.save(state)
            next_heartbeat = now + self.config.heartbeat_interval_seconds

        return_code = process.process.returncode
        usage = self._usage(started)
        if return_code != 0:
            error = self.engine.stderr_tail(process)
            self._report_failure(
                job,
                state,
                f"Isolated Compute process exited with code {return_code}: {error}",
                usage,
            )
            return True
        self._save_pending(
            state,
            "output_pending",
            usage=usage,
        )
        try:
            self._deliver_success(job, state)
        except EngineError as error:
            self._report_failure(
                job,
                state,
                f"Compute output collection failed: {error}",
                usage,
            )
        except RunnerAPIError as error:
            if error.status in {413, 415, 422}:
                self._report_failure(
                    job,
                    state,
                    f"Platform rejected Compute output: {error}",
                    state.usage,
                )
            else:
                LOGGER.warning(
                    "Compute result delivery is pending and will be retried: %s",
                    error,
                )
        return True

    def run_once(self) -> bool:
        if self.state_store.load() is not None:
            return self.recover_pending()
        readiness = self.client.report_status(self.config.backend, active=False)
        if readiness.get("execution_ready") is not True:
            return False
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
            or not lease_token.startswith("aicl_")
            or len(lease_token) < 40
        ):
            raise ValueError(
                "Platform lease response is missing signature or lease token"
            )
        job = self._verified_job(raw_job, signature)
        state = RunnerState(
            phase="leased",
            envelope=raw_job,
            signature=signature,
            lease_token=lease_token,
        )
        self.state_store.save(state)
        process: JobProcess | None = None
        try:
            with tempfile.TemporaryDirectory(prefix="airalogy-compute-inputs-") as path:
                input_files = self._download_inputs(job, lease_token, Path(path))
                container_name, volume_name = self.engine.create_workspace(job)
                state.container_name = container_name
                state.volume_name = volume_name
                self._save_pending(state, "staging")
                self.engine.populate_workspace(job, volume_name, input_files)
            self._save_pending(state, "staged")
            started_response = self.client.start(job.job_id, lease_token)
            if isinstance(started_response.get("lease_expires_at"), str):
                state.metadata["lease_expires_at"] = started_response[
                    "lease_expires_at"
                ]
            self._save_pending(state, "started")
            process = self.engine.start(job, container_name, volume_name)
            self._save_pending(state, "running")
            return self._monitor(job, state, process)
        except (RunnerAPIError, EngineError, OSError, ValueError) as error:
            if process is not None and process.process.poll() is None:
                self._stop_process(process)
            self._report_failure(job, state, f"Local Compute setup failed: {error}")
            return True

    def run_forever(self) -> None:
        def stop_handler(_signum, _frame) -> None:
            self.request_shutdown()

        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, stop_handler)
            signal.signal(signal.SIGTERM, stop_handler)
        LOGGER.info("Compute Runner started with %s", self.config.backend)
        while not self.shutdown_event.is_set():
            try:
                handled = self.run_once()
            except RunnerHaltError:
                raise
            except (RunnerAPIError, EngineError, OSError, ValueError) as error:
                LOGGER.error("Runner cycle failed: %s", error)
                handled = False
            if not handled:
                self.shutdown_event.wait(self.config.poll_interval_seconds)
        LOGGER.info("Compute Runner stopped")
