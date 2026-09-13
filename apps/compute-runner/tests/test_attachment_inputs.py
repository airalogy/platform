"""The existing analysis.v1 transport safely stages multiple explicit inputs."""

import hashlib
import io
import tarfile
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from airalogy_compute_runner.engine import ContainerEngine
from airalogy_compute_runner.models import ComputeJobEnvelope
from airalogy_compute_runner.runtime import RunnerRuntime
from airalogy_compute_runner.security import (
    expected_job_signature,
    verify_job_signature,
)
from airalogy_compute_runner.state import StateStore
from test_runner import TOKEN, FakeClient, FakeEngine, analysis_envelope, config


def attachment_envelope():
    payloads = (b'{"records":[]}', b'{"files":[]}', b"value\n11\n17\n")
    names = ("records.json", "attachments.json", "measurement_record_v1.csv")
    inputs = []
    raw = analysis_envelope()
    for name, payload in zip(names, payloads, strict=True):
        identity = str(uuid4())
        inputs.append(
            {
                "id": identity,
                "mount_name": name,
                "filename": name,
                "media_type": "text/csv"
                if name.endswith("csv")
                else "application/json",
                "byte_size": len(payload),
                "checksum_sha256": hashlib.sha256(payload).hexdigest(),
                "download_path": f"/compute-runner/v1/jobs/{raw['job_id']}/inputs/{identity}",
            }
        )
    raw["inputs"] = inputs
    return raw, dict(zip((item["id"] for item in inputs), payloads, strict=True))


class AttachmentInputTests(unittest.TestCase):
    def test_multi_input_analysis_uses_existing_signature_and_workspace_bound(self):
        raw, payloads = attachment_envelope()
        verify_job_signature(raw, expected_job_signature(raw, TOKEN), TOKEN)
        job = ComputeJobEnvelope.parse(raw)
        empty = ComputeJobEnvelope.parse(analysis_envelope())
        self.assertEqual(
            job.workspace_bytes - empty.workspace_bytes,
            sum(map(len, payloads.values())),
        )
        self.assertEqual(len(job.inputs), 3)
        modified = deepcopy(raw)
        modified["inputs"][2]["checksum_sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            verify_job_signature(modified, expected_job_signature(raw, TOKEN), TOKEN)

    def test_attachment_mount_cannot_replace_parameters_or_escape_directory(self):
        for name in (
            "input.json",
            "../outside.csv",
            "/tmp/outside.csv",
            "records.json",
        ):
            with self.subTest(name=name):
                raw, _ = attachment_envelope()
                raw["inputs"][2]["mount_name"] = name
                with self.assertRaises(ValueError):
                    ComputeJobEnvelope.parse(raw)

    def test_all_downloads_use_exact_size_and_hash_before_staging(self):
        raw, payloads = attachment_envelope()
        job = ComputeJobEnvelope.parse(raw)

        class Client(FakeClient):
            corrupt = False

            def download_input(self, path, lease_token, destination, *, expected_size):
                payload = payloads[path.rsplit("/", 1)[-1]]
                self.assertions.append((expected_size, len(payload)))
                destination.write_bytes(
                    b"x" * len(payload) if self.corrupt else payload
                )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            client = Client(raw)
            client.assertions = []
            runner = RunnerRuntime(
                config(root / "state.json"),
                client,
                FakeEngine(),
                StateStore(root / "state.json"),
            )
            paths = runner._download_inputs(job, "lease", root)
            self.assertEqual(
                {identity: path.read_bytes() for identity, path in paths.items()},
                payloads,
            )
            self.assertTrue(
                all(expected == actual for expected, actual in client.assertions)
            )
            client.corrupt = True
            with self.assertRaisesRegex(ValueError, "checksum"):
                runner._download_inputs(job, "lease", root)

    def test_staged_attachment_bytes_and_parent_directory_are_root_owned_readonly(self):
        raw, payloads = attachment_envelope()
        job = ComputeJobEnvelope.parse(raw)

        class Pipe(io.BytesIO):
            def close(self):
                self.saved = self.getvalue()
                super().close()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = {}
            for identity, payload in payloads.items():
                files[identity] = root / identity
                files[identity].write_bytes(payload)
            pipe = Pipe()
            process = SimpleNamespace(
                stdin=pipe, returncode=0, communicate=lambda **kwargs: (b"", b"")
            )
            engine = object.__new__(ContainerEngine)
            engine.config = config(root / "state.json")
            engine.executable = "/usr/bin/docker"
            with patch(
                "airalogy_compute_runner.engine.subprocess.Popen", return_value=process
            ):
                engine.populate_workspace(job, "safe-volume", files)
            with tarfile.open(fileobj=io.BytesIO(pipe.saved)) as archive:
                directory = archive.getmember("input")
                self.assertEqual(
                    (directory.uid, directory.gid, directory.mode), (0, 0, 0o555)
                )
                for item in job.inputs:
                    member = archive.getmember(f"input/{item.mount_name}")
                    self.assertEqual(
                        (member.uid, member.gid, member.mode), (0, 0, 0o444)
                    )
                    self.assertEqual(
                        archive.extractfile(member).read(), payloads[item.id]
                    )


if __name__ == "__main__":
    unittest.main()
