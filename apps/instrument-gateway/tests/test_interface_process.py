import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from airalogy_instrument_gateway.credentials import write_credentials
from airalogy_instrument_gateway.interface_process import (
    InterfaceProcessClient,
    InterfaceProcessError,
    verify_runtime,
)

PROJECT = Path(__file__).resolve().parents[3]
WORKER = """
import json, os, sys
r = json.load(sys.stdin)
assert 'NODE_OPTIONS' not in os.environ and 'AIRALOGY_GATEWAY_TOKEN' not in os.environ
assert 'DYLD_INSERT_LIBRARIES' not in os.environ and 'LD_PRELOAD' not in os.environ
print(json.dumps(dict(schema='airalogy.interface-worker-response.v1',operation=r['operation'],job_id=r['job_id'],runtime_sha256=r['runtime_sha256'],workflow_digest=r['workflow_digest'],hardware_qualified=False,data={'observed':19.75})))
"""


def pin(path):
    raw = path.read_bytes()
    return {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def prepared(root, source=WORKER):
    # Pure transport/integrity fixture, not a genuine Node or browser runtime.
    roots = [root / name for name in ("source", "dependency", "browser")]
    for path in roots:
        path.mkdir(mode=0o700)
    (roots[0] / "worker.mjs").write_text(source)
    (roots[1] / "index.js").write_text("fixed-dependency")
    (roots[2] / "browser").write_text("fixed-browser-bytes")
    (root / "package.json").write_text('{"name":"owned-transport-fixture"}')
    (root / "dependency-link").symlink_to(roots[1], target_is_directory=True)
    write_credentials(root / "workflow.json", {"sha256": "a" * 64})
    node = Path(sys.executable).resolve()
    runtime = {
        "schema": "airalogy.interface-worker-runtime.v1",
        "node": {"path": str(node), **pin(node)},
        "entry": str(roots[0] / "worker.mjs"),
        "browser": str(roots[2] / "browser"),
        "package": {"path": str(root / "package.json"), **pin(root / "package.json")},
        "trees": [
            {
                "root": str(path),
                "exclude_node_modules": False,
                "files": {item.name: pin(item) for item in path.iterdir()},
                "links": {},
            }
            for path in roots
        ],
        "resolutions": [
            {"path": str(root / "dependency-link"), "target": str(roots[1])}
        ],
        "unavailable": [
            [str(root / "optional-dependency")],
            [str(root / "earlier-dependency")],
        ],
        "workflow": {
            "path": str(root / "workflow.json"),
            "sha256": pin(root / "workflow.json")["sha256"],
            "workflow_digest": "a" * 64,
        },
        "evidence_root": str(root),
    }
    write_credentials(root / "runtime.json", runtime)
    return {
        "schema": "airalogy.interface-worker-config.v1",
        "runtime_file": str(root / "runtime.json"),
        "runtime_sha256": pin(root / "runtime.json")["sha256"],
    }


class InterfaceProcessTests(unittest.TestCase):
    def test_runtime_verification_detects_bytes_resolution_new_modules_and_permissions(
        self,
    ):
        for change in (
            lambda root: (root / "source/worker.mjs").write_text("changed"),
            lambda root: (root / "dependency/index.js").write_text("changed"),
            lambda root: (root / "browser/browser").write_text("changed"),
            lambda root: (root / "source/extra.js").write_text("unexpected"),
            lambda root: (root / "dependency/index.js").chmod(0o666),
            lambda root: (root / "workflow.json").write_text("{}"),
            lambda root: (root / "dependency-link").unlink(),
            lambda root: (root / "optional-dependency").mkdir(),
            lambda root: (root / "earlier-dependency").mkdir(),
            lambda root: (
                (root / "source/node_modules").mkdir()
                or (root / "source/node_modules/shadow.js").write_text("shadow")
            ),
        ):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                config = prepared(root)
                self.assertEqual(
                    verify_runtime(config)["workflow"]["workflow_digest"], "a" * 64
                )
                change(root)
                with self.assertRaises((ValueError, OSError)):
                    verify_runtime(config)

    @patch.dict(
        os.environ,
        {
            "AIRALOGY_GATEWAY_TOKEN": "owned-test-not-a-credential",
            "NODE_OPTIONS": "--owned-test-must-not-reach-worker",
            "DYLD_INSERT_LIBRARIES": "/owned-test-never-load.dylib",
            "LD_PRELOAD": "/owned-test-never-load.so",
        },
    )
    def test_one_shot_correlated_process_has_no_inherited_credentials_or_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            client = InterfaceProcessClient(prepared(Path(directory).resolve()))
            identifier = str(uuid4())
            self.assertEqual(client.call("probe")["data"], {"observed": 19.75})
            result = client.call("execute", job_id=identifier)
            self.assertEqual(result["job_id"], identifier)
            with self.assertRaises(InterfaceProcessError):
                client.call("execute", job_id=identifier)
            client._lock.acquire()
            try:
                with self.assertRaises(InterfaceProcessError):
                    client.call("probe")
            finally:
                client._lock.release()

    def test_output_bounds_failed_identity_and_timeouts_do_not_retry(self):
        for source in (
            "import sys;sys.stdout.write('x'*100000)",
            WORKER.replace("job_id=r['job_id']", "job_id='wrong'"),
            "import time;time.sleep(30)",
            "import subprocess,sys;subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])",
        ):
            with tempfile.TemporaryDirectory() as directory:
                client = InterfaceProcessClient(
                    prepared(Path(directory).resolve(), source)
                )
                identifier = str(uuid4())
                started = time.monotonic()
                with self.assertRaises(InterfaceProcessError) as error:
                    client.call("execute", job_id=identifier, timeout_seconds=0.5)
                self.assertTrue(error.exception.operation_may_have_started)
                self.assertLess(time.monotonic() - started, 5)
                with self.assertRaises(InterfaceProcessError):
                    client.call("execute", job_id=identifier)

    def test_cancelled_before_launch_and_invalid_operations_never_create_process(self):
        with tempfile.TemporaryDirectory() as directory:
            client = InterfaceProcessClient(prepared(Path(directory).resolve()))
            stopped = threading.Event()
            stopped.set()
            with self.assertRaises(InterfaceProcessError) as error:
                client.call("execute", job_id=str(uuid4()), stop_event=stopped)
            self.assertFalse(error.exception.operation_may_have_started)
            with self.assertRaises(ValueError):
                client.call("shell", job_id=str(uuid4()))
            with self.assertRaises(ValueError):
                client.call("probe", job_id=str(uuid4()))

    def test_cleanup_failure_closes_pipes_and_preserves_uncertainty(self):
        children = []
        popen = subprocess.Popen

        def capture(*args, **kwargs):
            child = popen(*args, **kwargs)
            children.append(child)
            return child

        with tempfile.TemporaryDirectory() as directory:
            client = InterfaceProcessClient(
                prepared(
                    Path(directory).resolve(),
                    WORKER.replace("job_id=r['job_id']", "job_id='wrong'"),
                )
            )
            identifier = str(uuid4())
            with (
                patch(
                    "airalogy_instrument_gateway.interface_process.subprocess.Popen",
                    side_effect=capture,
                ),
                patch(
                    "airalogy_instrument_gateway.interface_process._terminate",
                    side_effect=PermissionError("owned-test-cleanup-denied"),
                ),
                self.assertRaises(InterfaceProcessError) as error,
            ):
                client.call("execute", job_id=identifier)
            self.assertTrue(error.exception.operation_may_have_started)
            self.assertIn("cleanup could not be confirmed", str(error.exception))
            self.assertFalse(client._lock.locked())
            self.assertEqual(len(children), 1)
            child = children[0]
            self.assertIsNotNone(child.poll())
            self.assertTrue(
                all(
                    stream.closed
                    for stream in (child.stdin, child.stdout, child.stderr)
                )
            )
            with self.assertRaises(InterfaceProcessError):
                client.call("execute", job_id=identifier)

    @unittest.skipUnless(
        os.environ.get("RUN_INTERFACE_PROCESS_TESTS") == "1",
        "requires explicitly selected actual Node/Chromium test runtime",
    )
    def test_actual_node_browser_manifest_and_workflow_from_independent_python_client(
        self,
    ):
        result = subprocess.run(
            ["node", str(PROJECT / "scripts/instrument-interface-worker-example.mjs")],
            check=True,
            capture_output=True,
            timeout=45,
        )
        example = json.loads(result.stdout)
        client = InterfaceProcessClient.from_file(example["config_file"])
        probe = client.call("probe", timeout_seconds=4)
        self.assertTrue(probe["data"]["initial_matches"])
        self.assertEqual(
            probe["data"]["target"]["application"], "Airalogy Simulated Reader"
        )
        response = client.call("execute", job_id=str(uuid4()), timeout_seconds=20)
        self.assertEqual(response["data"]["values"], {"result.value": "0.84"})
        self.assertEqual(response["workflow_digest"], example["workflow_digest"])
        self.assertFalse(response["hardware_qualified"])


if __name__ == "__main__":
    unittest.main()
