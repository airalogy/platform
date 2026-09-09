"""POSIX local raw-file outbox. Never controls equipment or sends network traffic.

The caller must hold the Instrument runtime lock and supply a pinned plan plus
explicit, independently reviewed file-completion observations. A stable file is
not proof of a successful experiment. Files remain until an operator-controlled
retention workflow removes them; no automatic eviction can destroy offline data.
"""

from __future__ import annotations

import hashlib
import math
import os
import stat
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from .output_contract import (
    CAPTURE_SCHEMA,
    MAX_METADATA_BYTES,
    SHA256,
    canonical,
    digest,
    provenance,
    validate_capture,
    validate_plan,
    validate_sources,
)
from .package_contract import strict_json

CHUNK_BYTES = 64 * 1024
LOCAL_METADATA_LIMIT = MAX_METADATA_BYTES * 2


def _check_platform():
    if os.name != "posix" or not all(
        hasattr(os, key) for key in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")
    ):
        raise ValueError("Safe raw-file capture currently requires POSIX local storage")


def _directory(info, *, private=False):
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & (0o077 if private else 0o022)
    ):
        raise ValueError(
            "Selected directory must be owned by this user and not writable by others"
        )


def _regular(info, *, private=False):
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.getuid()
        or info.st_mode & (0o077 if private else 0o022)
    ):
        raise ValueError(
            "Output must be an owned regular file without links or other writers"
        )


def _stamp(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


@contextmanager
def _absolute_directory(path, *, private=False, create=False):
    # Do not resolve() away a symlink supplied by an adapter. The operator must
    # explicitly select the actual absolute directory (e.g. /private/tmp on macOS).
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts or str(path) == "/":
        raise ValueError(
            "Select an absolute non-root directory without parent traversal"
        )
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for index, part in enumerate(path.parts[1:]):
            if create and index == len(path.parts) - 2:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
        _directory(os.fstat(fd), private=private)
        yield fd
    finally:
        os.close(fd)


@contextmanager
def _source(root_fd, path):
    fd = os.dup(root_fd)
    device = os.fstat(root_fd).st_dev
    try:
        parts = path.split("/")
        for part in parts[:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            _directory(info)
            if info.st_dev != device:
                raise ValueError("Output path crosses a filesystem boundary")
        file_fd = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
        )
        try:
            info = os.fstat(file_fd)
            _regular(info)
            if info.st_dev != device:
                raise ValueError("Output file crosses a filesystem boundary")
            yield file_fd
        finally:
            os.close(file_fd)
    finally:
        os.close(fd)


@contextmanager
def _private_file(directory, name, *, write=False):
    flags = os.O_RDWR | os.O_CREAT if write else os.O_RDONLY
    fd = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
    try:
        _regular(os.fstat(fd), private=True)
        yield fd
    finally:
        os.close(fd)


def _read_json(directory, name):
    with _private_file(directory, name) as fd:
        if os.fstat(fd).st_size > LOCAL_METADATA_LIMIT:
            raise ValueError("Local output journal exceeds its limit")
        raw = bytearray()
        while chunk := os.read(
            fd, min(CHUNK_BYTES, LOCAL_METADATA_LIMIT + 1 - len(raw))
        ):
            raw.extend(chunk)
            if len(raw) > LOCAL_METADATA_LIMIT:
                raise ValueError("Local output journal exceeds its limit")
    return strict_json(bytes(raw))


def _exists(directory, name):
    try:
        info = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return False
    _regular(info, private=True)
    return True


def _write_json(directory, name, value):
    raw = canonical(value)
    if len(raw) > LOCAL_METADATA_LIMIT:
        raise ValueError("Local output journal exceeds its limit")
    temporary = f".{name}.tmp"
    with _private_file(directory, temporary, write=True) as fd:
        # Validate existing crash remnants before truncating: O_TRUNC during
        # open would modify a hard-linked file before its link count is checked.
        os.ftruncate(fd, 0)
        with os.fdopen(os.dup(fd), "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
    os.fsync(directory)


class CaptureStore:
    def __init__(
        self,
        outbox,
        *,
        max_bytes=4 * 1024**3,
        max_jobs=100,
        quiet_seconds=1.0,
        timeout_seconds=300.0,
    ):
        _check_platform()
        if type(max_bytes) is not int or not 1024**2 <= max_bytes <= 1024**4:
            raise ValueError("Outbox capacity must be between 1 MiB and 1 TiB")
        if type(max_jobs) is not int or not 1 <= max_jobs <= 1000:
            raise ValueError("Outbox job limit must be between 1 and 1000")
        if any(
            type(value) not in (int, float) or not math.isfinite(value)
            for value in (quiet_seconds, timeout_seconds)
        ):
            raise ValueError("Capture timing limits must be finite numbers")
        if (
            not 0.01 <= quiet_seconds <= 60
            or not quiet_seconds < timeout_seconds <= 3600
        ):
            raise ValueError("Invalid file quiet interval or capture deadline")
        self.outbox = Path(outbox)
        self.max_bytes, self.max_jobs = max_bytes, max_jobs
        self.quiet_seconds, self.timeout_seconds = quiet_seconds, timeout_seconds

    @contextmanager
    def _locked(self, *, create=False):
        import fcntl

        with (
            _absolute_directory(self.outbox, private=True, create=create) as fd,
            _private_file(fd, ".capture.lock", write=True) as lock,
        ):
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield fd
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    @contextmanager
    def _job(self, root, job_id, *, create=False):
        if create:
            try:
                os.mkdir(job_id, 0o700, dir_fd=root)
                os.fsync(root)
            except FileExistsError:
                pass
        fd = os.open(job_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        try:
            _directory(os.fstat(fd), private=True)
            if os.fstat(fd).st_dev != os.fstat(root).st_dev:
                raise ValueError("Outbox job crosses a filesystem boundary")
            yield fd
        finally:
            os.close(fd)

    def _inventory(self, root, job_id):
        total, count, found = 0, 0, False
        with os.scandir(root) as entries:
            for entry in entries:
                if entry.name == ".capture.lock":
                    continue
                count += 1
                if count > self.max_jobs:
                    raise ValueError(
                        "Outbox job quota exceeded; preserve and reconcile existing data"
                    )
                if str(UUID(entry.name)) != entry.name:
                    raise ValueError("Unexpected directory in the private outbox")
                found |= entry.name == job_id
                with self._job(root, entry.name) as job:
                    if entry.name != job_id and not _exists(job, "capture.json"):
                        raise ValueError(
                            "Finish the other pending file capture before preparing new work"
                        )
                    with os.scandir(job) as files:
                        for index, item in enumerate(files):
                            if index >= 70:
                                raise ValueError("Outbox job contains too many files")
                            info = item.stat(follow_symlinks=False)
                            _regular(info, private=True)
                            total += info.st_size
        if not found and count >= self.max_jobs:
            raise ValueError("Outbox job quota exceeded; no existing data was removed")
        return total

    def _capacity(self, root, job_id, additional):
        total = self._inventory(root, job_id)
        if total + additional > self.max_bytes:
            raise ValueError("Outbox byte quota exceeded; no existing data was removed")
        disk = os.fstatvfs(root)
        if additional > disk.f_bavail * disk.f_frsize:
            raise ValueError("Insufficient local space for the selected outputs")

    def prepare(self, plan, source_root, sources):
        """Pin explicitly finished source files. Retrying never selects new bytes."""
        plan = validate_plan(plan)
        sources = validate_sources(plan, sources)
        deadline = time.monotonic() + self.timeout_seconds
        source_root = Path(source_root)
        if (
            source_root == self.outbox
            or source_root in self.outbox.parents
            or self.outbox in source_root.parents
        ):
            raise ValueError("Source and private outbox directories must not overlap")
        selection = {"plan": plan, "source_root": str(source_root), "sources": sources}
        with self._locked(create=True) as root:
            try:
                os.stat(plan["job_id"], dir_fd=root, follow_symlinks=False)
                exists = True
            except FileNotFoundError:
                exists = False
            if exists:
                with self._job(root, plan["job_id"]) as job:
                    committed = _exists(job, "request.json")
                    journal = "request.json" if committed else ".request.json.tmp"
                    if not _exists(job, journal):
                        raise ValueError(
                            "Capture preparation has no durable content pin; reconcile it before retrying"
                        )
                    # Recover only a complete private temporary journal. Never
                    # repin today's source bytes after losing yesterday's intent.
                    existing = self._request(job, plan, journal=journal)
                    if any(existing[key] != value for key, value in selection.items()):
                        raise ValueError(
                            "A different file selection is already pinned to this job"
                        )
                    if not committed:
                        _write_json(job, "request.json", existing)
                    return self._summary(existing)
            self._capacity(root, plan["job_id"], LOCAL_METADATA_LIMIT)
            declared = {item["name"]: item for item in plan["outputs"]}
            stamps = {}
            source_hashes = {}
            with _absolute_directory(source_root) as source:
                identity = _stamp(os.fstat(source))[:2]
                for item in sources:
                    with _source(source, item["path"]) as fd:
                        info = os.fstat(fd)
                        if info.st_size > declared[item["name"]]["max_bytes"]:
                            raise ValueError(
                                "Selected output exceeds its declared size"
                            )
                        stamps[item["name"]] = _stamp(info)
                        self._capacity(
                            root,
                            plan["job_id"],
                            sum(value[2] for value in stamps.values())
                            + LOCAL_METADATA_LIMIT * 2,
                        )
                        checksum, size = self._hash(fd, info.st_size, deadline)
                        if size != info.st_size or _stamp(os.fstat(fd)) != _stamp(info):
                            raise ValueError(
                                "Selected output changed during preparation"
                            )
                        source_hashes[item["name"]] = checksum
                    with _source(source, item["path"]) as current:
                        if _stamp(os.fstat(current)) != stamps[item["name"]]:
                            raise ValueError(
                                "Selected output path changed during preparation"
                            )
            self._capacity(
                root,
                plan["job_id"],
                sum(value[2] for value in stamps.values()) + LOCAL_METADATA_LIMIT * 2,
            )
            request = {
                **selection,
                "source_identity": identity,
                "stamps": stamps,
                "source_hashes": source_hashes,
            }
            with self._job(root, plan["job_id"], create=True) as job:
                if _exists(job, "request.json"):
                    raise ValueError("Output selection appeared concurrently")
                _write_json(job, "request.json", request)
                return self._summary(request)

    @staticmethod
    def _summary(request):
        return {
            "job_id": request["plan"]["job_id"],
            "plan_digest": digest(request["plan"]),
            "selected": [item["name"] for item in request["sources"]],
        }

    @staticmethod
    def _request(job, plan, *, journal="request.json"):
        request = _read_json(job, journal)
        if (
            not isinstance(request, dict)
            or set(request)
            != {
                "plan",
                "source_root",
                "sources",
                "source_identity",
                "stamps",
                "source_hashes",
            }
            or request["plan"] != plan
        ):
            raise ValueError(
                "Output capture plan changed or its local journal is invalid"
            )
        sources = validate_sources(plan, request["sources"])
        if (
            not isinstance(request["source_root"], str)
            or not Path(request["source_root"]).is_absolute()
        ):
            raise ValueError("Invalid pinned source root")
        if (
            not isinstance(request["source_identity"], list)
            or len(request["source_identity"]) != 2
        ):
            raise ValueError("Invalid pinned source identity")
        if not isinstance(request["stamps"], dict) or set(request["stamps"]) != {
            item["name"] for item in sources
        }:
            raise ValueError("Invalid pinned output identities")
        for value in [request["source_identity"], *request["stamps"].values()]:
            if not isinstance(value, list) or any(
                type(number) is not int or number < 0 for number in value
            ):
                raise ValueError("Invalid pinned output identity")
        if any(len(value) != 5 for value in request["stamps"].values()):
            raise ValueError("Invalid pinned output identity")
        if (
            not isinstance(request["source_hashes"], dict)
            or set(request["source_hashes"]) != set(request["stamps"])
            or any(
                not isinstance(value, str) or not SHA256.fullmatch(value)
                for value in request["source_hashes"].values()
            )
        ):
            raise ValueError("Invalid pinned output content digest")
        return request

    @staticmethod
    def _deadline(deadline):
        if time.monotonic() > deadline:
            raise TimeoutError(
                "File capture exceeded its local deadline; resume without executing the instrument"
            )

    def _hash(self, fd, maximum, deadline, *, target=None):
        result, size = hashlib.sha256(), 0
        while True:
            self._deadline(deadline)
            chunk = os.read(fd, min(CHUNK_BYTES, maximum + 1 - size))
            if not chunk:
                return result.hexdigest(), size
            size += len(chunk)
            if size > maximum:
                raise ValueError("Output exceeded its pinned size during capture")
            result.update(chunk)
            if target is not None:
                target.write(chunk)

    def _verify(self, job, name, receipt, deadline):
        with _private_file(job, name) as fd:
            before = _stamp(os.fstat(fd))
            observed = self._hash(fd, receipt["byte_size"], deadline)
            if (
                observed != (receipt["sha256"], receipt["byte_size"])
                or _stamp(os.fstat(fd)) != before
            ):
                raise ValueError(
                    "Captured snapshot changed or is incomplete; never upload it"
                )

    def _capture_one(self, job, request, item, index, deadline):
        name = item["name"]
        output = f"output-{index:02d}.bin"
        receipt_name, partial = (
            f"output-{index:02d}.json",
            f"output-{index:02d}.partial",
        )
        declared = next(
            value for value in request["plan"]["outputs"] if value["name"] == name
        )
        if _exists(job, receipt_name):
            receipt = _read_json(job, receipt_name)
            # Validate this receipt against a one-file view, without relaxing the
            # original plan's required-file checks on the final manifest.
            self._validate_receipt(request, item, receipt)
            if _exists(job, output):
                self._verify(job, output, receipt, deadline)
            else:
                self._verify(job, partial, receipt, deadline)
                os.replace(partial, output, src_dir_fd=job, dst_dir_fd=job)
                os.fsync(job)
            return receipt
        if _exists(job, output):
            raise ValueError(
                "Snapshot has no durable receipt; preserve it for reconciliation"
            )
        with _absolute_directory(request["source_root"]) as source:
            if _stamp(os.fstat(source))[:2] != request["source_identity"]:
                raise ValueError("Selected source directory was replaced")
            with _source(source, item["path"]) as fd:
                expected = request["stamps"][name]
                if _stamp(os.fstat(fd)) != expected:
                    raise ValueError("Selected output changed since preparation")
                time.sleep(self.quiet_seconds)
                self._deadline(deadline)
                if _stamp(os.fstat(fd)) != expected:
                    raise ValueError("Selected output is still being written")
                with _private_file(job, partial, write=True) as target_fd:
                    os.ftruncate(target_fd, 0)
                    with os.fdopen(os.dup(target_fd), "wb") as target:
                        checksum, size = self._hash(
                            fd,
                            min(expected[2], declared["max_bytes"]),
                            deadline,
                            target=target,
                        )
                        target.flush()
                        os.fsync(target.fileno())
                os.lseek(fd, 0, os.SEEK_SET)
                if (
                    self._hash(fd, expected[2], deadline) != (checksum, size)
                    or _stamp(os.fstat(fd)) != expected
                ):
                    raise ValueError("Selected output changed while copying")
                with _source(source, item["path"]) as current:
                    if _stamp(os.fstat(current)) != expected:
                        raise ValueError(
                            "Selected output path was replaced while copying"
                        )
                if size != expected[2]:
                    raise ValueError("Selected output was only partially copied")
                if checksum != request["source_hashes"][name]:
                    raise ValueError("Selected output changed since preparation")
                receipt = {
                    "name": name,
                    "sha256": checksum,
                    "byte_size": size,
                    "media_type": declared["media_type"],
                    **provenance(item),
                }
                # Record the verified hash before publishing the data filename.
                # Recovery can then safely finish a lost rename, even after the
                # vendor overwrote or removed the original source file.
                _write_json(job, receipt_name, receipt)
                os.replace(partial, output, src_dir_fd=job, dst_dir_fd=job)
                os.fsync(job)
                return receipt

    @staticmethod
    def _validate_receipt(request, item, receipt):
        single = {
            **request["plan"],
            "outputs": [
                value
                for value in request["plan"]["outputs"]
                if value["name"] == item["name"]
            ],
        }
        validate_capture(
            single,
            {
                "schema": CAPTURE_SCHEMA,
                "job_id": single["job_id"],
                "plan_digest": digest(single),
                "files": [receipt],
                "omitted": [],
            },
        )
        if (
            provenance(receipt) != provenance(item)
            or receipt["byte_size"] != request["stamps"][item["name"]][2]
            or receipt["sha256"] != request["source_hashes"][item["name"]]
        ):
            raise ValueError("Captured receipt differs from the selected source")

    def capture(self, plan):
        """Snapshot or resume the same files; no adapter method is ever invoked."""
        plan = validate_plan(plan)
        deadline = time.monotonic() + self.timeout_seconds
        with self._locked() as root, self._job(root, plan["job_id"]) as job:
            request = self._request(job, plan)
            if _exists(job, "capture.json"):
                return self._inspect_job(job, plan, request, deadline)
            receipts = []
            for index, item in enumerate(request["sources"]):
                # Account for existing crash remnants and reserve remaining raw
                # bytes plus bounded journals before touching another source.
                remaining = 0
                for j, value in enumerate(request["sources"]):
                    if j < index or _exists(job, f"output-{j:02d}.json"):
                        continue
                    expected_size = request["stamps"][value["name"]][2]
                    partial = f"output-{j:02d}.partial"
                    existing_size = (
                        os.stat(partial, dir_fd=job, follow_symlinks=False).st_size
                        if _exists(job, partial)
                        else 0
                    )
                    if existing_size > expected_size:
                        raise ValueError("Uncommitted output exceeds its pinned size")
                    remaining += expected_size - existing_size
                self._capacity(root, plan["job_id"], remaining + LOCAL_METADATA_LIMIT)
                receipts.append(self._capture_one(job, request, item, index, deadline))
            selected = {item["name"] for item in receipts}
            result = validate_capture(
                plan,
                {
                    "schema": CAPTURE_SCHEMA,
                    "job_id": plan["job_id"],
                    "plan_digest": digest(plan),
                    "files": receipts,
                    "omitted": sorted(
                        item["name"]
                        for item in plan["outputs"]
                        if item["name"] not in selected
                    ),
                },
            )
            if _exists(job, "capture.json"):
                if _read_json(job, "capture.json") != result:
                    raise ValueError("Completed capture manifest changed")
            else:
                _write_json(job, "capture.json", result)
            return result

    def inspect(self, plan):
        """Rehash durable data independently of the source directory or equipment."""
        plan = validate_plan(plan)
        deadline = time.monotonic() + self.timeout_seconds
        with self._locked() as root, self._job(root, plan["job_id"]) as job:
            request = self._request(job, plan)
            return self._inspect_job(job, plan, request, deadline)

    def _inspect_job(self, job, plan, request, deadline):
        result = validate_capture(plan, _read_json(job, "capture.json"))
        if [value["name"] for value in result["files"]] != [
            value["name"] for value in request["sources"]
        ]:
            raise ValueError("Completed capture differs from the selected outputs")
        for index, (item, receipt) in enumerate(
            zip(request["sources"], result["files"], strict=True)
        ):
            self._validate_receipt(request, item, receipt)
            if _read_json(job, f"output-{index:02d}.json") != receipt:
                raise ValueError("Captured file receipt changed")
            self._verify(job, f"output-{index:02d}.bin", receipt, deadline)
        return result

    @contextmanager
    def open_output(self, plan, name):
        """Yield only a named, rehashed snapshot; never an adapter-provided path."""
        plan = validate_plan(plan)
        deadline = time.monotonic() + self.timeout_seconds
        with self._locked() as root, self._job(root, plan["job_id"]) as job:
            request = self._request(job, plan)
            result = validate_capture(plan, _read_json(job, "capture.json"))
            if [value["name"] for value in result["files"]] != [
                value["name"] for value in request["sources"]
            ]:
                raise ValueError("Completed capture differs from the selected outputs")
            index = next(
                (
                    index
                    for index, item in enumerate(result["files"])
                    if item["name"] == name
                ),
                None,
            )
            if index is None:
                raise ValueError("Output was not captured for this job")
            receipt = result["files"][index]
            self._validate_receipt(request, request["sources"][index], receipt)
            if _read_json(job, f"output-{index:02d}.json") != receipt:
                raise ValueError("Captured file receipt changed")
            with _private_file(job, f"output-{index:02d}.bin") as fd:
                before = _stamp(os.fstat(fd))
                if (
                    self._hash(fd, receipt["byte_size"], deadline)
                    != (receipt["sha256"], receipt["byte_size"])
                    or _stamp(os.fstat(fd)) != before
                ):
                    raise ValueError("Captured output no longer matches its digest")
                os.lseek(fd, 0, os.SEEK_SET)
                with os.fdopen(os.dup(fd), "rb") as stream:
                    yield receipt, stream
                if _stamp(os.fstat(fd)) != before:
                    raise ValueError("Captured output changed while being read")
