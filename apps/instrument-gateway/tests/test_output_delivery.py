"""Disposable acquisition files and receipt faults; never hardware acceptance."""

import copy
import hashlib
import io
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4, uuid5

from airalogy_instrument_gateway import InstrumentAdapter, InstrumentResult
from airalogy_instrument_gateway.client import (
    GatewayAPIError,
    PlatformClient,
    _file_body,
)
from airalogy_instrument_gateway.models import InstrumentJobEnvelope
from airalogy_instrument_gateway.output_capture import CaptureStore
from airalogy_instrument_gateway.output_delivery import bundle, completed_result
from airalogy_instrument_gateway.runtime import GatewayHaltError, GatewayRuntime
from airalogy_instrument_gateway.state import StateStore
from test_gateway import FakeClient, config, envelope
from test_output_capture import plan, selected


def file_job():
    raw = envelope()
    raw["activation"] = {"id": str(uuid4())}
    raw["file_outputs"] = {
        "plan": {**plan(), "job_id": raw["job_id"]},
        "destination": {
            "activation_id": raw["activation"]["id"],
            "lab_id": str(uuid4()),
            "project_id": str(uuid4()),
            "task_id": raw["task_id"],
            "scope_type": "project",
            "visibility": "project",
            "asset_state": "draft",
            "record_association": "awaiting_review",
        },
    }
    return raw


class FileAdapter(InstrumentAdapter):
    def __init__(self, root):
        self.root, self.executions, self.stops = root, 0, 0
        self.transform = lambda value: value

    def supports(self, job):
        return True

    def confirm(self, job):
        return None

    def execute(self, job, stop_event):
        self.executions += 1
        raw = b"sample,signal\nsynthetic,0.84\n"
        (self.root / "export").mkdir(exist_ok=True)
        (self.root / "export/result.csv").write_bytes(raw)
        return self.transform(
            InstrumentResult(
                {"simulation_only": True},
                [{**selected()[0], "sha256": hashlib.sha256(raw).hexdigest()}],
            )
        )

    def safe_stop(self, job, reason):
        self.stops += 1


class ReceivingClient(FakeClient):
    def __init__(self, raw):
        super().__init__(raw)
        self.capture, self.registered, self.finalized = None, {}, None
        self.lose, self.mutate = None, lambda value: value
        self.on_complete = lambda: None

    def _return(self, stage, value):
        if self.lose == stage:
            self.lose = None
            raise GatewayAPIError("Synthetic lost response after receipt was stored")
        return self.mutate(copy.deepcopy(value))

    def complete(self, *args):
        super().complete(*args)
        self.on_complete()
        return self._return(
            "complete", {"status": "completed", "files_pending": self.finalized is None}
        )

    def snapshot(self):
        items = []
        captured = {item["name"]: item for item in self.capture["files"]}
        for declared in self.raw["file_outputs"]["plan"]["outputs"]:
            name = declared["name"]
            item = {
                **declared,
                "id": str(uuid5(UUID(self.raw["job_id"]), name)),
                "state": "awaiting_upload" if name in captured else "omitted",
            }
            if name in self.registered:
                item.update(self.registered[name], **captured[name], state="registered")
            items.append(item)
        return {
            "job_id": self.raw["job_id"],
            **self.raw["file_outputs"],
            "state": "delivered" if self.finalized else "awaiting_files",
            "execution_status": "completed",
            "items": items,
            "finalized_at": self.finalized,
        }

    def report_capture(self, job_id, token, capture):
        self.calls.append(("capture", capture))
        if self.capture is not None and self.capture != capture:
            raise AssertionError("Capture changed across retries")
        self.capture = copy.deepcopy(capture)
        return self._return("capture", self.snapshot())

    def upload_output(self, job_id, token, output_id, receipt, stream):
        self.calls.append(("upload", output_id))
        data = stream.read()
        assert (
            len(data) == receipt["byte_size"]
            and hashlib.sha256(data).hexdigest() == receipt["sha256"]
        )
        result = self.registered.setdefault(
            receipt["name"],
            {
                "output_id": output_id,
                "research_file_id": str(uuid4()),
                "data_asset_id": str(uuid4()),
                "data_asset_version_id": str(uuid4()),
                "sha256": receipt["sha256"],
                "byte_size": len(data),
            },
        )
        return self._return("upload", {"status": "registered", **result})

    def finalize_outputs(self, job_id, token, capture):
        self.calls.append(("finalize", capture))
        assert self.capture == capture and len(self.registered) == len(capture["files"])
        self.finalized = self.finalized or datetime.now(UTC).isoformat()
        return self._return("finalize", self.snapshot())


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir(mode=0o700)
        self.store = StateStore(self.root / "state.json")
        self.config = replace(config(self.store.path), output_root=self.source)
        self.adapter = FileAdapter(self.source)
        self.client = ReceivingClient(file_job())

    def runtime(self, *, recover=False):
        return GatewayRuntime(
            self.config, self.client, None if recover else self.adapter, self.store
        )

    def test_execution_captures_before_completion_and_delivers(self):
        def check_snapshot():
            CaptureStore(self.root / "instrument-output-outbox").inspect(
                self.client.raw["file_outputs"]["plan"]
            )
            (self.source / "export/result.csv").write_bytes(
                b"next acquisition reused filename"
            )

        self.client.on_complete = check_snapshot
        self.assertTrue(self.runtime().run_once())
        self.assertIsNone(self.store.load())
        self.assertEqual(self.adapter.executions, 1)
        self.assertEqual(self.adapter.stops, 0)
        self.assertIsNotNone(self.client.finalized)

    def test_lost_responses_recover_without_driver_or_source(self):
        for stage in ("complete", "capture", "upload", "finalize"):
            with self.subTest(stage=stage):
                self.setUp()
                self.client.lose = stage
                with self.assertRaises(GatewayAPIError):
                    self.runtime().run_once()
                self.assertIsNotNone(self.store.load())
                (self.source / "export/result.csv").unlink()
                (self.source / "export").rmdir()
                self.source.rmdir()
                self.runtime(recover=True).recover_pending()
                self.assertIsNone(self.store.load())
                self.assertEqual(self.adapter.executions, 1)
                self.assertEqual(self.adapter.stops, 0)
                self.assertEqual(
                    len([call for call in self.client.calls if call[0] == "upload"]), 1
                )

    def test_invalid_completion_is_retained_without_physical_retry(self):
        for transform in (
            lambda value: value.result,
            lambda value: InstrumentResult(
                value.result, [{**value.files[0], "sha256": "bad"}]
            ),
            lambda value: InstrumentResult(
                value.result, [{**value.files[0], "path": "../private"}]
            ),
            lambda value: InstrumentResult({"bad": float("nan")}, value.files),
            lambda value: object(),
        ):
            with self.subTest(transform=transform):
                self.setUp()
                self.adapter.transform = transform
                with self.assertRaises(GatewayHaltError):
                    self.runtime().run_once()
                self.assertEqual(self.store.load().phase, "completion_unresolved")
                with self.assertRaises(GatewayHaltError):
                    self.runtime(recover=True).recover_pending()
                self.assertEqual((self.adapter.executions, self.adapter.stops), (1, 0))
                self.assertFalse(
                    any(call[0] == "complete" for call in self.client.calls)
                )

    def test_changed_source_is_never_repinned_after_capture_failure(self):
        with (
            patch.object(
                CaptureStore, "prepare", side_effect=OSError("Synthetic full disk")
            ),
            self.assertRaises(OSError),
        ):
            self.runtime().run_once()
        self.assertEqual(self.store.load().phase, "completion_pending")
        (self.source / "export/result.csv").write_bytes(b"different run")
        with self.assertRaisesRegex(ValueError, "acquisition bytes changed"):
            self.runtime(recover=True).recover_pending()
        self.assertEqual(self.adapter.executions, 1)
        self.assertFalse(any(call[0] == "complete" for call in self.client.calls))

    def test_wrong_receipt_does_not_clear_journal(self):
        mutations = (
            lambda s: s.update(
                destination={**s["destination"], "project_id": str(uuid4())}
            ),
            lambda s: s["items"][0].update(id=str(uuid4())),
            lambda s: s["items"][0].update(required=False),
            lambda s: s["items"][0].update(required=1),
            lambda s: s.update(items=s["items"] * 2),
            lambda s: s.update(execution_status="running"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.setUp()

                def mutate(value, mutation=mutation):
                    if "items" in value:
                        mutation(value)
                    return value

                self.client.mutate = mutate
                with self.assertRaises(ValueError):
                    self.runtime().run_once()
                self.assertEqual(self.store.load().phase, "outputs_pending")
                self.assertEqual(self.adapter.executions, 1)

    def test_registered_digest_or_identity_cannot_change_on_retry(self):
        for key, value in (
            ("research_file_id", str(uuid4())),
            ("sha256", "f" * 64),
            ("data_asset_id", "not-uuid"),
        ):
            with self.subTest(key=key):
                self.setUp()
                self.client.lose = "finalize"
                with self.assertRaises(GatewayAPIError):
                    self.runtime().run_once()

                def mutate(response, key=key, value=value):
                    if "items" in response:
                        response["items"][0][key] = value
                    return response

                self.client.mutate = mutate
                with self.assertRaises(ValueError):
                    self.runtime(recover=True).recover_pending()
                self.assertIsNotNone(self.store.load())

    def test_no_root_fails_before_acquisition(self):
        self.config = replace(self.config, output_root=None)
        self.runtime().run_once()
        self.assertEqual(self.adapter.executions, 0)
        self.assertTrue(self.client.failure_confirmations[-1])

    def test_source_outbox_overlap_fails_before_acquisition(self):
        self.config = replace(self.config, output_root=self.root)
        self.runtime().run_once()
        self.assertEqual(self.adapter.executions, 0)

    def test_capture_control_loss_never_repeats_acquisition(self):
        self.client.heartbeats = [{"stop_requested": True}]
        controller = self.runtime()
        with self.assertRaises(GatewayHaltError):
            controller.run_once()
        self.assertEqual(self.store.load().phase, "completion_pending")
        with self.assertRaises(GatewayHaltError):
            controller.recover_pending()
        controller._capture_worker.join(5)
        self.assertFalse(controller._capture_worker.is_alive())
        self.assertEqual((self.adapter.executions, self.adapter.stops), (1, 0))
        self.assertFalse(any(call[0] == "complete" for call in self.client.calls))

    def test_capture_heartbeat_and_manifest_survive_completion_response_loss(self):
        self.client.lose = "complete"
        with self.assertRaises(GatewayAPIError):
            self.runtime().run_once()
        self.assertTrue(any(call[0] == "heartbeat" for call in self.client.calls))
        self.assertIsNotNone(self.store.load().metadata["output_capture_digest"])
        self.client.heartbeat_error = GatewayAPIError("Already completed")
        self.runtime(recover=True).recover_pending()
        self.assertIsNone(self.store.load())

    def test_capture_preparation_retains_original_expected_hashes(self):
        result = self.adapter.execute(
            InstrumentJobEnvelope.parse(self.client.raw), threading.Event()
        )
        store = CaptureStore(self.root / "instrument-output-outbox")
        approved = self.client.raw["file_outputs"]["plan"]
        hashes = {"result.csv": result.files[0]["sha256"]}
        store.prepare(approved, self.source, selected(), expected_hashes=hashes)
        with self.assertRaises(ValueError):
            store.prepare(
                approved,
                self.source,
                selected(),
                expected_hashes=hashes,
                expected_root_identity=[0, 0],
            )
        fresh = CaptureStore(self.root / "different-outbox")
        with self.assertRaises(ValueError):
            fresh.prepare(
                approved,
                self.source,
                selected(),
                expected_hashes=hashes,
                expected_root_identity=[0, 0],
            )
        with self.assertRaises(ValueError):
            store.prepare(
                approved,
                self.source,
                selected(),
                expected_hashes={"result.csv": "f" * 64},
            )
        with self.assertRaises(ValueError):
            store.prepare(approved, self.source, selected(), expected_hashes={})

    def test_no_file_authority_cannot_select_files(self):
        job = InstrumentJobEnvelope.parse(envelope())
        with self.assertRaises(ValueError):
            completed_result(job, InstrumentResult({}, selected()))

    def test_scope_and_optional_omission_contracts(self):
        for key in ("activation_id", "task_id", "visibility", "record_association"):
            raw = file_job()
            raw["file_outputs"]["destination"][key] = "changed"
            with self.assertRaises(ValueError):
                bundle(InstrumentJobEnvelope.parse(raw))
        self.client.raw["file_outputs"]["plan"]["outputs"][0]["required"] = False
        self.adapter.transform = lambda value: InstrumentResult(value.result, [])
        self.runtime().run_once()
        self.assertIsNone(self.store.load())
        self.assertFalse(self.client.registered)


class UploadHTTPTests(unittest.TestCase):
    def test_real_fixed_length_binary_transport_and_no_redirect(self):
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_PUT(self):
                content = self.rfile.read(int(self.headers["Content-Length"]))
                calls.append((self.path, dict(self.headers), content))
                self.send_response(302 if len(calls) > 1 else 200)
                self.send_header("Location", "/must-not-follow")
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        client = PlatformClient(
            f"http://127.0.0.1:{server.server_port}",
            "aigw_" + "a" * 48,
            file_delivery_enabled=True,
        )
        raw = b"x" * 200000
        receipt = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "byte_size": len(raw),
            "media_type": "text/csv",
        }
        job, output = str(uuid4()), str(uuid4())
        client.upload_output(job, "aijl_original", output, receipt, io.BytesIO(raw))
        self.assertEqual(calls[0][2], raw)
        headers = {key.lower(): value for key, value in calls[0][1].items()}
        self.assertEqual(headers["content-length"], str(len(raw)))
        self.assertEqual(headers["x-airalogy-content-sha256"], receipt["sha256"])
        self.assertEqual(headers["x-airalogy-instrument-lease"], "aijl_original")
        self.assertNotIn("transfer-encoding", headers)
        with self.assertRaises(GatewayAPIError):
            client.upload_output(job, "aijl_original", output, receipt, io.BytesIO(raw))
        self.assertEqual(len(calls), 2)
        with self.assertRaises(ValueError):
            client.upload_output(
                "../redirect", "lease", output, receipt, io.BytesIO(raw)
            )
        for content, size, checksum in (
            (b"long", 3, "f" * 64),
            (b"short", 6, "f" * 64),
            (b"same", 4, "f" * 64),
        ):
            with self.assertRaises(ValueError):
                list(_file_body(io.BytesIO(content), size, checksum))


if __name__ == "__main__":
    unittest.main()
