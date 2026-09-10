import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from test_interface_process import WORKER, pin, prepared

from airalogy_instrument_gateway.credentials import write_credentials
from airalogy_instrument_gateway.interface_process import (
    InterfaceProcessClient,
    InterfaceProcessError,
    NativeReadProcessClient,
    verify_native_read_runtime,
)
from airalogy_instrument_gateway.package_contract import canonical


def native_fixture(root):
    # Pure IPC fixture, NOT a macOS helper, AX capture or hardware acceptance.
    config = prepared(
        root,
        WORKER.replace("interface-worker", "native-read-worker").replace(
            "workflow_digest", "definition_digest"
        ),
    )
    path = root / "runtime.json"
    runtime = json.loads(path.read_bytes())
    runtime["schema"] = "airalogy.native-read-worker-runtime.v1"
    (root / "source/worker.mjs").rename(root / "source/native-read-worker.mjs")
    runtime["entry"] = str(root / "source/native-read-worker.mjs")
    tree = runtime["trees"][0]
    tree["files"] = {"native-read-worker.mjs": pin(Path(runtime["entry"]))}
    helper = root / "browser"
    (helper / "browser").rename(helper / "helper")
    (helper / "main.swift").write_text("owned inert fixture")
    (helper / "native-build.json").write_text("{}")
    runtime["trees"][-1]["files"] = {file.name: pin(file) for file in helper.iterdir()}
    runtime.pop("browser")
    runtime["native_build"] = str(helper / "native-build.json")
    document = {
        "schema": "airalogy.native-read-definition.v1",
        "selection": {"build_file": runtime["native_build"]},
    }
    write_credentials(root / "definition.json", document)
    runtime.pop("workflow")
    runtime["definition"] = {
        "path": str(root / "definition.json"),
        "sha256": pin(root / "definition.json")["sha256"],
        "definition_digest": hashlib.sha256(canonical(document)).hexdigest(),
    }
    path.write_text(json.dumps(runtime))
    config["schema"] = "airalogy.native-read-worker-config.v1"
    config["runtime_sha256"] = pin(path)["sha256"]
    return config


class NativeReadProcessTests(unittest.TestCase):
    @patch("airalogy_instrument_gateway.interface_process.sys.platform", "darwin")
    def test_native_schema_correlation_and_browser_scope_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config = native_fixture(root)
            runtime = verify_native_read_runtime(config)
            self.assertIn("definition", runtime)
            client = NativeReadProcessClient(config)
            self.assertEqual(client.call("probe")["data"], {"observed": 19.75})
            identifier = str(uuid4())
            response = client.call("execute", job_id=identifier)
            self.assertEqual(response["job_id"], identifier)
            self.assertEqual(
                response["definition_digest"],
                runtime["definition"]["definition_digest"],
            )
            with self.assertRaises(InterfaceProcessError):
                client.call("execute", job_id=identifier)
            with self.assertRaises(InterfaceProcessError):
                InterfaceProcessClient(config).call("probe")

    @patch("airalogy_instrument_gateway.interface_process.sys.platform", "darwin")
    def test_helper_definition_and_manifest_drift_refuse_before_launch(self):
        for changed in (
            "browser/helper",
            "browser/main.swift",
            "browser/native-build.json",
            "definition.json",
        ):
            with (
                self.subTest(changed=changed),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory).resolve()
                config = native_fixture(root)
                (root / changed).write_text("changed")
                with self.assertRaises(InterfaceProcessError) as error:
                    NativeReadProcessClient(config).call("execute", job_id=str(uuid4()))
                self.assertFalse(error.exception.operation_may_have_started)

    def test_other_operating_systems_and_browser_configs_cannot_select_native(self):
        with tempfile.TemporaryDirectory() as directory:
            config = prepared(Path(directory).resolve())
            with (
                patch(
                    "airalogy_instrument_gateway.interface_process.sys.platform",
                    "darwin",
                ),
                self.assertRaises(InterfaceProcessError),
            ):
                NativeReadProcessClient(config).call("probe")
        with tempfile.TemporaryDirectory() as directory:
            config = native_fixture(Path(directory).resolve())
            with (
                patch(
                    "airalogy_instrument_gateway.interface_process.sys.platform",
                    "linux",
                ),
                self.assertRaises(InterfaceProcessError),
            ):
                NativeReadProcessClient(config).call("probe")


if __name__ == "__main__":
    unittest.main()
