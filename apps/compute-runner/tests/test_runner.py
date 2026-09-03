from __future__ import annotations

import hashlib
import io
import stat
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID

from airalogy_compute_runner.client import RunnerAPIError
from airalogy_compute_runner.config import RunnerConfig
from airalogy_compute_runner.engine import ContainerEngine, JobProcess, OutputProcess
from airalogy_compute_runner.models import ComputeJobEnvelope
from airalogy_compute_runner.runtime import RunnerRuntime
from airalogy_compute_runner.security import (
    expected_job_signature,
    verify_job_signature,
)
from airalogy_compute_runner.state import RunnerState, StateStore

TOKEN = f"aicr_{'a' * 48}"
HELPER = f"busybox@sha256:{'b' * 64}"


def envelope(
    *,
    inputs: list[dict[str, Any]] | None = None,
    outputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    source = "\nimport json, os\njson.dump({'value': 42}, open(os.environ['AIRALOGY_RESULT_JSON'], 'w'))\n"

    return {
        "schema": "airalogy.compute-job.v1",
        "job_id": "00000000-0000-0000-0000-000000000001",
        "action_id": "00000000-0000-0000-0000-000000000002",
        "task_id": "00000000-0000-0000-0000-000000000003",
        "run_id": "00000000-0000-0000-0000-000000000004",
        "issued_at": now.isoformat(),
        "lease_expires_at": (now + timedelta(minutes=2)).isoformat(),
        "environment": {
            "id": "00000000-0000-0000-0000-000000000005",
            "revision_id": "00000000-0000-0000-0000-000000000006",
            "revision": 3,
            "image_ref": f"python@sha256:{'c' * 64}",
            "runtime_version": "3.12",
            "language": "python",
            "resource_limits": {
                "cpu_millis": 1000,
                "memory_mb": 256,
                "gpu_count": 0,
                "timeout_seconds": 60,
                "max_output_bytes": 4096,
            },
            "network_policy": "none",
            "allowed_egress_hosts": [],
        },
        "source": {
            "code": source,
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
        },
        "input_payload": {"question": "answer"},
        "inputs": inputs or [],
        "outputs": outputs or [],
        "result_schema": {"type": "object"},
    }


def config(state_file: Path) -> RunnerConfig:
    return RunnerConfig(
        platform_url="http://127.0.0.1:4000",
        runner_token=TOKEN,
        state_file=state_file,
        backend="docker",
        helper_image=HELPER,
        egress_networks={},
        poll_interval_seconds=0.01,
        heartbeat_interval_seconds=0.01,
        request_timeout_seconds=1,
        stop_timeout_seconds=1,
        max_workspace_bytes=64 * 1024 * 1024,
    )


def output_declaration(*, required: bool = True) -> dict[str, Any]:
    job_id = "00000000-0000-0000-0000-000000000001"
    output_id = "00000000-0000-0000-0000-000000000008"
    return {
        "id": output_id,
        "mount_name": "analysis.json",
        "upload_path": f"/compute-runner/v1/jobs/{job_id}/outputs/{output_id}",
        "asset_name": "Analysis output",
        "description": "Verified analysis artifact",
        "kind": "file",
        "media_type": "application/json",
        "max_bytes": 2048,
        "required": required,
        "data_schema": {},
        "metadata": {"role": "analysis"},
    }


class FakeProcess:
    def __init__(self, running: bool = False):
        self.returncode = None if running else 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = self.returncode or 143
        return self.returncode


class FakeEngine:
    def __init__(self, *, running: bool = False, output_payload: bytes | None = None):
        self.running = running
        self.output_payload = output_payload
        self.calls: list[str] = []
        self.process: FakeProcess | None = None

    def network_for(self, job):
        self.calls.append("network")
        return "none"

    def create_workspace(self, job):
        self.calls.append("create")
        return ContainerEngine.names(job.job_id)

    def populate_workspace(self, job, volume_name, input_files):
        self.calls.append("populate")

    def start(self, job, container_name, volume_name):
        self.calls.append("start")
        self.process = FakeProcess(self.running)
        return JobProcess(self.process, container_name, volume_name)

    def read_result(self, job, volume_name):
        self.calls.append("result")
        return {"value": 42}, 13

    def stderr_tail(self, process, limit=8000):
        return ""

    def output_metadata(self, output, volume_name):
        self.calls.append("output-metadata")
        if self.output_payload is None:
            return None
        return len(self.output_payload), hashlib.sha256(self.output_payload).hexdigest()

    def open_output(self, output, volume_name):
        self.calls.append("open-output")
        return OutputProcess(FakeProcess(), io.BytesIO(self.output_payload or b""))

    def finish_output(self, process):
        self.calls.append("finish-output")
        process.stream.close()

    def abort_output(self, process):
        self.calls.append("abort-output")
        process.stream.close()

    def stop(self, container_name):
        self.calls.append("stop")
        if self.process is not None:
            self.process.returncode = 143

    def cleanup(self, container_name, volume_name):
        self.calls.append("cleanup")


class FakeClient:
    def __init__(self, raw: dict[str, Any]):
        self.raw = raw
        self.calls: list[tuple[str, Any]] = []
        self.cancel_on_heartbeat = False
        self.completed_outputs: list[dict[str, Any]] = []

    def report_status(self, backend, *, active):
        self.calls.append(("status", active))
        return {"execution_ready": True}

    def lease(self):
        self.calls.append(("lease", None))
        return {
            "job": self.raw,
            "signature": expected_job_signature(self.raw, TOKEN),
            "lease_token": f"aicl_{'d' * 48}",
        }

    def download_input(self, path, lease_token, destination, *, expected_size):
        self.calls.append(("download", path))
        destination.write_bytes(b"x" * expected_size)

    def start(self, job_id, lease_token):
        self.calls.append(("start", None))
        return {
            "status": "running",
            "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
        }

    def heartbeat(self, job_id, lease_token):
        self.calls.append(("heartbeat", None))
        return {
            "status": "cancel_requested" if self.cancel_on_heartbeat else "running",
            "cancel_requested": self.cancel_on_heartbeat,
            "reason": "operator cancelled" if self.cancel_on_heartbeat else None,
        }

    def upload_output(
        self,
        path,
        lease_token,
        source,
        *,
        expected_size,
        checksum_sha256,
        media_type,
    ):
        payload = source.read()
        self.calls.append(("upload-output", path))
        if len(payload) != expected_size:
            raise AssertionError("test output size mismatch")
        return {
            "status": "uploaded",
            "checksum_sha256": checksum_sha256,
            "byte_size": expected_size,
        }

    def complete(self, job_id, lease_token, result, usage, outputs):
        self.completed_outputs = outputs
        self.calls.append(("complete", result))
        return {"status": "completed"}

    def fail(self, job_id, lease_token, error, usage=None):
        self.calls.append(("fail", error))
        return {"status": "failed"}

    def cancelled(self, job_id, lease_token, reason, usage=None):
        self.calls.append(("cancelled", reason))
        return {"status": "cancelled"}


class InterruptedUploadClient(FakeClient):
    def __init__(self, raw: dict[str, Any]):
        super().__init__(raw)
        self.interrupted = False

    def upload_output(self, *args, **kwargs):
        if not self.interrupted:
            self.interrupted = True
            raise RunnerAPIError("simulated network interruption")
        return super().upload_output(*args, **kwargs)


class FailRunningSaveStore(StateStore):
    def save(self, state):
        if state.phase == "running":
            raise OSError("simulated journal failure")
        super().save(state)


class RunnerTests(unittest.TestCase):
    def test_signature_and_exact_source_digest_reject_tampering(self):
        raw = envelope()
        signature = expected_job_signature(raw, TOKEN)

        verify_job_signature(raw, signature, TOKEN)
        parsed = ComputeJobEnvelope.parse(raw)
        self.assertTrue(parsed.source_code.startswith("\nimport"))

        raw["source"]["code"] += "# changed"
        with self.assertRaisesRegex(ValueError, "signature"):
            verify_job_signature(raw, signature, TOKEN)

    def test_envelope_rejects_mutable_image_and_path_traversal(self):
        raw = envelope()
        raw["environment"]["image_ref"] = "python:latest"
        with self.assertRaisesRegex(ValueError, "immutable"):
            ComputeJobEnvelope.parse(raw)

        raw = envelope(
            inputs=[
                {
                    "id": "../../escape",
                    "mount_name": "input.csv",
                    "download_path": "/compute-runner/v1/jobs/a/inputs/b",
                    "checksum_sha256": "a" * 64,
                    "byte_size": 1,
                }
            ]
        )
        with self.assertRaisesRegex(ValueError, "UUID"):
            ComputeJobEnvelope.parse(raw)

        input_id = "00000000-0000-0000-0000-000000000007"
        raw = envelope(
            inputs=[
                {
                    "id": input_id,
                    "mount_name": "input.csv",
                    "download_path": (
                        "/compute-runner/v1/jobs/"
                        "00000000-0000-0000-0000-000000000099/inputs/"
                        f"{input_id}"
                    ),
                    "checksum_sha256": "a" * 64,
                    "byte_size": 1,
                }
            ]
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            ComputeJobEnvelope.parse(raw)

        output = output_declaration()
        output["upload_path"] = (
            "/compute-runner/v1/jobs/00000000-0000-0000-0000-000000000099/"
            f"outputs/{output['id']}"
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            ComputeJobEnvelope.parse(envelope(outputs=[output]))

    def test_config_requires_https_and_immutable_helper(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "requires HTTPS"),
        ):
            RunnerConfig(
                platform_url="http://lab.example.edu",
                runner_token=TOKEN,
                state_file=Path(directory) / "state.json",
                backend="podman",
                helper_image=HELPER,
                egress_networks={},
            )

        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "immutable"),
        ):
            RunnerConfig(
                platform_url="https://lab.example.edu",
                runner_token=TOKEN,
                state_file=Path(directory) / "state.json",
                backend="podman",
                helper_image="busybox:latest",
                egress_networks={},
            )

    def test_state_store_is_private_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            store = StateStore(path)
            raw = envelope()
            state = RunnerState(
                phase="leased",
                envelope=raw,
                signature=expected_job_signature(raw, TOKEN),
                lease_token=f"aicl_{'d' * 48}",
            )
            store.save(state)

            self.assertEqual(store.load(), state)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_runtime_completes_job_and_clears_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            client = FakeClient(envelope())
            engine = FakeEngine()
            runtime = RunnerRuntime(
                config(state_path), client, engine, StateStore(state_path)
            )

            self.assertTrue(runtime.run_once())

            self.assertEqual(
                [name for name, _payload in client.calls],
                ["status", "lease", "start", "complete"],
            )
            self.assertEqual(engine.calls[-2:], ["result", "cleanup"])
            self.assertFalse(state_path.exists())

    def test_runtime_uploads_declared_output_before_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            payload = b'{"rows":42}'
            client = FakeClient(envelope(outputs=[output_declaration()]))
            engine = FakeEngine(output_payload=payload)
            runtime = RunnerRuntime(
                config(state_path), client, engine, StateStore(state_path)
            )

            self.assertTrue(runtime.run_once())

            names = [name for name, _payload in client.calls]
            self.assertLess(names.index("upload-output"), names.index("complete"))
            self.assertEqual(
                client.completed_outputs,
                [
                    {
                        "output_id": output_declaration()["id"],
                        "checksum_sha256": hashlib.sha256(payload).hexdigest(),
                        "byte_size": len(payload),
                    }
                ],
            )
            self.assertFalse(state_path.exists())

    def test_runtime_fails_when_required_output_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            client = FakeClient(envelope(outputs=[output_declaration()]))
            engine = FakeEngine()
            runtime = RunnerRuntime(
                config(state_path), client, engine, StateStore(state_path)
            )

            self.assertTrue(runtime.run_once())

            self.assertEqual(client.calls[-1][0], "fail")
            self.assertIn("required", client.calls[-1][1].lower())
            self.assertFalse(state_path.exists())

    def test_runtime_retries_output_after_network_interruption(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            payload = b'{"rows":42}'
            client = InterruptedUploadClient(envelope(outputs=[output_declaration()]))
            engine = FakeEngine(output_payload=payload)
            runtime = RunnerRuntime(
                config(state_path), client, engine, StateStore(state_path)
            )

            self.assertTrue(runtime.run_once())
            self.assertEqual(StateStore(state_path).load().phase, "output_pending")
            self.assertNotIn("fail", [name for name, _payload in client.calls])

            self.assertTrue(runtime.run_once())
            self.assertEqual(client.calls[-1][0], "complete")
            self.assertFalse(state_path.exists())

    def test_runtime_stops_before_acknowledging_cancellation(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            client = FakeClient(envelope())
            client.cancel_on_heartbeat = True
            engine = FakeEngine(running=True)
            runtime = RunnerRuntime(
                config(state_path), client, engine, StateStore(state_path)
            )

            self.assertTrue(runtime.run_once())

            self.assertLess(engine.calls.index("stop"), engine.calls.index("cleanup"))
            self.assertEqual(client.calls[-1], ("cancelled", "operator cancelled"))
            self.assertFalse(state_path.exists())

    def test_runtime_stops_started_container_if_journal_update_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            client = FakeClient(envelope())
            engine = FakeEngine(running=True)
            runtime = RunnerRuntime(
                config(state_path), client, engine, FailRunningSaveStore(state_path)
            )

            self.assertTrue(runtime.run_once())

            self.assertIn("stop", engine.calls)
            self.assertEqual(client.calls[-1][0], "fail")
            self.assertFalse(state_path.exists())

    def test_recovery_stops_uncertain_container_before_failure_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            raw = envelope()
            state = RunnerState(
                phase="started",
                envelope=raw,
                signature=expected_job_signature(raw, TOKEN),
                lease_token=f"aicl_{'d' * 48}",
                container_name="airalogy-job-recover",
                volume_name="airalogy-work-recover",
            )
            store = StateStore(state_path)
            store.save(state)
            client = FakeClient(raw)
            engine = FakeEngine(running=True)
            runtime = RunnerRuntime(config(state_path), client, engine, store)

            self.assertTrue(runtime.recover_pending())

            self.assertLess(engine.calls.index("stop"), engine.calls.index("cleanup"))
            self.assertEqual(client.calls[-1][0], "fail")
            self.assertFalse(state_path.exists())

    def test_container_names_are_derived_not_interpolated(self):
        job_id = str(UUID("00000000-0000-0000-0000-000000000001"))
        container, volume = ContainerEngine.names(job_id)

        self.assertRegex(container, r"^airalogy-job-[0-9a-f]{24}$")
        self.assertRegex(volume, r"^airalogy-work-[0-9a-f]{24}$")

    def test_research_container_command_enforces_local_isolation_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = object.__new__(ContainerEngine)
            engine.config = config(Path(directory) / "state.json")
            engine.executable = "/usr/bin/docker"
            fake_process = FakeProcess(running=True)
            job = ComputeJobEnvelope.parse(envelope())

            with patch(
                "airalogy_compute_runner.engine.subprocess.Popen",
                return_value=fake_process,
            ) as popen:
                engine.start(job, "safe-container", "safe-volume")

            command = popen.call_args.args[0]
            self.assertIn("65532:65532", command)
            self.assertIn("--read-only", command)
            self.assertIn("no-new-privileges", command)
            self.assertIn("--cap-drop", command)
            self.assertIn("--pids-limit", command)
            self.assertIn("--memory", command)
            self.assertIn("--cpus", command)
            self.assertEqual(command[command.index("--log-driver") + 1], "none")
            self.assertEqual(command[command.index("--network") + 1], "none")
            self.assertEqual(
                command[command.index("--mount") + 1],
                "type=volume,source=safe-volume,target=/airalogy",
            )
            self.assertFalse(any("type=bind" in argument for argument in command))
            self.assertIn(job.image_ref, command)


if __name__ == "__main__":
    unittest.main()
