from __future__ import annotations

import hashlib
import io
import stat
import tempfile
import unittest
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID

from airalogy_compute_runner.client import PlatformClient, RunnerAPIError
from airalogy_compute_runner.config import RunnerConfig
from airalogy_compute_runner.engine import ContainerEngine, JobProcess, OutputProcess
from airalogy_compute_runner.models import (
    ANALYSIS_JOB_SCHEMA,
    RESEARCH_JOB_SCHEMA,
    SUPPORTED_JOB_SCHEMAS,
    ComputeJobEnvelope,
)
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


def analysis_envelope(**kwargs: Any) -> dict[str, Any]:
    raw = envelope(**kwargs)
    raw["schema"] = ANALYSIS_JOB_SCHEMA
    for key in ("action_id", "task_id", "run_id"):
        raw.pop(key)
    raw["context"] = {
        "kind": "analysis",
        "analysis_id": "00000000-0000-0000-0000-000000000009",
        "project_id": "00000000-0000-0000-0000-000000000010",
        "lab_id": "00000000-0000-0000-0000-000000000011",
    }
    return raw


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
    def test_status_explicitly_advertises_supported_job_schemas(self):
        client = object.__new__(PlatformClient)
        with patch.object(client, "_request", return_value={}) as request:
            client.report_status("podman", active=False)
        payload = request.call_args.kwargs["payload"]
        self.assertEqual(payload["job_schemas"], list(SUPPORTED_JOB_SCHEMAS))
        self.assertEqual(
            payload["job_schemas"], [RESEARCH_JOB_SCHEMA, ANALYSIS_JOB_SCHEMA]
        )
        self.assertEqual(payload["protocol_version"], "airalogy.compute-runner.v1")
        self.assertTrue(all(payload["security"].values()))

    def test_analysis_context_is_explicit_without_fake_research_identifiers(self):
        raw = analysis_envelope()
        parsed = ComputeJobEnvelope.parse(raw)
        self.assertIsNone(parsed.action_id)
        self.assertIsNone(parsed.task_id)
        self.assertIsNone(parsed.run_id)
        for key in ("analysis_id", "project_id", "lab_id"):
            self.assertEqual(getattr(parsed, key), raw["context"][key])
        legacy = ComputeJobEnvelope.parse(envelope())
        self.assertIsNotNone(legacy.task_id)
        self.assertIsNone(legacy.analysis_id)
        self.assertIsNone(legacy.project_id)
        self.assertIsNone(legacy.lab_id)

    def test_analysis_context_rejects_missing_mixed_or_ambiguous_identifiers(self):
        invalid = []
        for key in ("analysis_id", "project_id", "lab_id"):
            raw = analysis_envelope()
            raw["context"][key] = "not-a-uuid"
            invalid.append(raw)
            raw = analysis_envelope()
            del raw["context"][key]
            invalid.append(raw)
            raw = analysis_envelope()
            raw[key] = raw["context"][key]
            invalid.append(raw)
        for key in ("action_id", "task_id", "run_id"):
            for value in (None, envelope()[key]):
                raw = analysis_envelope()
                raw[key] = value
                invalid.append(raw)
        for change in ({"kind": "research"}, {"unexpected": True}, {"task_id": None}):
            raw = analysis_envelope()
            raw["context"].update(change)
            invalid.append(raw)
        raw = analysis_envelope()
        raw.pop("context")
        invalid.append(raw)
        raw = envelope()
        raw["context"] = analysis_envelope()["context"]
        invalid.append(raw)
        for index, raw in enumerate(invalid):
            with self.subTest(case=index), self.assertRaises((ValueError, TypeError)):
                ComputeJobEnvelope.parse(raw)

    def test_both_schemas_preserve_the_same_execution_validation(self):
        changes = [
            (("source", "code"), "print('changed')"),
            (("environment", "image_ref"), "python:latest"),
            (("environment", "language"), "shell"),
            (("environment", "network_policy"), "host"),
            (("environment", "allowed_egress_hosts"), ["example.org"]),
            (("environment", "resource_limits", "memory_mb"), True),
            (("environment", "resource_limits", "timeout_seconds"), 0),
            (("environment", "resource_limits", "max_output_bytes"), 1),
            (
                ("lease_expires_at",),
                (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            ),
        ]
        for factory in (envelope, analysis_envelope):
            for path, value in changes:
                raw = factory()
                target = raw
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with (
                    self.subTest(schema=raw["schema"], path=path),
                    self.assertRaises((ValueError, TypeError)),
                ):
                    ComputeJobEnvelope.parse(raw)
            output = output_declaration()
            output["upload_path"] += "/../escape"
            with self.assertRaisesRegex(ValueError, "does not match"):
                ComputeJobEnvelope.parse(factory(outputs=[output]))
            input_id = "00000000-0000-0000-0000-000000000012"
            with self.assertRaisesRegex(ValueError, "does not match"):
                ComputeJobEnvelope.parse(
                    factory(
                        inputs=[
                            {
                                "id": input_id,
                                "mount_name": "records.json",
                                "download_path": f"/compute-runner/v1/jobs/{input_id}/inputs/{input_id}",
                                "checksum_sha256": "a" * 64,
                                "byte_size": 3,
                            }
                        ]
                    )
                )

    def test_analysis_signature_binds_context_and_rejects_unsigned_unknown_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = analysis_envelope()
            runtime = RunnerRuntime(
                config(Path(directory) / "state.json"),
                FakeClient(raw),
                FakeEngine(),
                StateStore(Path(directory) / "state.json"),
            )
            signature = expected_job_signature(raw, TOKEN)
            self.assertEqual(runtime._verified_job(raw, signature).raw, raw)
            for key in ("analysis_id", "project_id", "lab_id"):
                tampered = deepcopy(raw)
                tampered["context"][key] = envelope()["job_id"]
                with self.assertRaisesRegex(ValueError, "signature"):
                    runtime._verified_job(tampered, signature)
            for factory in (envelope, analysis_envelope):
                with self.assertRaisesRegex(ValueError, "signature"):
                    runtime._verified_job(factory(), "")
                for schema in (None, "airalogy.compute-job.analysis.v2", "unsigned"):
                    unknown = factory()
                    unknown["schema"] = schema
                    with self.assertRaisesRegex(ValueError, "schema"):
                        runtime._verified_job(
                            unknown, expected_job_signature(unknown, TOKEN)
                        )
            expired = analysis_envelope()
            expired["issued_at"] = (
                datetime.now(UTC) - timedelta(minutes=3)
            ).isoformat()
            expired["lease_expires_at"] = (
                datetime.now(UTC) - timedelta(minutes=1)
            ).isoformat()
            with self.assertRaisesRegex(ValueError, "expired"):
                runtime._verified_job(expired, expected_job_signature(expired, TOKEN))

    def test_analysis_downloads_private_input_and_recovers_output_without_rerunning(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            input_id = "00000000-0000-0000-0000-000000000012"
            raw = analysis_envelope(
                inputs=[
                    {
                        "id": input_id,
                        "mount_name": "records.json",
                        "download_path": f"/compute-runner/v1/jobs/{envelope()['job_id']}/inputs/{input_id}",
                        "checksum_sha256": hashlib.sha256(b"xxx").hexdigest(),
                        "byte_size": 3,
                    }
                ],
                outputs=[output_declaration()],
            )
            client = InterruptedUploadClient(raw)
            engine = FakeEngine(output_payload=b'{"value":42}')
            runtime = RunnerRuntime(
                config(state_path), client, engine, StateStore(state_path)
            )
            self.assertTrue(runtime.run_once())
            saved = StateStore(state_path).load()
            self.assertEqual(saved.phase, "output_pending")
            self.assertEqual(saved.envelope["context"], raw["context"])
            self.assertEqual(stat.S_IMODE(state_path.stat().st_mode), 0o600)
            verify_job_signature(saved.envelope, saved.signature, TOKEN)
            self.assertTrue(runtime.run_once())
            self.assertEqual(engine.calls.count("start"), 1)
            self.assertEqual([name for name, _ in client.calls].count("lease"), 1)
            self.assertEqual([name for name, _ in client.calls].count("download"), 1)
            self.assertEqual(client.calls[-1], ("complete", {"value": 42}))
            self.assertFalse(state_path.exists())

    def test_analysis_recovery_refuses_tampered_state_before_callbacks(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            raw = analysis_envelope()
            signature = expected_job_signature(raw, TOKEN)
            raw["context"]["analysis_id"] = envelope()["job_id"]
            store = StateStore(state_path)
            store.save(
                RunnerState(
                    phase="completion_pending",
                    envelope=raw,
                    signature=signature,
                    lease_token=f"aicl_{'d' * 48}",
                    result={"value": 42},
                )
            )
            client, engine = FakeClient(raw), FakeEngine()
            runtime = RunnerRuntime(config(state_path), client, engine, store)
            with self.assertRaisesRegex(ValueError, "signature"):
                runtime.recover_pending()
            self.assertEqual(client.calls, [])
            self.assertEqual(engine.calls, [])
            self.assertTrue(state_path.exists())

    def test_recovery_refuses_correctly_signed_unknown_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            raw = analysis_envelope()
            raw["schema"] = "airalogy.compute-job.analysis.v2"
            store = StateStore(path)
            store.save(
                RunnerState(
                    phase="completion_pending",
                    envelope=raw,
                    signature=expected_job_signature(raw, TOKEN),
                    lease_token=f"aicl_{'d' * 48}",
                    result={"value": 42},
                )
            )
            client, engine = FakeClient(raw), FakeEngine()
            runtime = RunnerRuntime(config(path), client, engine, store)
            with self.assertRaisesRegex(ValueError, "schema"):
                runtime.recover_pending()
            self.assertEqual(client.calls, [])
            self.assertEqual(engine.calls, [])

    def test_analysis_recovery_never_reexecutes_uncertain_container(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            raw = analysis_envelope()
            store = StateStore(path)
            store.save(
                RunnerState(
                    phase="started",
                    envelope=raw,
                    signature=expected_job_signature(raw, TOKEN),
                    lease_token=f"aicl_{'d' * 48}",
                    container_name="analysis-recover",
                    volume_name="analysis-volume",
                )
            )
            client, engine = FakeClient(raw), FakeEngine(running=True)
            runtime = RunnerRuntime(config(path), client, engine, store)
            self.assertTrue(runtime.recover_pending())
            self.assertEqual(engine.calls, ["stop", "cleanup"])
            self.assertEqual([name for name, _ in client.calls], ["fail"])
            self.assertFalse(path.exists())

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
        self.assert_container_isolation(envelope())

    def test_analysis_container_command_enforces_local_isolation_contract(self):
        self.assert_container_isolation(analysis_envelope())

    def assert_container_isolation(self, raw):
        with tempfile.TemporaryDirectory() as directory:
            engine = object.__new__(ContainerEngine)
            engine.config = config(Path(directory) / "state.json")
            engine.executable = "/usr/bin/docker"
            fake_process = FakeProcess(running=True)
            job = ComputeJobEnvelope.parse(raw)

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


class WorkspaceSetupRecoveryTests(unittest.TestCase):
    def test_setup_failure_has_journaled_exact_cleanup_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner_config = config(Path(temporary) / "state.json")
            journal = StateStore(runner_config.state_file)
            expected = ContainerEngine.names(analysis_envelope()["job_id"])

            class FailingWorkspace(FakeEngine):
                cleaned_names = None

                def create_workspace(self, job):
                    saved = journal.load()
                    if (
                        saved is None
                        or (saved.container_name, saved.volume_name) != expected
                    ):
                        raise AssertionError(
                            "cleanup identities must precede workspace creation"
                        )
                    raise OSError("synthetic helper startup failure")

                def cleanup(self, container_name, volume_name):
                    self.cleaned_names = (container_name, volume_name)
                    super().cleanup(container_name, volume_name)

            engine = FailingWorkspace()
            runtime = RunnerRuntime(
                runner_config,
                client=FakeClient(analysis_envelope()),
                engine=engine,
                state_store=journal,
            )
            self.assertTrue(runtime.run_once())
            self.assertEqual(engine.cleaned_names, expected)
            self.assertIsNone(journal.load())


if __name__ == "__main__":
    unittest.main()
