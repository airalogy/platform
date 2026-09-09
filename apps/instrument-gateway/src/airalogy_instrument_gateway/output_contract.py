"""Bounded raw-file contracts, shared byte-for-byte with Platform.

These describe reported provenance, not verified scientific evidence. No field
grants file access, supplies a URL, runs a conversion, or submits a Record.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from uuid import UUID

PLAN_SCHEMA = "airalogy.instrument-output-plan.v1"
CAPTURE_SCHEMA = "airalogy.instrument-output-capture.v1"
MAX_FILES = 16
MAX_FILE_BYTES = 2_147_483_647
MAX_METADATA_BYTES = 128 * 1024
SHA256 = re.compile(r"[a-f0-9]{64}")
MEDIA_TYPE = re.compile(r"[a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+")


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _object(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f"Invalid {label} fields")


def _text(value, label, limit):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError(f"Invalid {label}")
    return value


def _integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Invalid {label}")
    return value


def relative_path(value):
    """Portable, explicitly selected relative path, never a URL or glob."""
    _text(value, "output path", 240)
    for part in value.split("/"):
        if (
            not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", part)
            or part.endswith(".")
            or part.split(".")[0].upper()
            in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *[f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)],
            }
        ):
            raise ValueError("Output path must be a relative portable path")
    return value


def declarations(value):
    if not isinstance(value, list) or len(value) > MAX_FILES:
        raise ValueError("Invalid output declaration count")
    seen = set()
    for item in value:
        _object(
            item, ("name", "media_type", "max_bytes", "required"), "output declaration"
        )
        name = relative_path(item["name"])
        if "/" in name or name.casefold() in seen:
            raise ValueError("Output names must be unique portable basenames")
        seen.add(name.casefold())
        if not MEDIA_TYPE.fullmatch(_text(item["media_type"], "media type", 128)):
            raise ValueError("Invalid output media type")
        _integer(item["max_bytes"], "output maximum size", 1, MAX_FILE_BYTES)
        if type(item["required"]) is not bool:
            raise ValueError("Output required must be boolean")
    return sorted([dict(item) for item in value], key=lambda item: item["name"])


def validate_plan(value):
    _object(value, ("schema", "job_id", "context_sha256", "outputs"), "output plan")
    if value["schema"] != PLAN_SCHEMA:
        raise ValueError("Unsupported output plan schema")
    job_id = value["job_id"]
    if not isinstance(job_id, str) or str(UUID(job_id)) != job_id:
        raise ValueError("Output plan requires a canonical job UUID")
    if not isinstance(value["context_sha256"], str) or not SHA256.fullmatch(
        value["context_sha256"]
    ):
        raise ValueError("Output plan requires its exact approved context digest")
    result = {**value, "outputs": declarations(value["outputs"])}
    if len(canonical(result)) > MAX_METADATA_BYTES:
        raise ValueError("Output plan exceeds its metadata limit")
    return result


PROVENANCE_KEYS = (
    "captured_at",
    "original_units",
    "conversion_rules",
    "completion_reference",
)


def provenance(value):
    timestamp = _text(value["captured_at"], "capture time", 64)
    instant = datetime.fromisoformat(timestamp)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Capture time must include its original timezone offset")
    # Preserve the reported offset. A timestamp is not proof that acquisition or
    # file writing succeeded; require a separate reviewed completion reference.
    _text(value["completion_reference"], "file completion reference", 1024)
    for field, count, length in (
        ("original_units", 64, 512),
        ("conversion_rules", 32, 1024),
    ):
        items = value[field]
        if not isinstance(items, list) or len(items) > count:
            raise ValueError(f"Invalid {field}")
        for item in items:
            _text(item, field, length)
    return {key: value[key] for key in PROVENANCE_KEYS}


def validate_sources(plan, value):
    plan = validate_plan(plan)
    if not isinstance(value, list) or len(value) > MAX_FILES:
        raise ValueError("Invalid selected output count")
    declared = {item["name"]: item for item in plan["outputs"]}
    seen, paths = set(), set()
    for item in value:
        _object(
            item,
            ("name", "path", "write_complete_confirmed", *PROVENANCE_KEYS),
            "selected output",
        )
        if (
            not isinstance(item["name"], str)
            or item["name"] not in declared
            or item["name"] in seen
        ):
            raise ValueError("Selected output is duplicated or undeclared")
        seen.add(item["name"])
        path = relative_path(item["path"])
        if path.casefold() in paths:
            raise ValueError("Each selected output requires a distinct source path")
        paths.add(path.casefold())
        if item["write_complete_confirmed"] is not True:
            raise ValueError("Confirm file writing finished before capture")
        provenance(item)
    if any(item["required"] and name not in seen for name, item in declared.items()):
        raise ValueError("A required output is missing")
    result = sorted(value, key=lambda item: item["name"])
    if len(canonical(result)) > MAX_METADATA_BYTES:
        raise ValueError("Selected output metadata exceeds its limit")
    return json.loads(canonical(result))


def validate_capture(plan, value):
    plan = validate_plan(plan)
    _object(
        value, ("schema", "job_id", "plan_digest", "files", "omitted"), "output capture"
    )
    if (
        value["schema"] != CAPTURE_SCHEMA
        or value["job_id"] != plan["job_id"]
        or value["plan_digest"] != digest(plan)
    ):
        raise ValueError("Output capture differs from the pinned plan")
    if not isinstance(value["files"], list) or len(value["files"]) > MAX_FILES:
        raise ValueError("Invalid captured output count")
    declared = {item["name"]: item for item in plan["outputs"]}
    seen = set()
    for item in value["files"]:
        _object(
            item,
            ("name", "sha256", "byte_size", "media_type", *PROVENANCE_KEYS),
            "captured output",
        )
        name = item["name"]
        if not isinstance(name, str) or name not in declared or name in seen:
            raise ValueError("Captured output is duplicated or undeclared")
        seen.add(name)
        contract = declared[name]
        if item["media_type"] != contract["media_type"]:
            raise ValueError("Captured output media type differs from its declaration")
        if not isinstance(item["sha256"], str) or not SHA256.fullmatch(item["sha256"]):
            raise ValueError("Invalid captured output digest")
        _integer(item["byte_size"], "captured output size", 0, contract["max_bytes"])
        provenance(item)
    omitted = sorted(set(declared) - seen)
    if value["omitted"] != omitted or any(
        declared[name]["required"] for name in omitted
    ):
        raise ValueError("Output capture omits a required or undeclared file")
    if len(canonical(value)) > MAX_METADATA_BYTES:
        raise ValueError("Output capture exceeds its metadata limit")
    return json.loads(
        canonical(
            {**value, "files": sorted(value["files"], key=lambda item: item["name"])}
        )
    )
