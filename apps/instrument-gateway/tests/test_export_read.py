"""Owned export files only; no directory scan, network, model or instrument."""

import hashlib
import json
import os
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from airalogy_instrument_gateway.export_read import (
    ExportReadCancelled,
    ExportReadClient,
    ExportReadError,
    ExportReadTimeout,
    validate_config,
)
from airalogy_instrument_gateway.output_capture import (
    _absolute_directory,
    source_root_identity,
)
from airalogy_instrument_gateway.output_delivery import selection

OUTPUTS = [
    {
        "name": "result.csv",
        "media_type": "text/csv",
        "max_bytes": 1048576,
        "required": True,
    },
    {
        "name": "export.json",
        "media_type": "application/json",
        "max_bytes": 131072,
        "required": True,
    },
]
DATA = b"sample,signal\nsample-A,1.25\n"


def config(root):
    return {
        "schema": "airalogy.export-read-config.v1",
        "root": str(root),
        "root_identity": source_root_identity(root),
    }


def manifest(export_id):
    return {
        "schema": "airalogy.export-completion.v1",
        "export_id": export_id,
        "sample_reference": "sample-A",
        "export_complete": True,
        "completed_at": "2026-09-11T12:30:00+08:00",
        "files": [
            {
                "name": "result.csv",
                "sha256": hashlib.sha256(DATA).hexdigest(),
                "byte_size": len(DATA),
                "captured_at": "2026-09-11T12:29:00+08:00",
                "original_units": ["signal: synthetic_unit"],
                "conversion_rules": [],
                "completion_reference": "Owned synthetic export closed; not an instrument experiment",
            }
        ],
    }


def publish(root, export_id, value=None):
    directory = root / export_id
    directory.mkdir(mode=0o700, exist_ok=True)
    (directory / "result.csv").write_bytes(DATA)
    temporary = directory / "export.tmp"
    temporary.write_text(
        json.dumps(value if value is not None else manifest(export_id))
    )
    temporary.replace(directory / "export.json")


class ExportReadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.export_id = str(uuid4())
        self.client = ExportReadClient(config(self.root), OUTPUTS)

    def read(self, **kwargs):
        return self.client.read(self.export_id, "sample-A", **kwargs)

    def test_invalid_local_configuration_and_read_limits_fail_before_io(self):
        current = config(self.root)
        for changed in (
            {**current, "root_identity": [True, 1]},
            {**current, "root_identity": [0, -1]},
            {**current, "schema": "unknown"},
            {**current, "root": "relative"},
            {**current, "extra": 1},
        ):
            with self.assertRaises(ValueError):
                validate_config(changed)
        with patch.object(
            self.client, "_manifest", side_effect=AssertionError("No read")
        ):
            for seconds in (False, 0, -1, 121, float("nan"), float("inf")):
                with self.assertRaises(ValueError):
                    self.read(timeout_seconds=seconds)
            for sample in ("", " ", "a\n", "a" * 129, None):
                with self.assertRaises(ValueError):
                    self.client.read(self.export_id, sample)
        self.assertFalse(self.client.lock.locked())

    def test_root_replacement_between_identity_check_and_open_prevents_read(self):
        source = self.root / "inbox"
        source.mkdir(mode=0o700)
        client = ExportReadClient(config(source), OUTPUTS)

        @contextmanager
        def replace_then_open(path):
            source.rename(self.root / "original-inbox")
            source.mkdir(mode=0o700)
            with _absolute_directory(path) as fd:
                yield fd

        with (
            patch(
                "airalogy_instrument_gateway.export_read._absolute_directory",
                replace_then_open,
            ),
            patch.object(client, "_manifest", side_effect=AssertionError("No read")),
            self.assertRaises(ExportReadError),
        ):
            client.read(self.export_id, "sample-A")

    def test_data_mutation_during_read_is_rejected(self):
        publish(self.root, self.export_id)
        selected = self.root / self.export_id / "result.csv"
        inode = selected.stat().st_ino
        original = os.read

        def read_then_change(fd, length):
            raw = original(fd, length)
            if raw and os.fstat(fd).st_ino == inode:
                before = selected.stat()
                selected.write_bytes(b"x" * len(DATA))
                # Make the injected mutation observable even when successive
                # tmpfs writes fall within the same filesystem clock tick.
                os.utime(
                    selected,
                    ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000),
                )
            return raw

        with (
            patch("os.read", side_effect=read_then_change),
            self.assertRaises(ExportReadError),
        ):
            self.read()

    def test_valid_export_preserves_original_bytes_units_and_explicit_sample(self):
        publish(self.root, self.export_id)
        with patch("os.scandir", side_effect=AssertionError("No scanning")):
            result = self.read()
        self.assertFalse(result.result["scientific_validation"])
        self.assertEqual(result.result["sample_reference"], "sample-A")
        self.assertEqual(result.result["file_count"], 2)
        source = next(item for item in result.files if item["name"] == "result.csv")
        self.assertEqual(source["sha256"], hashlib.sha256(DATA).hexdigest())
        self.assertEqual(source["captured_at"], "2026-09-11T12:29:00+08:00")
        self.assertEqual(source["original_units"], ["signal: synthetic_unit"])
        self.assertEqual((self.root / self.export_id / "result.csv").read_bytes(), DATA)
        plan = {
            "schema": "airalogy.instrument-output-plan.v1",
            "job_id": str(uuid4()),
            "context_sha256": "a" * 64,
            "outputs": OUTPUTS,
        }
        self.assertEqual(len(selection(plan, result.files)[0]), 2)

    def test_waits_for_only_the_selected_atomic_completion_receipt(self):
        publish(self.root, str(uuid4()))
        timer = threading.Timer(0.05, publish, args=(self.root, self.export_id))
        timer.start()
        try:
            self.assertEqual(
                self.read(timeout_seconds=1).result["export_id"], self.export_id
            )
        finally:
            timer.join(timeout=2)

    def test_partial_or_missing_data_is_not_completion(self):
        directory = self.root / self.export_id
        directory.mkdir(mode=0o700)
        (directory / "result.csv").write_bytes(DATA)
        with self.assertRaises(ExportReadTimeout):
            self.read(timeout_seconds=0.03)
        (directory / "export.json").write_text('{"schema":')
        with self.assertRaises(ValueError):
            self.read()
        publish(self.root, self.export_id)
        (directory / "result.csv").write_bytes(DATA[:2])
        with self.assertRaises(ExportReadError):
            self.read()
        (directory / "result.csv").unlink()
        with self.assertRaises(FileNotFoundError):
            self.read()

    def test_sample_identity_completion_and_metadata_shapes_are_not_guessed(self):
        for field, values in {
            "export_id": [str(uuid4()), None],
            "sample_reference": ["sample-B", None],
            "export_complete": [False, 1],
            "completed_at": ["2026-09-11T12:30:00", "bad"],
        }.items():
            for value in values:
                content = manifest(self.export_id)
                content[field] = value
                publish(self.root, self.export_id, content)
                with (
                    self.subTest(field=field, value=value),
                    self.assertRaises(ValueError),
                ):
                    self.read()
        for value in (None, [], {}, True):
            content = manifest(self.export_id)
            content["files"][0]["name"] = value
            publish(self.root, self.export_id, content)
            with self.assertRaises(ValueError):
                self.read()

    def test_undeclared_paths_duplicates_hashes_and_quotas_fail(self):
        for name in (
            "../secret",
            "/secret",
            "other.csv",
            "export.json",
            "https://example.com",
        ):
            value = manifest(self.export_id)
            value["files"][0]["name"] = name
            publish(self.root, self.export_id, value)
            with self.assertRaises(ValueError):
                self.read()
        value = manifest(self.export_id)
        value["files"] *= 2
        publish(self.root, self.export_id, value)
        with self.assertRaises(ValueError):
            self.read()
        publish(self.root, self.export_id)
        (self.root / self.export_id / "result.csv").write_bytes(b"x" * len(DATA))
        with self.assertRaises(ExportReadError):
            self.read()
        publish(self.root, self.export_id)
        client = ExportReadClient(config(self.root), OUTPUTS, max_total_bytes=1)
        with self.assertRaises(ExportReadError):
            client.read(self.export_id, "sample-A")

    def test_links_special_files_permissions_and_directory_replacement_fail(self):
        publish(self.root, self.export_id)
        selected = self.root / self.export_id / "result.csv"
        selected.unlink()
        selected.symlink_to(self.root / "private.csv")
        with self.assertRaises(OSError):
            self.read()
        selected.unlink()
        outside = self.root / "private.csv"
        outside.write_bytes(DATA)
        os.link(outside, selected)
        with self.assertRaises(ValueError):
            self.read()
        selected.unlink()
        os.mkfifo(selected)
        with self.assertRaises(ValueError):
            self.read()
        selected.unlink()
        selected.write_bytes(DATA)
        selected.chmod(0o666)
        with self.assertRaises(ValueError):
            self.read()
        self.client.config["root_identity"][1] += 1
        with self.assertRaises(ValueError):
            self.read()

    def test_cancellation_and_single_reader_lock(self):
        stop = threading.Event()
        errors = []

        def read():
            try:
                self.read(stop_event=stop)
            except ExportReadCancelled as error:
                errors.append(error)

        entered = threading.Event()
        original = self.client._manifest

        def observed(*args):
            entered.set()
            return original(*args)

        with patch.object(self.client, "_manifest", side_effect=observed):
            worker = threading.Thread(target=read)
            worker.start()
            try:
                self.assertTrue(entered.wait(timeout=1))
                with self.assertRaises(ExportReadError):
                    self.read()
            finally:
                stop.set()
                worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)

    def test_receipt_replacement_before_return_is_rejected(self):
        publish(self.root, self.export_id)
        original = self.client._read_ready

        def replaced(*args):
            result = original(*args)
            publish(self.root, self.export_id)
            return result

        with (
            patch.object(self.client, "_read_ready", side_effect=replaced),
            self.assertRaises(ExportReadError),
        ):
            self.read()


if __name__ == "__main__":
    unittest.main()
