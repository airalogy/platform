"""Bounded, read-only export inbox; no scanning, conversion or equipment control.

A reviewed producer closes files and atomically publishes <export UUID>/export.json
last. Its assertions bind bytes and explicit sample references, not scientific
validity or live hardware identity. Existing OutputDelivery makes durable copies.
"""

import hashlib
import math
import os
import threading
import time
from pathlib import Path
from uuid import UUID

from .credentials import read_private_json
from .models import InstrumentResult
from .output_capture import (
    CHUNK_BYTES,
    _absolute_directory,
    _source,
    _stamp,
    source_root_identity,
)
from .output_contract import (
    MAX_METADATA_BYTES,
    PROVENANCE_KEYS,
    SHA256,
    declarations,
    provenance,
    validate_sources,
)
from .package_contract import strict_json

CONFIG_SCHEMA = "airalogy.export-read-config.v1"
MANIFEST_SCHEMA = "airalogy.export-completion.v1"
MANIFEST_NAME = "export.json"


class ExportReadError(RuntimeError):
    pass


class ExportReadCancelled(ExportReadError):
    pass


class ExportReadTimeout(ExportReadError):
    pass


def validate_config(value):
    if not isinstance(value, dict) or set(value) != {"schema", "root", "root_identity"}:
        raise ValueError("Invalid export reader configuration")
    if value["schema"] != CONFIG_SCHEMA or not isinstance(value["root"], str):
        raise ValueError("Unsupported export reader configuration")
    identity = value["root_identity"]
    if (
        not isinstance(identity, list)
        or len(identity) != 2
        or any(type(n) is not int or not 0 <= n < 2**64 for n in identity)
    ):
        raise ValueError("Pin the selected export directory identity")
    if source_root_identity(value["root"]) != identity:
        raise ValueError("Export directory differs from its local authorization")
    return {**value, "root_identity": list(identity)}


def read_export_config(path):
    return validate_config(read_private_json(Path(path), strict=True))


def _sample(value):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 128
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise ValueError("Select an explicit sample reference")
    return value


class ExportReadClient:
    def __init__(self, config, outputs, *, max_total_bytes=64 * 1024 * 1024):
        self.config = validate_config(config)
        self.outputs = declarations(outputs)
        marker = next(
            (item for item in self.outputs if item["name"] == MANIFEST_NAME), None
        )
        if (
            not marker
            or marker["media_type"] != "application/json"
            or not marker["required"]
            or marker["max_bytes"] > MAX_METADATA_BYTES
        ):
            raise ValueError(
                "Declare a required bounded export.json completion receipt"
            )
        if (
            len(self.outputs) < 2
            or type(max_total_bytes) is not int
            or not 1 <= max_total_bytes <= 2**31 - 1
        ):
            raise ValueError("Declare data outputs and a bounded total read size")
        self.max_total_bytes = max_total_bytes
        self.lock = threading.Lock()

    def identity(self):
        """Fresh local inbox identity, NOT an observation of vendor hardware."""
        return validate_config(self.config)["root_identity"]

    def read(self, export_id, sample_reference, *, stop_event=None, timeout_seconds=30):
        if not isinstance(export_id, str) or str(UUID(export_id)) != export_id:
            raise ValueError("Select an exact export UUID; no latest-file selection")
        _sample(sample_reference)
        if (
            type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or not 0.01 <= timeout_seconds <= 120
        ):
            raise ValueError(
                "Export wait/read deadline must be between 0.01 and 120 seconds"
            )
        if not self.lock.acquire(blocking=False):
            raise ExportReadError("Another read is active on this export reader")
        stop = stop_event if stop_event is not None else threading.Event()
        deadline = time.monotonic() + timeout_seconds

        def check():
            if stop.is_set():
                raise ExportReadCancelled(
                    "Local export reading cancelled; no instrument stop was performed"
                )
            if time.monotonic() >= deadline:
                raise ExportReadTimeout(
                    "The selected export did not complete within the read deadline"
                )

        try:
            while True:
                check()
                self.identity()
                with _absolute_directory(self.config["root"]) as root:
                    if _stamp(os.fstat(root))[:2] != self.config["root_identity"]:
                        raise ExportReadError(
                            "Export directory was replaced before reading"
                        )
                    try:
                        marker, marker_stamp = self._manifest(root, export_id, check)
                    except FileNotFoundError:
                        marker = None
                    if marker is not None:
                        result = self._read_ready(
                            root, export_id, sample_reference, marker, check
                        )
                        again, stamp = self._manifest(root, export_id, check)
                        if again != marker or stamp != marker_stamp:
                            raise ExportReadError(
                                "Export completion receipt changed during reading"
                            )
                        self.identity()
                        check()
                        return result
                # Only this exact manifest is watched. Invalid/partial manifests
                # fail, rather than becoming an implicit retry or success signal.
                stop.wait(min(0.1, max(0, deadline - time.monotonic())))
        finally:
            self.lock.release()

    def _manifest(self, root, export_id, check):
        check()
        limit = next(
            item["max_bytes"] for item in self.outputs if item["name"] == MANIFEST_NAME
        )
        with _source(root, f"{export_id}/{MANIFEST_NAME}") as source:
            before = _stamp(os.fstat(source))
            if not 0 < before[2] <= limit:
                raise ExportReadError("Export receipt exceeds its declared size")
            raw = bytearray()
            while chunk := os.read(source, min(CHUNK_BYTES, limit + 1 - len(raw))):
                check()
                raw.extend(chunk)
                if len(raw) > limit:
                    raise ExportReadError(
                        "Export receipt exceeded its size while reading"
                    )
            if _stamp(os.fstat(source)) != before:
                raise ExportReadError("Export receipt is still changing")
            check()
            return bytes(raw), before

    def _read_ready(self, root, export_id, sample, raw, check):
        value = strict_json(raw)
        if not isinstance(value, dict) or set(value) != {
            "schema",
            "export_id",
            "sample_reference",
            "export_complete",
            "completed_at",
            "files",
        }:
            raise ValueError("Invalid export completion manifest")
        if (
            value["schema"] != MANIFEST_SCHEMA
            or value["export_id"] != export_id
            or value["sample_reference"] != sample
            or value["export_complete"] is not True
        ):
            raise ValueError(
                "Export identity, sample or explicit completion differs from this request"
            )
        if not isinstance(value["files"], list) or len(value["files"]) > 15:
            raise ValueError("Invalid completed export file count")
        # Shape validation only, not job authority. OutputDelivery validates the
        # returned sources again against the actual signed job's output plan.
        plan = {
            "schema": "airalogy.instrument-output-plan.v1",
            "job_id": export_id,
            "context_sha256": "0" * 64,
            "outputs": self.outputs,
        }
        sources, hashes, sizes = [], {}, {}
        for item in value["files"]:
            if (
                not isinstance(item, dict)
                or set(item) != {"name", "sha256", "byte_size", *PROVENANCE_KEYS}
                or not isinstance(item["name"], str)
                or item["name"] == MANIFEST_NAME
            ):
                raise ValueError("Invalid export file evidence")
            if (
                not isinstance(item["sha256"], str)
                or not SHA256.fullmatch(item["sha256"])
                or type(item["byte_size"]) is not int
                or item["byte_size"] < 0
            ):
                raise ValueError(
                    "Every completed export needs its original byte size and digest"
                )
            name = item["name"]
            # No paths, globs or URLs are accepted from producer metadata. Fixed
            # logical basenames below the selected UUID directory define access.
            sources.append(
                {
                    "name": name,
                    "path": f"{export_id}/{name}",
                    "write_complete_confirmed": True,
                    **provenance(item),
                }
            )
            hashes[name], sizes[name] = item["sha256"], item["byte_size"]
        sources.append(
            {
                "name": MANIFEST_NAME,
                "path": f"{export_id}/{MANIFEST_NAME}",
                "write_complete_confirmed": True,
                "captured_at": value["completed_at"],
                "original_units": [],
                "conversion_rules": [],
                "completion_reference": f"Export completion receipt {export_id}; byte collection only, not experiment success",
            }
        )
        sources = validate_sources(plan, sources)
        hashes[MANIFEST_NAME], sizes[MANIFEST_NAME] = (
            hashlib.sha256(raw).hexdigest(),
            len(raw),
        )
        if sum(sizes.values()) > self.max_total_bytes:
            raise ExportReadError("Selected export exceeds the total read quota")
        for declaration in self.outputs:
            check()
            name = declaration["name"]
            if name not in sizes:
                continue
            if sizes[name] > declaration["max_bytes"]:
                raise ExportReadError("Export file exceeds its approved size")
            if name == MANIFEST_NAME:
                continue
            path = f"{export_id}/{name}"
            with _source(root, path) as source:
                before = _stamp(os.fstat(source))
                if before[2] != sizes[name]:
                    raise ExportReadError(
                        "Export file size differs from its completion receipt"
                    )
                digest, size = hashlib.sha256(), 0
                while chunk := os.read(source, CHUNK_BYTES):
                    check()
                    size += len(chunk)
                    if size > sizes[name]:
                        raise ExportReadError("Export file is still growing")
                    digest.update(chunk)
                check()
                if (
                    size != sizes[name]
                    or digest.hexdigest() != hashes[name]
                    or _stamp(os.fstat(source)) != before
                ):
                    raise ExportReadError(
                        "Export bytes changed or differ from their completion receipt"
                    )
            with _source(root, path) as source:
                if _stamp(os.fstat(source)) != before:
                    raise ExportReadError("Export file was replaced while reading")
        return InstrumentResult(
            result={
                "export_id": export_id,
                "sample_reference": sample,
                "manifest_sha256": hashes[MANIFEST_NAME],
                "file_count": len(sources),
                "byte_size": sum(sizes.values()),
                "source_kind": "file_export",
                "scientific_validation": False,
            },
            files=[{**item, "sha256": hashes[item["name"]]} for item in sources],
        )
