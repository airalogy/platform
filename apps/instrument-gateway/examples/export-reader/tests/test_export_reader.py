"""Independent fixed tests, including actual owned local files; no instrument."""

import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from export_reader import create_adapter

from airalogy_instrument_gateway.export_read import ExportReadCancelled
from airalogy_instrument_gateway.output_capture import source_root_identity


class ExportContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        source = self.root / "inbox"
        source.mkdir(mode=0o700)
        self.config = self.root / "config.json"
        self.config.write_text(
            json.dumps(
                {
                    "schema": "airalogy.export-read-config.v1",
                    "root": str(source),
                    "root_identity": source_root_identity(source),
                }
            )
        )
        self.config.chmod(0o600)
        self.adapter = create_adapter(self.config)
        export_id = str(uuid4())
        self.directory = source / export_id
        self.directory.mkdir(mode=0o700)
        raw = b"sample,signal\nindependent-A,4.75\n"
        self.raw = raw
        (self.directory / "result.csv").write_bytes(raw)
        self.manifest = {
            "schema": "airalogy.export-completion.v1",
            "export_id": export_id,
            "sample_reference": "independent-A",
            "export_complete": True,
            "completed_at": "2026-09-11T08:09:10-04:00",
            "files": [
                {
                    "name": "result.csv",
                    "byte_size": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "captured_at": "2026-09-11T08:09:00-04:00",
                    "original_units": ["signal: independent_fixture_unit"],
                    "conversion_rules": [],
                    "completion_reference": "Independent closed-file fixture, no physical equipment",
                }
            ],
        }
        (self.directory / "export.json").write_text(json.dumps(self.manifest))
        self.job = SimpleNamespace(
            command_key="export.files.collect",
            command_version="1.0.0",
            arguments={"export_id": export_id, "sample_reference": "independent-A"},
        )

    def test_returns_original_files_and_receipt_not_a_fabricated_measurement(self):
        result = self.adapter.execute(self.job, threading.Event())
        self.assertEqual(result.result["sample_reference"], "independent-A")
        self.assertEqual(result.result["source_kind"], "file_export")
        self.assertFalse(result.result["scientific_validation"])
        self.assertEqual(
            {item["name"] for item in result.files}, {"export.json", "result.csv"}
        )
        selected = next(item for item in result.files if item["name"] == "result.csv")
        self.assertEqual(selected["sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(
            selected["original_units"], ["signal: independent_fixture_unit"]
        )
        self.assertEqual(selected["captured_at"], "2026-09-11T08:09:00-04:00")

    def test_identity_is_local_source_not_fabricated_device_firmware(self):
        self.assertEqual(self.adapter.identity()["firmware"], "not-observed")
        self.assertTrue(
            self.adapter.identity()["identity_reference"].startswith(
                "local-export-inbox:"
            )
        )

    def test_wrong_sample_unknown_command_cancellation_and_changed_bytes_fail(self):
        with self.assertRaises(ValueError):
            self.adapter.execute(
                SimpleNamespace(
                    **{**vars(self.job), "command_key": "instrument.start"}
                ),
                threading.Event(),
            )
        self.job.arguments["sample_reference"] = "other-sample"
        with self.assertRaises(ValueError):
            self.adapter.execute(self.job, threading.Event())
        self.job.arguments["sample_reference"] = "independent-A"
        stop = threading.Event()
        stop.set()
        with self.assertRaises(ExportReadCancelled):
            self.adapter.execute(self.job, stop)
        (self.directory / "result.csv").write_bytes(b"not the exported bytes")
        with self.assertRaises(RuntimeError):
            self.adapter.execute(self.job, threading.Event())


if __name__ == "__main__":
    unittest.main()
