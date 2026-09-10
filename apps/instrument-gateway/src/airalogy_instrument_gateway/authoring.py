"""Bounded source author: immutable selected inputs, remote proposals, local sandbox.

Never imports generated source, loads a driver, reads execution credentials or
launches instrument software. The private authoring journal is NOT a Gateway journal.
"""

import os
import re
import secrets
import ssl
import stat
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener
from uuid import UUID, uuid4

from .authoring_contract import (
    REQUEST_SCHEMA,
    candidate_digest,
    fingerprint,
    validate_proposal,
    validate_request,
    validate_spec,
)
from .client import GatewayAPIError, _RejectRedirects
from .config import validate_platform_url
from .credentials import read_private_json
from .package_builder import build_package
from .package_cli import read_selected
from .package_contract import canonical, sha256, strict_json
from .package_installation import _private_root
from .package_sandbox import reconcile_sandbox, sandbox_name, test_package
from .state import StateStore


def prepare(
    *,
    workspace,
    platform_url,
    gateway_id,
    resource_id,
    spec,
    sdk_wheel,
    trusted_sdk_digest,
    image,
    max_iterations=3,
    duration_seconds=900,
    timeout_seconds=60,
    expected_preview_digest=None,
):
    preview = prepare_preview(
        workspace=workspace,
        platform_url=platform_url,
        gateway_id=gateway_id,
        resource_id=resource_id,
        spec=spec,
        sdk_wheel=sdk_wheel,
        trusted_sdk_digest=trusted_sdk_digest,
        image=image,
        max_iterations=max_iterations,
        duration_seconds=duration_seconds,
        timeout_seconds=timeout_seconds,
    )
    if (
        expected_preview_digest is not None
        and preview["preview_digest"] != expected_preview_digest
    ):
        raise ValueError("Authoring inputs changed after preview")
    parent = Path(preview["workspace"])
    token = "aiauthor_" + secrets.token_urlsafe(32)
    request = {
        **preview["request_template"],
        "id": str(uuid4()),
        "credential_digest": sha256(token.encode()),
    }
    request["fingerprint"] = fingerprint(request)
    validate_request(request)
    content = {
        "schema": "airalogy.private-authoring.v1",
        "request": request,
        "platform_url": preview["platform_url"],
        "authoring_token": token,
        "sdk_wheel": preview["sdk_wheel"],
    }
    root = parent / request["id"]
    root.mkdir(mode=0o700)
    _save(root / "request.json", canonical(content))
    # Bearer-free, not public: selected manuals/source/tests remain private Lab data.
    _save(root / "authorization.json", canonical(request))
    return {
        "request_file": str(root / "request.json"),
        "authorization_file": str(root / "authorization.json"),
        "fingerprint": request["fingerprint"],
        "hardware_authorized": False,
    }


def prepare_preview(
    *,
    workspace,
    platform_url,
    gateway_id,
    resource_id,
    spec,
    sdk_wheel,
    trusted_sdk_digest,
    image,
    max_iterations=3,
    duration_seconds=900,
    timeout_seconds=60,
):
    """Inspect selected inputs without credentials, writes, network or code import."""
    parent = _private_root(Path(workspace))
    spec = validate_spec(strict_json(read_selected(Path(spec), limit=131072)))
    if sha256(read_selected(Path(sdk_wheel))) != trusted_sdk_digest:
        raise ValueError("Selected SDK does not match its independent digest")
    request = {
        "schema": REQUEST_SCHEMA,
        "id": "00000000-0000-4000-8000-000000000001",
        "gateway_id": str(UUID(gateway_id)),
        "resource_id": str(UUID(resource_id)),
        "credential_digest": "0" * 64,
        "spec": spec,
        "max_iterations": max_iterations,
        "duration_seconds": duration_seconds,
        "sandbox": {
            "sdk_digest": trusted_sdk_digest,
            "image": image,
            "timeout_seconds": timeout_seconds,
        },
    }
    request["fingerprint"] = fingerprint(request)
    validate_request(request)
    for key in ("id", "credential_digest", "fingerprint"):
        request.pop(key)
    content = {
        "workspace": str(parent),
        "request_template": request,
        "platform_url": validate_platform_url(platform_url),
        "sdk_wheel": str(Path(sdk_wheel).absolute()),
    }
    return {
        **content,
        "preview_digest": sha256(canonical(content)),
        "hardware_authorized": False,
    }


def read_request(path):
    path = Path(path).absolute()
    root = _private_root(path.parent)
    content = read_private_json(path, max_bytes=262144)
    if content.get("schema") != "airalogy.private-authoring.v1":
        raise ValueError(
            "Use a separate authoring request, not runtime/installation credentials"
        )
    request = validate_request(content["request"])
    token = content.get("authoring_token", "")
    if (
        not isinstance(token, str)
        or not re.fullmatch(r"aiauthor_[A-Za-z0-9_-]{43}", token)
        or sha256(token.encode()) != request["credential_digest"]
    ):
        raise ValueError("Authoring credential differs from its request")
    if root.name != request["id"]:
        raise ValueError("Keep the authoring request in its original session directory")
    validate_platform_url(content["platform_url"])
    return content


class AuthoringClient:
    def __init__(self, content):
        self.url = validate_platform_url(content["platform_url"])
        self.token = content["authoring_token"]
        self.id = str(UUID(content["request"]["id"]))
        handlers = [
            _RejectRedirects(),
            HTTPSHandler(context=ssl.create_default_context()),
        ]
        if urlparse(self.url).hostname in {"localhost", "127.0.0.1", "::1"}:
            handlers.append(ProxyHandler({}))
        self.opener = build_opener(*handlers)

    def call(self, operation, payload=None, *, turn_id=None):
        if operation not in {"status", "turns", "report"}:
            raise ValueError("Unsupported source-authoring operation")
        suffix = (
            f"turns/{UUID(str(turn_id))}/report" if operation == "report" else operation
        )
        request = Request(
            f"{self.url}/instrument-authoring/{self.id}/{suffix}",
            data=canonical(payload or {}),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Airalogy-Authoring-Token": self.token,
            },
        )
        deadline, raw = time.monotonic() + 75, bytearray()
        try:
            with self.opener.open(request, timeout=70) as response:
                while True:
                    chunk = response.read1(min(65536, 1048577 - len(raw)))
                    raw.extend(chunk)
                    if len(raw) > 1048576 or time.monotonic() > deadline:
                        raise GatewayAPIError("Authoring response exceeded its limit")
                    if not chunk:
                        break
        except HTTPError as error:
            error.close()
            raise GatewayAPIError(
                f"Authoring request rejected (HTTP {error.code}); review Platform status",
                status=error.code,
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise GatewayAPIError(
                "Authoring connection lost; retain the request and resume the same attempt"
            ) from error
        result = strict_json(bytes(raw))
        if not isinstance(result, dict):
            raise GatewayAPIError("Authoring response must be an object")
        return result


def _blob(path):
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or info.st_nlink != 1
    ):
        raise ValueError("Authoring artifacts must remain private regular files")
    return read_selected(path)


def _save(path, raw):
    """Publish a complete immutable artifact; retries verify, never overwrite."""
    if path.exists() or path.is_symlink():
        if _blob(path) != raw:
            raise ValueError("A saved authoring artifact changed; reconcile manually")
        return
    fd, temporary = tempfile.mkstemp(prefix=".pending-author-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(raw)
            target.flush()
            os.fsync(target.fileno())
        os.link(temporary, path, follow_symlinks=False)
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        os.unlink(temporary)


def _open(status, request):
    if status.get("request") != request:
        raise ValueError(
            "Platform authorization differs from the selected local inputs"
        )
    expires = datetime.fromisoformat(status["expires_at"])
    return status.get("effective_state") == "open" and expires > datetime.now(UTC)


def _report(request, turn, *, phase, archive=None, passed=False, reason="", output=""):
    return {
        "candidate_digest": turn["candidate_digest"],
        "archive_digest": archive,
        "phase": phase,
        "sdk_digest": request["sandbox"]["sdk_digest"],
        "image": request["sandbox"]["image"],
        "passed": passed,
        "failure_reason": reason,
        "untrusted_test_output": output[:8000],
    }


def _test_turn(root, request, turn, sdk, *, tester, reconcile, expires_at):
    turn_id = str(UUID(turn["id"]))
    proposal = validate_proposal(turn["proposal"], request["spec"])
    if candidate_digest(request["spec"], proposal) != turn["candidate_digest"]:
        raise ValueError("Proposal differs from its immutable candidate identity")
    _save(root / f"{turn_id}.proposal.json", canonical(proposal))
    if proposal["missing_information"]:
        return None
    report_path = root / f"{turn_id}.report.json"
    if report_path.exists():
        report = strict_json(_blob(report_path))
        if report != _report(
            request,
            turn,
            phase=report["phase"],
            archive=report["archive_digest"],
            passed=report["passed"],
            reason=report["failure_reason"],
            output=report["untrusted_test_output"],
        ):
            raise ValueError("Saved test report differs from this candidate")
        if (
            report["archive_digest"]
            and sha256(_blob(root / f"{turn_id}.zip")) != report["archive_digest"]
        ):
            raise ValueError("Saved package differs from its report")
        return report
    spec = request["spec"]
    try:
        raw, _ = build_package(
            spec["manifest"],
            factory=spec["factory"],
            payloads={
                name: value.encode()
                for mapping in (proposal["sources"], spec["tests"], spec["licenses"])
                for name, value in mapping.items()
            },
        )
    except ValueError as error:
        report = _report(
            request, turn, phase="build", reason="package_build", output=str(error)
        )
        _save(report_path, canonical(report))
        return report
    _save(root / f"{turn_id}.zip", raw)
    marker = root / f"{turn_id}.sandbox.json"
    if marker.exists():
        saved = strict_json(_blob(marker))
        if saved != {"invocation_id": turn_id, "archive_digest": sha256(raw)}:
            raise ValueError("Sandbox journal identity changed")
        if not reconcile:
            raise ValueError(
                f"Previous test is uncertain ({sandbox_name(turn_id)}); use --reconcile-test to stop only this test and record failure before continuing"
            )
        reconcile_sandbox(turn_id)
        report = _report(
            request,
            turn,
            phase="sandbox",
            archive=sha256(raw),
            reason="local_test_interrupted",
        )
    else:
        remaining = int(
            (datetime.fromisoformat(expires_at) - datetime.now(UTC)).total_seconds()
        )
        if remaining < 1:
            raise ValueError("Authoring expired before the local test could start")
        _save(
            marker, canonical({"invocation_id": turn_id, "archive_digest": sha256(raw)})
        )
        result = tester(
            raw,
            sdk_wheel=sdk,
            trusted_sdk_digest=request["sandbox"]["sdk_digest"],
            image=request["sandbox"]["image"],
            timeout_seconds=min(request["sandbox"]["timeout_seconds"], remaining),
            invocation_id=turn_id,
        )
        if (
            result["archive_digest"] != sha256(raw)
            or result["sdk_digest"] != request["sandbox"]["sdk_digest"]
            or result["image"] != request["sandbox"]["image"]
        ):
            raise ValueError("Sandbox report identity changed")
        report = _report(
            request,
            turn,
            phase="sandbox",
            archive=sha256(raw),
            passed=result["passed"],
            reason=result["failure_reason"] or "",
            output=result["untrusted_test_output"],
        )
    _save(report_path, canonical(report))
    return report


def run(
    path,
    *,
    client=None,
    tester=test_package,
    reconcile=False,
    reconcile_turn_ids=None,
    pause_requested=lambda: False,
    progress=lambda phase: None,
):
    content = read_request(path)
    root, request = Path(path).absolute().parent, content["request"]
    client = client or AuthoringClient(content)
    sdk = read_selected(Path(content["sdk_wheel"]))
    if sha256(sdk) != request["sandbox"]["sdk_digest"]:
        raise ValueError("SDK changed; authoring cannot continue")
    with StateStore(root / "authoring.json").exclusive():
        for _ in range(request["max_iterations"] + 1):
            if pause_requested():
                return {"state": "locally_paused", "hardware_authorized": False}
            progress("checking_authorization")
            status = client.call("status")
            active = _open(status, request)
            turns = status["turns"]
            if len(turns) > request["max_iterations"] or [
                t["ordinal"] for t in turns
            ] != list(range(1, len(turns) + 1)):
                raise ValueError("Authoring attempt sequence changed")
            turn = turns[-1] if turns else None
            if turn and turn["state"] == "generated":
                if (
                    not active
                    and not (root / f"{UUID(turn['id'])}.report.json").exists()
                    and not (
                        reconcile
                        and (root / f"{UUID(turn['id'])}.sandbox.json").exists()
                    )
                ):
                    return {
                        "state": "authorization_ended",
                        "hardware_authorized": False,
                    }
                if pause_requested():
                    return {"state": "locally_paused", "hardware_authorized": False}
                if (
                    reconcile
                    and reconcile_turn_ids is not None
                    and (root / f"{UUID(turn['id'])}.sandbox.json").exists()
                    and not (root / f"{UUID(turn['id'])}.report.json").exists()
                    and turn["id"] not in reconcile_turn_ids
                ):
                    raise ValueError(
                        "Interrupted test was not included in the confirmed preview"
                    )
                progress("checking_or_testing_candidate")
                report = _test_turn(
                    root,
                    request,
                    turn,
                    sdk,
                    tester=tester,
                    reconcile=reconcile,
                    expires_at=status["expires_at"],
                )
                if report is None:
                    return {
                        "state": "needs_information",
                        "questions": turn["proposal"]["missing_information"],
                        "hardware_authorized": False,
                    }
                progress("confirming_test_receipt")
                result = client.call("report", report, turn_id=turn["id"])
                if result.get("turn", {}).get("report") != report:
                    raise GatewayAPIError(
                        "Test receipt not confirmed; resume without repeating the test"
                    )
                if report["passed"]:
                    return {
                        "state": "draft_tested",
                        "package": str(root / f"{UUID(turn['id'])}.zip"),
                        "report": str(root / f"{UUID(turn['id'])}.report.json"),
                        "hardware_authorized": False,
                        "next_step": "Independent source review and separate Platform import/install/qualification",
                    }
            elif turn and turn["effective_state"] == "generating":
                return {"state": "model_in_progress", "hardware_authorized": False}
            if not active:
                return {"state": "authorization_ended", "hardware_authorized": False}
            if len(turns) >= request["max_iterations"]:
                return {"state": "budget_exhausted", "hardware_authorized": False}
            call_path = root / f"call-{len(turns) + 1}.json"
            call = (
                strict_json(_blob(call_path))
                if call_path.exists()
                else {"id": str(uuid4()), "previous_id": turn["id"] if turn else None}
            )
            if call["previous_id"] != (turn["id"] if turn else None):
                raise ValueError("Saved model attempt differs from remote history")
            _save(call_path, canonical(call))
            if pause_requested():
                return {"state": "locally_paused", "hardware_authorized": False}
            progress("requesting_source")
            client.call(
                "turns", call
            )  # Status, not this possibly lost response, is authoritative.
    raise ValueError("Unexpected authoring iteration state")
