"""Local setup orchestration. No driver imports, startup, shell or model calls.

The browser receives only public enrollment/install documents. Runtime and
installer credentials remain in exclusive owner-only files in the selected root.
Existing pairing and installation implementations remain the authority boundary.
"""

import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import ClassVar
from uuid import UUID, uuid4

from .config import validate_platform_url
from .credentials import read_credentials, read_private_json, write_credentials
from .installation_manager import (
    InstallationClient,
    _inputs,
    apply,
    prepare,
    read_request,
)
from .package_cli import read_selected
from .package_contract import MAX_ARCHIVE_BYTES, canonical, sha256
from .package_installation import _private_root, installation_preview
from .pairing_cli import _client, claim


def fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValueError("Missing or unexpected setup fields")


def text(value, limit=4096):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("Enter a bounded, single-line value")
    return value.strip()


def selected_path(value):
    path = Path(text(value))
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Select an absolute path without parent traversal")
    return path


class SetupWorkspace:
    ui_directory = "setup_ui"
    upload_limits: ClassVar = {
        "package": MAX_ARCHIVE_BYTES,
        "sdk_wheel": MAX_ARCHIVE_BYTES,
        "config": 16384,
    }

    def __init__(self, root):
        self.root = _private_root(Path(root))
        info = self.root.stat()
        self.root_identity = (info.st_dev, info.st_ino)
        self.pending = {}
        self.lock = threading.Lock()

    def _check_root(self):
        info = _private_root(self.root).stat()
        if (info.st_dev, info.st_ino) != self.root_identity:
            raise ValueError("Workstation directory changed; stop and inspect it")

    def upload(self, kind, raw):
        if kind not in self.upload_limits:
            raise ValueError("Unsupported setup file")
        limit = self.upload_limits[kind]
        if not raw or len(raw) > limit:
            raise ValueError("Selected file exceeded its size limit")
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("Another setup operation is running")
        try:
            self._check_root()
            directory = self.root / "setup-inputs"
            directory.mkdir(mode=0o700, exist_ok=True)
            _private_root(directory)
            total = count = 0
            with os.scandir(directory) as entries:
                for entry in entries:
                    count += 1
                    total += entry.stat(follow_symlinks=False).st_size
                    if count >= 64 or total + len(raw) > 256 * 1024 * 1024:
                        raise ValueError(
                            "Local setup copy quota exceeded; inspect retained files before cleanup"
                        )
            path = directory / f"{kind}-{uuid4().hex}"
            fd = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(fd, "wb") as target:
                target.write(raw)
                target.flush()
                os.fsync(target.fileno())
            directory_fd = os.open(
                directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return {"path": str(path), "bytes": len(raw), "sha256": sha256(raw)}
        finally:
            self.lock.release()

    def _credentials(self):
        value = read_credentials(self.root / "gateway.json")
        validate_platform_url(value["platform_url"])
        UUID(value["lab_id"])
        UUID(value["gateway_id"])
        text(value["client_name"], 200)
        return value

    @staticmethod
    def _scope(value):
        return {
            key: value[key]
            for key in ("platform_url", "lab_id", "gateway_id", "client_name")
        }

    def _scope_pin(self):
        # Pin the local identity too; a concurrent credential replacement must
        # invalidate confirmation without putting the token in a browser response.
        return sha256(canonical(self._credentials()))

    def _offer(self, kind, data, details):
        now = time.monotonic()
        self.pending = {
            key: item for key, item in self.pending.items() if item[2] > now
        }
        if len(self.pending) >= 8:
            self.pending.pop(next(iter(self.pending)))
        confirmation = secrets.token_urlsafe(32)
        self.pending[confirmation] = (kind, data, now + 300)
        return {
            "confirmation": confirmation,
            "expires_in_seconds": 300,
            "impact": details,
        }

    def _consume(self, kind, value):
        fields(value, ["confirmation"])
        item = self.pending.pop(text(value["confirmation"], 100), None)
        if item is None or item[0] != kind or item[2] <= time.monotonic():
            raise ValueError("Preview expired or already used; review a fresh preview")
        return item[1]

    def _request(self, local_id):
        name = str(UUID(text(local_id, 36)))
        path = self.root / f"installation-{name}.json"
        value = read_request(path)
        scope = self._credentials()
        if (
            value["root"] != str(self.root)
            or value["platform_url"] != scope["platform_url"]
            or any(
                value["request"][key] != scope[key] for key in ("lab_id", "gateway_id")
            )
        ):
            raise ValueError(
                "Saved request belongs to another workstation or Platform scope"
            )
        return path, value

    def state(self):
        scope = (
            self._scope(self._credentials())
            if (self.root / "gateway.json").exists()
            else None
        )
        requests, pairings = [], []
        # Only assistant-owned, exact-named metadata in the explicitly selected
        # private directory. Never inspect adjacent workstation directories.
        with os.scandir(self.root) as entries:
            for count, entry in enumerate(entries):
                if count >= 1000:
                    raise ValueError(
                        "Too many workstation entries; use the existing CLI to inspect this directory"
                    )
                match = re.fullmatch(
                    r"(installation|pairing)-([a-f0-9-]{36})\.json", entry.name
                )
                if not match:
                    continue
                kind, local_id = match.groups()
                if kind == "installation":
                    _path, value = self._request(local_id)
                    requests.append({"local_id": local_id, "request": value["request"]})
                else:
                    value = read_private_json(self.root / entry.name, strict=True)
                    if (
                        scope is None
                        or value.get("scope") != scope
                        or str(UUID(value["pairing_id"])) != local_id
                    ):
                        raise ValueError("Saved pairing belongs to another scope")
                    pairings.append(
                        {"id": local_id, "fingerprint": text(value["fingerprint"], 64)}
                    )
        return {
            "root": str(self.root),
            "scope": scope,
            "requests": requests,
            "pairings": pairings,
            "hardware_authorized": False,
            "activation_performed": False,
        }

    def dispatch(self, operation, data):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError(
                "Another setup operation is still running; refresh after it completes"
            )
        try:
            self._check_root()
            return self._dispatch(operation, data)
        finally:
            self.lock.release()

    def _dispatch(self, operation, data):
        if operation == "state":
            fields(data, [])
            return self.state()
        if operation == "identity-preview":
            fields(data, ["platform_url", "lab_id", "gateway_id", "client_name"])
            if (self.root / "gateway.json").exists():
                raise ValueError(
                    "A saved Gateway identity already exists; reuse it, do not overwrite it"
                )
            scope = {
                "platform_url": validate_platform_url(text(data["platform_url"])),
                "lab_id": str(UUID(text(data["lab_id"], 36))),
                "gateway_id": str(UUID(text(data["gateway_id"], 36))),
                "client_name": text(data["client_name"], 200),
            }
            return self._offer(
                "identity",
                scope,
                {
                    **scope,
                    "credential_file": str(self.root / "gateway.json"),
                    "network_request": False,
                },
            )
        if operation == "identity-confirm":
            scope = self._consume("identity", data)
            write_credentials(
                self.root / "gateway.json",
                {
                    "schema": "airalogy.gateway-credential.v1",
                    **scope,
                    "gateway_token": "aigw_" + secrets.token_urlsafe(32),
                },
            )
            return self.state()
        if operation == "pair":
            fields(data, ["code"])
            credentials = self._credentials()
            result = claim(credentials, text(data["code"], 256))
            pairing_id = str(UUID(result["id"]))
            saved = {
                "scope": self._scope(credentials),
                "pairing_id": pairing_id,
                "fingerprint": result["fingerprint"],
            }
            path = self.root / f"pairing-{pairing_id}.json"
            if path.exists():
                if read_private_json(path, strict=True) != saved:
                    raise ValueError(
                        "Pairing receipt changed; inspect the existing identity"
                    )
            else:
                write_credentials(path, saved)
            return {
                "id": pairing_id,
                "fingerprint": saved["fingerprint"],
                "approval_required": True,
            }
        if operation == "pairing-status":
            fields(data, ["id"])
            pairing_id = str(UUID(text(data["id"], 36)))
            saved = read_private_json(
                self.root / f"pairing-{pairing_id}.json", strict=True
            )
            credentials = self._credentials()
            if saved["scope"] != self._scope(credentials):
                raise ValueError("Pairing scope changed")
            result = _client(credentials).pairing_status(pairing_id)
            if (
                result.get("fingerprint") != saved["fingerprint"]
                or result.get("gateway_id") != credentials["gateway_id"]
            ):
                raise ValueError("Pairing response does not match this workstation")
            return {
                "id": pairing_id,
                "fingerprint": saved["fingerprint"],
                "state": text(result["state"], 40),
            }
        if operation == "installation-preview":
            fields(data, ["package", "sdk_wheel", "trusted_sdk_digest", "config"])
            scope_pin = self._scope_pin()
            paths = {
                key: str(selected_path(data[key]))
                for key in ("package", "sdk_wheel", "config")
            }
            inputs = {
                **paths,
                "root": str(self.root),
                "trusted_sdk_digest": text(data["trusted_sdk_digest"], 64),
            }
            preview = installation_preview(
                read_selected(Path(paths["package"])), **_inputs(inputs)
            )
            return self._offer(
                "installation",
                {"inputs": inputs, "preview": preview, "scope_pin": scope_pin},
                {
                    **preview,
                    "selection": paths,
                    "scope": self._scope(self._credentials()),
                },
            )
        if operation == "installation-confirm":
            selected = self._consume("installation", data)
            if selected["scope_pin"] != self._scope_pin():
                raise ValueError("Gateway identity changed after preview")
            scope = self._scope(self._credentials())
            scope.pop("client_name")
            local_id = str(uuid4())
            request = prepare(
                destination=self.root / f"installation-{local_id}.json",
                **scope,
                **selected["inputs"],
                expected_preview_digest=selected["preview"]["preview_digest"],
            )
            return {"local_id": local_id, "request": request, "approval_required": True}
        if operation == "installation-status":
            fields(data, ["local_id"])
            _path, value = self._request(data["local_id"])
            status = InstallationClient(value).call("status")
            if (
                status.get("descriptor") != value["request"]["descriptor"]
                or status.get("installer_fingerprint")
                != value["request"]["fingerprint"]
            ):
                raise ValueError(
                    "Platform installation identity differs from the local request"
                )
            if status.get("state") not in {
                "authorized",
                "installing",
                "installed",
                "expired",
                "revoked",
            }:
                raise ValueError("Unrecognized Platform installation state")
            return self._offer(
                "apply",
                {
                    "local_id": data["local_id"],
                    "scope_pin": self._scope_pin(),
                    "fingerprint": value["request"]["fingerprint"],
                },
                {
                    "state": status["state"],
                    "request": value["request"],
                    "root": str(self.root),
                    "hardware_authorized": False,
                    "activation_performed": False,
                },
            )
        if operation == "installation-apply":
            fields(data, ["confirmation", "source_reviewed"])
            if data["source_reviewed"] is not True:
                raise ValueError(
                    "Confirm local source/dependency review before installation"
                )
            selected = self._consume("apply", {"confirmation": data["confirmation"]})
            path, value = self._request(selected["local_id"])
            if (
                selected["scope_pin"] != self._scope_pin()
                or selected["fingerprint"] != value["request"]["fingerprint"]
            ):
                raise ValueError("Local scope changed after preview")
            return apply(path, source_reviewed=True)
        raise ValueError("Unsupported setup operation")
