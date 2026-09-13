"""Opt-in real OCI isolation check; no Platform, customer data or model calls.

Set COMPUTE_ENGINE_TEST=1 and pin COMPUTE_TEST_IMAGE / COMPUTE_TEST_HELPER_IMAGE
to locally installed, reviewed image@sha256 references. Only the fresh test
job's own container and tmpfs volume are removed by its finally block.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from airalogy_compute_runner.config import RunnerConfig
from airalogy_compute_runner.engine import ContainerEngine
from airalogy_compute_runner.models import ComputeJobEnvelope
from airalogy_compute_runner.security import (
    expected_job_signature,
    verify_job_signature,
)


@unittest.skipUnless(
    os.environ.get("COMPUTE_ENGINE_TEST") == "1", "Opt-in real container test"
)
class RealContainerAnalysisTest(unittest.TestCase):
    def test_private_analysis_stages_exact_input_and_returns_bounded_output(self):
        job_id, input_id, output_id = (str(uuid4()) for _ in range(3))
        source = """import json, os
from pathlib import Path
assert os.getuid() == 65532
try:
    Path('/must-not-write-root').write_text('unsafe')
except OSError:
    pass
else:
    raise RuntimeError('root filesystem is writable')
snapshot = json.loads((Path(os.environ['AIRALOGY_INPUT_DIR']) / 'records.json').read_text())
try:
    (Path(os.environ['AIRALOGY_INPUT_DIR']) / 'records.json').chmod(0o600)
except PermissionError:
    pass
else:
    raise RuntimeError('job can change immutable input ownership or mode')
values = [record['data']['measurement'] for record in snapshot['records']]
result = {'mean': sum(values) / len(values), 'count': len(values), 'uid': os.getuid()}
Path(os.environ['AIRALOGY_RESULT_JSON']).write_text(json.dumps(result))
Path('/airalogy/output/files/summary.json').write_text(json.dumps(result))
"""
        data = json.dumps(
            {"records": [{"data": {"measurement": number}} for number in (2, 4, 6, 8)]}
        ).encode()
        now = datetime.now(UTC)
        token = "aicr_" + "synthetic-only-credential-" * 3
        raw = {
            "schema": "airalogy.compute-job.analysis.v1",
            "job_id": job_id,
            "context": {
                "kind": "analysis",
                "analysis_id": str(uuid4()),
                "project_id": str(uuid4()),
                "lab_id": str(uuid4()),
            },
            "issued_at": now.isoformat(),
            "lease_expires_at": (now + timedelta(minutes=5)).isoformat(),
            "environment": {
                "id": str(uuid4()),
                "revision_id": str(uuid4()),
                "revision": 1,
                "image_ref": os.environ["COMPUTE_TEST_IMAGE"],
                "runtime_version": "python-3.13",
                "language": "python",
                "resource_limits": {
                    "cpu_millis": 1000,
                    "memory_mb": 256,
                    "gpu_count": 0,
                    "timeout_seconds": 60,
                    "max_output_bytes": 65536,
                },
                "network_policy": "none",
                "allowed_egress_hosts": [],
            },
            "source": {
                "code": source,
                "sha256": hashlib.sha256(source.encode()).hexdigest(),
            },
            "input_payload": {},
            "result_schema": {"type": "object"},
            "inputs": [
                {
                    "id": input_id,
                    "mount_name": "records.json",
                    "media_type": "application/json",
                    "byte_size": len(data),
                    "checksum_sha256": hashlib.sha256(data).hexdigest(),
                    "download_path": f"/compute-runner/v1/jobs/{job_id}/inputs/{input_id}",
                }
            ],
            "outputs": [
                {
                    "id": output_id,
                    "mount_name": "summary.json",
                    "asset_name": "Synthetic result",
                    "kind": "file",
                    "description": "Synthetic test",
                    "data_schema": {},
                    "metadata": {},
                    "media_type": "application/json",
                    "max_bytes": 4096,
                    "required": True,
                    "upload_path": f"/compute-runner/v1/jobs/{job_id}/outputs/{output_id}",
                }
            ],
        }
        verify_job_signature(raw, expected_job_signature(raw, token), token)
        job = ComputeJobEnvelope.parse(raw)
        with tempfile.TemporaryDirectory(prefix="airalogy-compute-test-") as temporary:
            root = Path(temporary)
            source_file = root / "records.json"
            source_file.write_bytes(data)
            config = RunnerConfig(
                platform_url="http://127.0.0.1:4000",
                runner_token=token,
                state_file=root / "state.json",
                backend=os.environ.get("COMPUTE_TEST_BACKEND", "docker"),
                helper_image=os.environ["COMPUTE_TEST_HELPER_IMAGE"],
                egress_networks={},
                poll_interval_seconds=1,
                heartbeat_interval_seconds=1,
                request_timeout_seconds=5,
                stop_timeout_seconds=1,
                max_workspace_bytes=64 * 1024 * 1024,
            )
            engine = ContainerEngine(config)
            container_name, volume_name = engine.names(job_id)
            try:
                engine.verify()
                engine.create_workspace(job)
                engine.populate_workspace(job, volume_name, {input_id: source_file})
                process = engine.start(job, container_name, volume_name)
                self.assertEqual(process.process.wait(timeout=60), 0)
                result, size = engine.read_result(job, volume_name)
                self.assertEqual(result, {"mean": 5.0, "count": 4, "uid": 65532})
                self.assertLess(size, job.max_output_bytes)
                output = job.outputs[0]
                output_size, digest = engine.output_metadata(output, volume_name)
                stream = engine.open_output(output, volume_name)
                payload = stream.stream.read(4097)
                engine.finish_output(stream)
                self.assertEqual(output_size, len(payload))
                self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
                self.assertEqual(json.loads(payload), result)
            finally:
                engine.cleanup(container_name, volume_name)
