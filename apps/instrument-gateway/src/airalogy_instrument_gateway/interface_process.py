"""Pinned local Node interface worker, never a remote-control or sandbox boundary.

Use only from independently reviewed, installed adapters. The Gateway remains
responsible for signed jobs, authority, leases and the durable operation journal.
Terminating this process is NOT evidence of a physical safe stop.
"""

import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import UUID

from .credentials import _parent, read_private_json
from .package_contract import canonical, strict_json


class InterfaceProcessError(RuntimeError):
    def __init__(self, message, *, operation_may_have_started=False):
        super().__init__(message)
        self.operation_may_have_started = operation_may_have_started


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("Unexpected interface runtime fields")


def _path(value):
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError("Select a bounded absolute runtime path")
    path = Path(value)
    if not path.is_absolute() or str(path) != value:
        raise ValueError("Select a canonical absolute runtime path")
    return path


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Select an exact runtime SHA256")
    return value


def _private_bytes(path, limit):
    parent = _parent(path)
    try:
        fd = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
        )
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or info.st_nlink != 1
                or info.st_size > limit
            ):
                raise ValueError("Select a bounded owner-only worker document")
            raw = stream.read(limit + 1)
            if len(raw) > limit:
                raise ValueError("Worker document exceeded its bound")
            return raw
    finally:
        os.close(parent)


def _file(path, guard):
    guard()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o022
            or info.st_size > 536870912
        ):
            raise ValueError(
                "Runtime file is not bounded regular read-only-to-others content"
            )
        sha = hashlib.sha256()
        size = 0
        while chunk := source.read(1048576):
            guard()
            size += len(chunk)
            if size > 536870912:
                raise ValueError("Runtime file exceeded its bound")
            sha.update(chunk)
        after = os.fstat(source.fileno())
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(info, key) != getattr(after, key) for key in fields):
            raise ValueError("Runtime bytes changed while verifying")
        return {"size": size, "sha256": sha.hexdigest()}


def _verify_tree(tree, guard):
    _keys(tree, ("root", "exclude_node_modules", "files", "links"))
    root = _path(tree["root"])
    if root.resolve(strict=True) != root or tree["exclude_node_modules"] is not False:
        raise ValueError("Runtime tree root changed")
    if not isinstance(tree["files"], dict) or not isinstance(tree["links"], dict):
        raise TypeError("Invalid runtime tree inventory")
    files, links = {}, {}
    count, size = 0, 0

    def visit(path):
        nonlocal count, size
        guard()
        count += 1
        info = path.lstat()
        if count > 20000 or (info.st_mode & 0o022 and not stat.S_ISLNK(info.st_mode)):
            raise ValueError(
                "Runtime tree exceeds its bound or permits untrusted writes"
            )
        name = path.relative_to(root).as_posix()
        if stat.S_ISLNK(info.st_mode):
            if not path.resolve(strict=True).is_relative_to(root):
                raise ValueError("Runtime link leaves the selected tree")
            links[name] = os.readlink(path)
        elif stat.S_ISDIR(info.st_mode):
            with os.scandir(path) as entries:
                for entry in entries:
                    if not (
                        tree["exclude_node_modules"] and entry.name == "node_modules"
                    ):
                        visit(Path(entry.path))
        else:
            files[name] = _file(path, guard)
            size += files[name]["size"]
            if size > 2147483648:
                raise ValueError("Runtime tree exceeds 2 GiB")

    visit(root)
    if files != tree["files"] or links != tree["links"]:
        raise ValueError("Installed interface runtime contents changed")
    return root


def verify_runtime(config, *, guard=lambda: None):
    return _verify_runtime(config, guard=guard, native_read=False)


def verify_native_read_runtime(config, *, guard=lambda: None):
    return _verify_runtime(config, guard=guard, native_read=True)


def _verify_runtime(config, *, guard, native_read):
    prefix = "native-read-worker" if native_read else "interface-worker"
    _keys(config, ("schema", "runtime_file", "runtime_sha256"))
    if (
        os.name != "posix"
        or (native_read and sys.platform != "darwin")
        or config["schema"] != f"airalogy.{prefix}-config.v1"
    ):
        raise ValueError("Select a supported private interface worker configuration")
    path = _path(config["runtime_file"])
    raw = _private_bytes(path, 2097152)
    if hashlib.sha256(raw).hexdigest() != _hash(config["runtime_sha256"]):
        raise ValueError("Worker runtime manifest changed")
    value = strict_json(raw)
    _keys(
        value,
        (
            "schema",
            "node",
            "entry",
            *(("native_build",) if native_read else ("browser",)),
            "package",
            "trees",
            "resolutions",
            "unavailable",
            "definition" if native_read else "workflow",
            "evidence_root",
        ),
    )
    if (
        value["schema"] != f"airalogy.{prefix}-runtime.v1"
        or not isinstance(value["trees"], list)
        or not 3 <= len(value["trees"]) <= 32
        or not isinstance(value["resolutions"], list)
        or len(value["resolutions"]) > 64
    ):
        raise ValueError("Invalid worker runtime inventory")
    roots = [_verify_tree(tree, guard) for tree in value["trees"]]
    if len(set(roots)) != len(roots):
        raise ValueError("Duplicate runtime trees")
    for resolution in value["resolutions"]:
        _keys(resolution, ("path", "target"))
        target = _path(resolution["target"])
        if (
            target not in roots
            or _path(resolution["path"]).resolve(strict=True) != target
        ):
            raise ValueError("Node dependency resolution changed")
    if not isinstance(value["unavailable"], list) or len(value["unavailable"]) > 64:
        raise ValueError("Invalid absent dependency inventory")
    for paths in value["unavailable"]:
        if not isinstance(paths, list) or not 1 <= len(paths) <= 32:
            raise ValueError("Invalid absent dependency lookup paths")
        for path in paths:
            selected = _path(path)
            if selected.exists() or selected.is_symlink():
                raise ValueError("Previously absent dependency lookup changed")
    for field in ("node", "package"):
        pin = value[field]
        _keys(pin, ("path", "size", "sha256"))
        selected = _path(pin["path"])
        if selected.resolve(strict=True) != selected or _file(selected, guard) != {
            key: pin[key] for key in ("size", "sha256")
        }:
            raise ValueError("Runtime executable or package metadata changed")
    entry = "native-read-worker.mjs" if native_read else "worker.mjs"
    if (
        _path(value["entry"]) != roots[0] / entry
        or entry not in value["trees"][0]["files"]
    ):
        raise ValueError("Select the exact inventoried worker")
    if native_read:
        if _path(value["native_build"]) != roots[-1] / "native-build.json" or not {
            "native-build.json",
            "helper",
            "main.swift",
        }.issubset(value["trees"][-1]["files"]):
            raise ValueError("Select the exact inventoried native helper build")
    elif (
        not _path(value["browser"]).is_relative_to(roots[-1])
        or _path(value["browser"]).relative_to(roots[-1]).as_posix()
        not in value["trees"][-1]["files"]
        or value["browser"] != str(_path(value["browser"]).resolve(strict=True))
    ):
        raise ValueError("Select the exact inventoried worker and browser")
    digest_field = "definition_digest" if native_read else "workflow_digest"
    selection = value["definition" if native_read else "workflow"]
    _keys(selection, ("path", "sha256", digest_field))
    selected = _private_bytes(
        _path(selection["path"]), 131072 if native_read else 524288
    )
    document = strict_json(selected)
    if not isinstance(document, dict):
        raise TypeError("Select a reviewed interface document")
    selected_digest = (
        hashlib.sha256(canonical(document)).hexdigest()
        if native_read
        else document.get("sha256")
    )
    if hashlib.sha256(selected).hexdigest() != _hash(
        selection["sha256"]
    ) or selected_digest != _hash(selection[digest_field]):
        raise ValueError("Reviewed interface document changed")
    if native_read and (
        document.get("schema") != "airalogy.native-read-definition.v1"
        or not isinstance(document.get("selection"), dict)
        or document.get("selection", {}).get("build_file") != value["native_build"]
    ):
        raise ValueError("Native worker requires its exact read-only definition")
    evidence = _path(value["evidence_root"])
    info = evidence.lstat()
    if (
        evidence.resolve(strict=True) != evidence
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("Worker evidence location changed")
    return value


def _terminate(child, *, force=False):
    # This reaps the local process group only, never certifies equipment safety.
    if force or child.poll() is None:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=3)


class InterfaceProcessClient:
    """One-shot trusted worker with no shell, shared profile or automatic retry."""

    _schema_prefix = "interface-worker"
    _selection_field = "workflow"
    _digest_field = "workflow_digest"

    def _verify(self, guard):
        return verify_runtime(self.config, guard=guard)

    def __init__(self, config):
        self.config = json.loads(json.dumps(config))
        self._lock = threading.Lock()
        self._attempted_jobs = set()

    @classmethod
    def from_file(cls, path):
        return cls(read_private_json(Path(path), strict=True))

    def call(self, operation, *, job_id=None, timeout_seconds=4, stop_event=None):
        if (
            operation not in ("probe", "execute")
            or (operation == "probe" and job_id is not None)
            or (
                operation == "execute"
                and (not isinstance(job_id, str) or str(UUID(job_id)) != job_id)
            )
        ):
            raise ValueError(
                "Select one fixed interface operation with its exact Job UUID"
            )
        if (
            type(timeout_seconds) not in (int, float)
            or not 0.1 <= timeout_seconds <= 300
        ):
            raise ValueError("Select a bounded interface operation deadline")
        if not self._lock.acquire(blocking=False):
            raise InterfaceProcessError("Concurrent interface operations are refused")
        deadline = time.monotonic() + timeout_seconds
        child = None
        completed = False

        def guard():
            if time.monotonic() >= deadline or (
                stop_event is not None and stop_event.is_set()
            ):
                raise InterfaceProcessError(
                    "Interface cancelled or deadline exceeded",
                    operation_may_have_started=child is not None,
                )

        try:
            if operation == "execute" and job_id in self._attempted_jobs:
                raise InterfaceProcessError("Do not replay an attempted interface job")
            runtime = self._verify(guard)
            request = {
                "schema": f"airalogy.{self._schema_prefix}-request.v1",
                "operation": operation,
                "job_id": job_id,
                "runtime_file": self.config["runtime_file"],
                "runtime_sha256": self.config["runtime_sha256"],
                self._digest_field: runtime[self._selection_field][self._digest_field],
            }
            payload = json.dumps(request, separators=(",", ":")).encode()
            if len(payload) > 8192:
                raise ValueError("Worker request exceeds its bound")
            guard()
            if operation == "execute":
                self._attempted_jobs.add(job_id)
            child = subprocess.Popen(
                [runtime["node"]["path"], runtime["entry"]],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=runtime["evidence_root"],
                env={
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "HOME": runtime["evidence_root"],
                    "TMPDIR": runtime["evidence_root"],
                },
                start_new_session=True,
            )
            streams = {child.stdout: bytearray(), child.stderr: bytearray()}
            with selectors.DefaultSelector() as selector:
                os.set_blocking(child.stdin.fileno(), False)
                selector.register(child.stdin, selectors.EVENT_WRITE)
                sent = 0
                for stream in streams:
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ)
                while selector.get_map():
                    guard()
                    for key, _ in selector.select(
                        min(0.05, max(0, deadline - time.monotonic()))
                    ):
                        if key.fileobj is child.stdin:
                            sent += os.write(
                                child.stdin.fileno(), payload[sent : sent + 4096]
                            )
                            if sent == len(payload):
                                selector.unregister(child.stdin)
                                child.stdin.close()
                            continue
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        else:
                            streams[key.fileobj].extend(chunk)
                            if len(streams[key.fileobj]) > 65536:
                                raise InterfaceProcessError(
                                    "Worker output exceeded its bound",
                                    operation_may_have_started=True,
                                )
            guard()
            if child.wait(timeout=max(0.01, deadline - time.monotonic())) != 0:
                raise InterfaceProcessError(
                    "Worker failed; inspect private evidence without replay",
                    operation_may_have_started=True,
                )
            value = strict_json(bytes(streams[child.stdout]))
            _keys(
                value,
                (
                    "schema",
                    "operation",
                    "job_id",
                    "runtime_sha256",
                    self._digest_field,
                    "data",
                    "hardware_qualified",
                ),
            )
            if (
                value["schema"] != f"airalogy.{self._schema_prefix}-response.v1"
                or any(
                    value[key] != request[key]
                    for key in (
                        "operation",
                        "job_id",
                        "runtime_sha256",
                        self._digest_field,
                    )
                )
                or value["hardware_qualified"] is not False
                or not isinstance(value["data"], dict)
            ):
                raise ValueError("Worker response does not match its exact request")
            completed = True
            return value
        except InterfaceProcessError:
            raise
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            subprocess.SubprocessError,
        ) as error:
            raise InterfaceProcessError(
                "Interface runtime verification or execution failed",
                operation_may_have_started=child is not None,
            ) from error
        finally:
            try:
                if child is not None:
                    try:
                        _terminate(child, force=not completed)
                    except (OSError, subprocess.SubprocessError) as error:
                        raise InterfaceProcessError(
                            "Local process cleanup could not be confirmed; reconcile without replay",
                            operation_may_have_started=True,
                        ) from error
                    finally:
                        for stream in (child.stdin, child.stdout, child.stderr):
                            stream.close()
            finally:
                self._lock.release()


class NativeReadProcessClient(InterfaceProcessClient):
    """Read-only macOS helper transport, with no application launch or UI actions."""

    _schema_prefix = "native-read-worker"
    _selection_field = "definition"
    _digest_field = "definition_digest"

    def _verify(self, guard):
        return verify_native_read_runtime(self.config, guard=guard)
