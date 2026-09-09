"""Real local files, restarts and injected I/O faults; no instrument or network."""

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from airalogy_instrument_gateway.output_capture import CaptureStore
from airalogy_instrument_gateway.output_contract import (
    CAPTURE_SCHEMA,
    PLAN_SCHEMA,
    declarations,
    digest,
    validate_capture,
    validate_plan,
    validate_sources,
)


def plan():
    return {
        "schema": PLAN_SCHEMA,
        "job_id": str(uuid4()),
        "context_sha256": "a" * 64,
        "outputs": [
            {
                "name": "result.csv",
                "media_type": "text/csv",
                "max_bytes": 1024**2,
                "required": True,
            },
            {
                "name": "trace.txt",
                "media_type": "text/plain",
                "max_bytes": 4096,
                "required": False,
            },
        ],
    }


def selected():
    return [
        {
            "name": "result.csv",
            "path": "export/result.csv",
            "write_complete_confirmed": True,
            "captured_at": "2026-09-09T12:34:56.789+08:00",
            "original_units": ["signal: a.u."],
            "conversion_rules": [],
            "completion_reference": "Synthetic fixture: producer closed its file",
        }
    ]


class OutputContractTests(unittest.TestCase):
    def test_strict_declarations_and_portable_names(self):
        base = plan()["outputs"][:1]
        for changes in (
            {"name": "../secret"},
            {"name": "/secret"},
            {"name": "sub/file.csv"},
            {"name": "CON.txt"},
            {"name": "file."},
            {"name": "C:\\file.csv"},
            {"name": "file:stream"},
            {"name": "file*.csv"},
            {"name": "résult.csv"},
            {"media_type": "text/plain\r\nsecret: value"},
            {"media_type": "текст/csv"},
            {"max_bytes": True},
            {"max_bytes": 0},
            {"max_bytes": 2**31},
            {"required": 1},
            {"url": "https://example.invalid"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                declarations([{**base[0], **changes}])
        with self.assertRaises(ValueError):
            declarations([*base, {**base[0], "name": "RESULT.csv"}])
        with self.assertRaises(ValueError):
            declarations(base * 17)

    def test_strict_selection_and_timezone(self):
        for change in (
            {"path": "../result.csv"},
            {"path": "/etc/passwd"},
            {"path": "https://example.invalid/a"},
            {"write_complete_confirmed": 1},
            {"captured_at": "2026-09-09T01:02:03"},
            {"completion_reference": ""},
            {"original_units": ["a"] * 65},
            {"conversion_rules": ["b"] * 33},
            {"conversion_rules": ["a\ncommand"]},
            {"name": "unknown.csv"},
            {"record_id": str(uuid4())},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_sources(plan(), [{**selected()[0], **change}])
        with self.assertRaises(ValueError):
            validate_sources(plan(), [])
        with self.assertRaises(ValueError):
            validate_sources(
                plan(),
                [
                    *selected(),
                    {**selected()[0], "name": "trace.txt", "path": "EXPORT/result.csv"},
                ],
            )
        value = selected()
        self.assertEqual(validate_sources(plan(), value), value)

    def test_plan_is_pinned_to_canonical_identity(self):
        for change in (
            {"job_id": "../other"},
            {"job_id": uuid4()},
            {"job_id": str(uuid4()).upper()},
            {"context_sha256": "Z" * 64},
            {"schema": "unknown"},
            {"target": "/private"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_plan({**plan(), **change})
        value = plan()
        self.assertEqual(validate_plan(value), value)

    def test_shared_api_contract_is_identical(self):
        import airalogy_instrument_gateway.output_contract as contract

        root = Path(__file__).resolve().parents[3]
        self.assertEqual(
            Path(contract.__file__).read_bytes(),
            (root / "apps/api/app/services/instrument_output_contract.py").read_bytes(),
        )


@unittest.skipUnless(os.name == "posix", "POSIX raw-file capture support")
class CaptureStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root / "instrument-export"
        (self.source / "export").mkdir(parents=True, mode=0o700)
        self.raw = b"sample,signal\nsynthetic-1,0.42\n"
        self.source_file = self.source / "export/result.csv"
        self.source_file.write_bytes(self.raw)
        self.outbox = self.root / "outbox"
        self.plan = plan()
        self.sources = selected()
        self.store = self.new_store()

    def new_store(self, **kwargs):
        return CaptureStore(self.outbox, quiet_seconds=0.01, **kwargs)

    def prepare(self):
        return self.store.prepare(self.plan, self.source, self.sources)

    @property
    def job(self):
        return self.outbox / self.plan["job_id"]

    def test_capture_reopen_and_original_provenance(self):
        self.prepare()
        result = self.store.capture(self.plan)
        self.assertEqual(result["schema"], CAPTURE_SCHEMA)
        self.assertEqual(result["plan_digest"], digest(self.plan))
        self.assertEqual(result["omitted"], ["trace.txt"])
        self.assertEqual(
            result["files"][0]["captured_at"], self.sources[0]["captured_at"]
        )
        self.assertEqual(
            result["files"][0]["sha256"], hashlib.sha256(self.raw).hexdigest()
        )
        self.assertNotIn(str(self.source), json.dumps(result))
        self.assertNotIn("path", result["files"][0])
        self.source_file.unlink()
        self.assertEqual(self.new_store().inspect(self.plan), result)
        self.assertEqual(self.new_store().capture(self.plan), result)
        with self.new_store().open_output(self.plan, "result.csv") as (receipt, stream):
            self.assertEqual(receipt, result["files"][0])
            self.assertEqual(stream.read(), self.raw)
        for path in (self.outbox, self.job, *self.job.iterdir()):
            self.assertEqual(path.stat().st_mode & 0o077, 0)

    def test_explicit_optional_outputs_and_zero_length(self):
        (self.source / "optional.txt").write_bytes(b"")
        self.sources.append(
            {**self.sources[0], "name": "trace.txt", "path": "optional.txt"}
        )
        self.prepare()
        result = self.store.capture(self.plan)
        self.assertEqual(result["omitted"], [])
        self.assertEqual(result["files"][1]["byte_size"], 0)
        self.assertEqual(result["files"][1]["sha256"], hashlib.sha256(b"").hexdigest())

    def test_context_selection_and_source_identity_cannot_change(self):
        self.prepare()
        self.assertEqual(self.prepare()["plan_digest"], digest(self.plan))
        for changed in (
            {**self.plan, "context_sha256": "b" * 64},
            {**self.plan, "outputs": self.plan["outputs"][:1]},
        ):
            with self.assertRaises(ValueError):
                self.store.prepare(changed, self.source, self.sources)
        with self.assertRaises(ValueError):
            self.store.prepare(
                self.plan,
                self.source,
                [{**self.sources[0], "captured_at": "2026-09-08T01:02:03+00:00"}],
            )
        self.source.rename(self.root / "old-source")
        (self.source / "export").mkdir(parents=True)
        self.source_file.write_bytes(self.raw)
        with self.assertRaisesRegex(ValueError, "directory was replaced"):
            self.store.capture(self.plan)

    def test_unselected_files_never_enter_capture(self):
        (self.source / "not-selected-private.txt").write_text("must stay local")
        self.prepare()
        result = self.store.capture(self.plan)
        self.assertEqual([item["name"] for item in result["files"]], ["result.csv"])
        with (
            self.assertRaises(ValueError),
            self.store.open_output(self.plan, "../not-selected-private.txt"),
        ):
            pass

    def test_source_symlink_hardlink_and_fifo_are_rejected(self):
        self.source_file.unlink()
        target = self.root / "not-authorized.csv"
        target.write_bytes(self.raw)
        for kind in ("symlink", "hardlink", "fifo"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    self.source_file.symlink_to(target)
                elif kind == "hardlink":
                    os.link(target, self.source_file)
                else:
                    os.mkfifo(self.source_file)
                with self.assertRaises((OSError, ValueError)):
                    self.prepare()
                self.source_file.unlink()
                self.assertFalse(
                    self.job.exists(), "Invalid selection must not leave a blocking job"
                )

    def test_source_directory_links_and_permissions_are_rejected(self):
        linked = self.root / "linked"
        linked.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(OSError):
            self.store.prepare(self.plan, linked, self.sources)
        (self.source / "nested").symlink_to(
            self.source / "export", target_is_directory=True
        )
        with self.assertRaises(OSError):
            self.store.prepare(
                self.plan,
                self.source,
                [{**self.sources[0], "path": "nested/result.csv"}],
            )
        self.source_file.chmod(0o666)
        with self.assertRaises(ValueError):
            self.prepare()
        self.source_file.chmod(0o600)
        self.source.chmod(0o777)
        with self.assertRaises(ValueError):
            self.prepare()
        self.source.chmod(0o700)

    def test_outbox_symlink_hardlink_and_overlap_are_rejected(self):
        self.outbox.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(OSError):
            self.prepare()
        self.outbox.unlink()
        for output in (self.source, self.source / "outbox"):
            with self.assertRaises(ValueError):
                CaptureStore(output).prepare(self.plan, self.source, self.sources)
        self.prepare()
        target = self.root / "do-not-truncate"
        target.write_bytes(b"untouched")
        target.chmod(0o600)
        os.link(target, self.job / "output-00.partial")
        with self.assertRaises(ValueError):
            self.store.capture(self.plan)
        self.assertEqual(target.read_bytes(), b"untouched")

    def test_partial_writer_replacement_and_size_changes_are_rejected(self):
        self.prepare()
        original = self.source_file.stat()
        self.source_file.write_bytes(self.raw.replace(b"0.42", b"9.99"))
        os.utime(self.source_file, ns=(original.st_atime_ns, original.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, "changed since preparation"):
            self.store.capture(self.plan)
        self.assertFalse((self.job / "capture.json").exists())

    def test_mutation_during_quiet_window_is_rejected(self):
        self.prepare()
        with (
            patch(
                "airalogy_instrument_gateway.output_capture.time.sleep",
                side_effect=lambda _: self.source_file.write_bytes(b"new content"),
            ),
            self.assertRaisesRegex(ValueError, "still being written"),
        ):
            self.store.capture(self.plan)

    def test_mutation_after_copy_is_rejected(self):
        self.prepare()
        original_hash = self.store._hash

        def copying(fd, maximum, deadline, *, target=None):
            result = original_hash(fd, maximum, deadline, target=target)
            if target is not None:
                self.source_file.write_bytes(b"changed during read")
            return result

        with (
            patch.object(self.store, "_hash", side_effect=copying),
            self.assertRaises(ValueError),
        ):
            self.store.capture(self.plan)
        self.assertFalse((self.job / "output-00.json").exists())

    def test_snapshot_and_receipt_tampering_are_rejected(self):
        self.prepare()
        self.store.capture(self.plan)
        snapshot = self.job / "output-00.bin"
        snapshot.write_bytes(b"wrong")
        for read in (self.store.inspect, self.store.capture):
            with self.assertRaises(ValueError):
                read(self.plan)
        with (
            self.assertRaises(ValueError),
            self.store.open_output(self.plan, "result.csv"),
        ):
            pass
        snapshot.write_bytes(self.raw)
        receipt = self.job / "output-00.json"
        value = json.loads(receipt.read_text())
        receipt.write_text(
            json.dumps({**value, "captured_at": "2026-09-01T00:00:00+00:00"})
        )
        with self.assertRaises(ValueError):
            self.store.inspect(self.plan)

    def test_capture_manifest_cannot_leak_paths_or_relax_required_outputs(self):
        self.prepare()
        value = self.store.capture(self.plan)
        for change in (
            {"job_id": str(uuid4())},
            {"plan_digest": "a" * 64},
            {"omitted": []},
            {"files": []},
            {"files": [{**value["files"][0], "url": "https://example.invalid"}]},
            {"files": value["files"] * 2},
            {"files": [{**value["files"][0], "byte_size": True}]},
            {"files": [{**value["files"][0], "media_type": "text/html"}]},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_capture(self.plan, {**value, **change})

    def test_resume_after_lost_rename_without_original_source(self):
        self.prepare()
        replace = os.replace

        def crash(source, target, **kwargs):
            if target == "output-00.bin":
                raise OSError("simulated process loss before publish")
            return replace(source, target, **kwargs)

        with (
            patch(
                "airalogy_instrument_gateway.output_capture.os.replace",
                side_effect=crash,
            ),
            self.assertRaises(OSError),
        ):
            self.store.capture(self.plan)
        self.assertTrue((self.job / "output-00.json").exists())
        self.assertFalse((self.job / "output-00.bin").exists())
        self.source_file.unlink()
        result = self.new_store().capture(self.plan)
        self.assertEqual(
            result["files"][0]["sha256"], hashlib.sha256(self.raw).hexdigest()
        )

    def test_interrupted_preparation_preserves_original_content_pin(self):
        replace = os.replace

        def crash(source, target, **kwargs):
            if target == "request.json":
                raise OSError("injected preparation publish failure")
            return replace(source, target, **kwargs)

        with (
            patch(
                "airalogy_instrument_gateway.output_capture.os.replace",
                side_effect=crash,
            ),
            self.assertRaises(OSError),
        ):
            self.prepare()
        self.source_file.write_bytes(b"later experiment")
        self.prepare()
        request = json.loads((self.job / "request.json").read_text())
        self.assertEqual(
            request["source_hashes"]["result.csv"], hashlib.sha256(self.raw).hexdigest()
        )
        with self.assertRaises(ValueError):
            self.store.capture(self.plan)

    def test_missing_initial_journal_requires_explicit_reconciliation(self):
        self.outbox.mkdir(mode=0o700)
        self.job.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "no durable content pin"):
            self.prepare()
        self.assertFalse((self.job / "request.json").exists())

    def test_resume_partial_copy_and_lost_final_manifest(self):
        self.prepare()
        partial = self.job / "output-00.partial"
        partial.write_bytes(self.raw[:3])
        partial.chmod(0o600)
        replace = os.replace

        def crash(source, target, **kwargs):
            if target == "capture.json":
                raise OSError("simulated response loss before final manifest")
            return replace(source, target, **kwargs)

        with (
            patch(
                "airalogy_instrument_gateway.output_capture.os.replace",
                side_effect=crash,
            ),
            self.assertRaises(OSError),
        ):
            self.store.capture(self.plan)
        self.source_file.write_bytes(b"next experiment with the same filename")
        result = self.new_store().capture(self.plan)
        self.assertEqual(
            result["files"][0]["sha256"], hashlib.sha256(self.raw).hexdigest()
        )

    def test_repeated_filename_in_distinct_jobs_is_not_merged(self):
        self.prepare()
        first = self.store.capture(self.plan)
        other = {**self.plan, "job_id": str(uuid4()), "context_sha256": "b" * 64}
        self.source_file.write_bytes(b"another experiment")
        self.store.prepare(other, self.source, self.sources)
        second = self.store.capture(other)
        self.assertNotEqual(first["files"][0]["sha256"], second["files"][0]["sha256"])
        self.assertEqual(self.store.inspect(self.plan), first)

    def test_quotas_preserve_existing_and_pending_data(self):
        self.store = self.new_store(max_bytes=1024**2, max_jobs=1)
        self.source_file.write_bytes(b"x" * (600 * 1024))
        with self.assertRaisesRegex(ValueError, "byte quota"):
            self.prepare()
        self.assertFalse(self.job.exists())
        self.source_file.write_bytes(self.raw)
        self.prepare()
        self.store.capture(self.plan)
        other = {**self.plan, "job_id": str(uuid4())}
        with self.assertRaisesRegex(ValueError, "job quota"):
            self.store.prepare(other, self.source, self.sources)
        self.assertEqual(
            self.store.inspect(self.plan)["files"][0]["byte_size"], len(self.raw)
        )

    def test_second_pending_job_is_blocked_and_disk_full_is_safe(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "other pending"):
            self.store.prepare(
                {**self.plan, "job_id": str(uuid4())}, self.source, self.sources
            )
        fs = os.fstatvfs

        class FullDisk:
            f_bavail = 0
            f_frsize = 4096

        with (
            patch(
                "airalogy_instrument_gateway.output_capture.os.fstatvfs",
                return_value=FullDisk(),
            ),
            self.assertRaisesRegex(ValueError, "Insufficient"),
        ):
            self.store.capture(self.plan)
        self.assertIs(os.fstatvfs, fs)
        self.assertTrue((self.job / "request.json").exists())
        self.store.capture(self.plan)

    def test_completed_recovery_does_not_require_new_quota_or_source(self):
        self.prepare()
        expected = self.store.capture(self.plan)
        self.source_file.unlink()
        with patch.object(
            self.store, "_capacity", side_effect=ValueError("quota unavailable")
        ):
            self.assertEqual(self.prepare()["plan_digest"], digest(self.plan))
            self.assertEqual(self.store.capture(self.plan), expected)
            self.assertEqual(self.store.inspect(self.plan), expected)

    def test_deadline_keeps_prepared_state_for_recovery(self):
        self.prepare()
        with (
            patch.object(
                self.store,
                "_deadline",
                side_effect=TimeoutError("injected local deadline"),
            ),
            self.assertRaises(TimeoutError),
        ):
            self.store.capture(self.plan)
        self.assertFalse((self.job / "capture.json").exists())
        self.assertTrue((self.job / "request.json").exists())
        self.assertEqual(
            self.store.capture(self.plan)["files"][0]["byte_size"], len(self.raw)
        )

    def test_cross_process_lock_cannot_be_bypassed(self):
        self.prepare()
        with self.store._locked():
            script = "from airalogy_instrument_gateway.output_capture import CaptureStore; import sys; s=CaptureStore(sys.argv[1]);\nwith s._locked(): pass"
            result = subprocess.run(
                [sys.executable, "-B", "-c", script, str(self.outbox)],
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"BlockingIOError", result.stderr)
        self.store.capture(self.plan)

    def test_journal_corruption_and_large_metadata_are_rejected(self):
        self.prepare()
        request = self.job / "request.json"
        original = request.read_bytes()
        for raw in (b'{"plan": {}, "plan": {}}', b"x" * (300 * 1024)):
            request.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.store.capture(self.plan)
        request.write_bytes(original)
        corrupted = copy.deepcopy(json.loads(original))
        corrupted["stamps"]["result.csv"][2] = True
        request.write_text(json.dumps(corrupted))
        with self.assertRaises(ValueError):
            self.store.capture(self.plan)

    def test_content_pin_detects_changes_even_when_stat_timestamps_match(self):
        from airalogy_instrument_gateway import output_capture

        self.prepare()
        initial = self.source_file.stat()
        stamp = output_capture._stamp
        expected = stamp(initial)
        self.source_file.write_bytes(self.raw.replace(b"0.42", b"9.99"))

        def coarse_filesystem(info):
            return expected if info.st_ino == initial.st_ino else stamp(info)

        with (
            patch.object(output_capture, "_stamp", side_effect=coarse_filesystem),
            self.assertRaisesRegex(ValueError, "changed since preparation"),
        ):
            self.store.capture(self.plan)
        self.assertFalse((self.job / "output-00.json").exists())

    def test_finite_limits_and_unsupported_platform_fail_closed(self):
        for change in (
            {"max_jobs": True},
            {"max_bytes": True},
            {"quiet_seconds": 0},
            {"quiet_seconds": float("nan")},
            {"timeout_seconds": float("inf")},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                CaptureStore(self.outbox, **change)
        with (
            patch("airalogy_instrument_gateway.output_capture.os.name", "nt"),
            self.assertRaisesRegex(ValueError, "POSIX"),
        ):
            CaptureStore(self.outbox)
