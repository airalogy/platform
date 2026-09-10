"""Private local development UI, independent of setup/runtime credentials.

Only the already bounded authoring coordinator can run. No shell, driver import,
device API, arbitrary artifact path, installation or remote desktop endpoint.
"""

import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar
from uuid import UUID, uuid4

from . import authoring
from .authoring_contract import candidate_digest, source_review, validate_proposal
from .package_contract import MAX_ARCHIVE_BYTES, canonical, sha256, strict_json
from .package_sandbox import sandbox_name
from .setup_cli import LocalDownload
from .setup_workspace import SetupWorkspace, fields, selected_path, text


class AuthoringWorkspace(SetupWorkspace):
    ui_directory = "authoring_ui"
    upload_limits: ClassVar = {"spec": 131072, "sdk_wheel": MAX_ARCHIVE_BYTES}

    def __init__(self, root):
        super().__init__(root)
        self.worker = None
        self.stop = threading.Event()
        self.job = None
        self._check_root()

    def _check_root(self):
        super()._check_root()
        if any(
            (self.root / name).exists() or (self.root / name).is_symlink()
            for name in ("gateway.json", "state.json")
        ):
            raise ValueError(
                "Use a separate development directory, not the runtime journal or credentials"
            )

    def _request(self, session_id):
        session_id = str(UUID(text(session_id, 36)))
        path = self.root / session_id / "request.json"
        return path, authoring.read_request(path)

    def _pin(self, content):
        return sha256(canonical(content))

    def _live(self):
        return self.worker is not None and self.worker.is_alive()

    def _sessions(self):
        result = []
        with os.scandir(self.root) as entries:
            for count, entry in enumerate(entries):
                if count >= 1000:
                    raise ValueError("Development directory metadata limit exceeded")
                try:
                    session_id = str(UUID(entry.name))
                except ValueError:
                    continue
                if entry.name != session_id:
                    continue
                _path, content = self._request(session_id)
                result.append(
                    {
                        "id": session_id,
                        "goal": content["request"]["spec"]["goal"],
                        "platform_url": content["platform_url"],
                        "gateway_id": content["request"]["gateway_id"],
                        "resource_id": content["request"]["resource_id"],
                        "fingerprint": content["request"]["fingerprint"],
                    }
                )
                if len(result) > 100:
                    raise ValueError("Use the CLI to inspect more than 100 sessions")
        return sorted(result, key=lambda item: item["id"])

    def _artifacts(self, path, content):
        """Validate retained outputs; no rebuild, testing, remote call or code import."""
        result = []
        with os.scandir(path.parent) as entries:
            for count, entry in enumerate(entries):
                if count >= 1000:
                    raise ValueError("Session artifact limit exceeded")
                if not entry.name.endswith(".proposal.json"):
                    continue
                turn_id = str(UUID(entry.name.removesuffix(".proposal.json")))
                proposal = validate_proposal(
                    strict_json(authoring._blob(path.parent / entry.name)),
                    content["request"]["spec"],
                )
                candidate = candidate_digest(content["request"]["spec"], proposal)
                report_path = path.parent / f"{turn_id}.report.json"
                marker = path.parent / f"{turn_id}.sandbox.json"
                if not report_path.exists():
                    result.append(
                        {
                            "id": turn_id,
                            "state": "test_uncertain"
                            if marker.exists()
                            else "needs_information"
                            if proposal["missing_information"]
                            else "not_tested",
                            "proposal": proposal,
                            "container": sandbox_name(turn_id)
                            if marker.exists()
                            else None,
                        }
                    )
                    continue
                report = strict_json(authoring._blob(report_path))
                expected = authoring._report(
                    content["request"],
                    {"candidate_digest": candidate},
                    phase=report["phase"],
                    archive=report["archive_digest"],
                    passed=report["passed"],
                    reason=report["failure_reason"],
                    output=report["untrusted_test_output"],
                )
                if report != expected or type(report["passed"]) is not bool:
                    raise ValueError("Retained report differs from the fixed candidate")
                if report["archive_digest"]:
                    raw = authoring._blob(path.parent / f"{turn_id}.zip")
                    if sha256(raw) != report["archive_digest"]:
                        raise ValueError("Retained package differs from its report")
                if report["passed"] and (
                    report["phase"] != "sandbox"
                    or not report["archive_digest"]
                    or report["failure_reason"]
                    or proposal["missing_information"]
                ):
                    raise ValueError("Invalid passing local test report")
                result.append(
                    {
                        "id": turn_id,
                        "state": "locally_tested_draft"
                        if report["passed"]
                        else "test_failed",
                        "report": report,
                        "proposal": proposal,
                    }
                )
                if len(result) > 5:
                    raise ValueError("Too many retained source candidates")
        return result

    def _inspect(self, session_id):
        path, content = self._request(session_id)
        runs = []
        with os.scandir(path.parent) as entries:
            for count, entry in enumerate(entries):
                if count >= 1000:
                    raise ValueError("Session history limit exceeded")
                if (
                    not entry.name.startswith("run-")
                    or not entry.name.endswith(".json")
                    or entry.name.endswith(".result.json")
                ):
                    continue
                run_id = str(UUID(entry.name[4:-5]))
                ticket = strict_json(authoring._blob(path.parent / entry.name))
                fields(
                    ticket,
                    [
                        "id",
                        "session_id",
                        "fingerprint",
                        "reconcile",
                        "reconcile_turn_ids",
                        "created_at",
                    ],
                )
                if (
                    ticket["id"] != run_id
                    or ticket["session_id"] != content["request"]["id"]
                    or ticket["fingerprint"] != content["request"]["fingerprint"]
                ):
                    raise ValueError("Local run history differs from this request")
                result_path = path.parent / f"run-{run_id}.result.json"
                result = (
                    strict_json(authoring._blob(result_path))
                    if result_path.exists()
                    else None
                )
                if result is not None:
                    fields(result, ["state", "hardware_authorized"])
                    if (
                        result["state"]
                        not in {
                            "draft_tested",
                            "needs_information",
                            "model_in_progress",
                            "authorization_ended",
                            "budget_exhausted",
                            "locally_paused",
                            "needs_inspection",
                        }
                        or result["hardware_authorized"] is not False
                    ):
                        raise ValueError("Invalid local completion summary")
                runs.append(
                    {
                        "id": run_id,
                        "created_at": ticket["created_at"],
                        "result": result,
                        "liveness": "not_observed",
                    }
                )
        return {
            "id": content["request"]["id"],
            "authorization": content["request"],
            "platform_url": content["platform_url"],
            "artifacts": self._artifacts(path, content),
            "runs": sorted(runs, key=lambda item: item["created_at"]),
            "hardware_authorized": False,
            "activation_performed": False,
        }

    def _state(self):
        return {
            "root": str(self.root),
            "sessions": self._sessions(),
            "job": {
                **self.job,
                "worker_alive": self._live(),
                "pause_requested": self.stop.is_set(),
            }
            if self.job
            else None,
            "hardware_authorized": False,
            "activation_performed": False,
        }

    def _progress(self, phase):
        with self.lock:
            self.job["phase"] = phase

    def _execute(self, path, ticket):
        try:
            outcome = authoring.run(
                path,
                reconcile=ticket["reconcile"],
                reconcile_turn_ids=ticket["reconcile_turn_ids"],
                pause_requested=self.stop.is_set,
                progress=self._progress,
            )
            # Persist an ordinary local summary. Raw proposals remain in their
            # existing private files and are only returned by explicit inspection.
            result = {"state": outcome["state"], "hardware_authorized": False}
            authoring._save(
                path.parent / f"run-{ticket['id']}.result.json", canonical(result)
            )
        except Exception:  # noqa: BLE001 - thread boundary must redact private failures
            # Private source, paths, credentials and remote details are not UI errors.
            result = {"state": "needs_inspection", "hardware_authorized": False}
            try:
                authoring._save(
                    path.parent / f"run-{ticket['id']}.result.json", canonical(result)
                )
            except (ValueError, OSError):
                pass  # The missing result remains explicit uncertainty on restart.
        with self.lock:
            self.job.update(phase="finished", result=result)

    def pause(self):
        """Cooperative local pause; does not cancel Platform grants or physical work."""
        self.stop.set()

    def _dispatch(self, operation, data):
        if operation == "state":
            fields(data, [])
            return self._state()
        if operation == "prepare-preview":
            fields(
                data,
                [
                    "platform_url",
                    "gateway_id",
                    "resource_id",
                    "spec",
                    "sdk_wheel",
                    "trusted_sdk_digest",
                    "image",
                    "max_iterations",
                    "duration_seconds",
                    "timeout_seconds",
                ],
            )
            inputs = {
                **data,
                "workspace": str(self.root),
                "spec": str(selected_path(data["spec"])),
                "sdk_wheel": str(selected_path(data["sdk_wheel"])),
            }
            for key in (
                "platform_url",
                "gateway_id",
                "resource_id",
                "trusted_sdk_digest",
                "image",
            ):
                inputs[key] = text(data[key])
            if any(
                type(data[key]) is not int
                for key in ("max_iterations", "duration_seconds", "timeout_seconds")
            ):
                raise ValueError("Use integer development limits")
            preview = authoring.prepare_preview(**inputs)
            return self._offer(
                "prepare",
                {"inputs": inputs, "digest": preview["preview_digest"]},
                preview,
            )
        if operation == "prepare-confirm":
            selected = self._consume("prepare", data)
            if len(self._sessions()) >= 100:
                raise ValueError("Development session limit exceeded")
            result = authoring.prepare(
                **selected["inputs"], expected_preview_digest=selected["digest"]
            )
            return self._inspect(Path(result["request_file"]).parent.name)
        if operation == "inspect":
            fields(data, ["id"])
            return self._inspect(data["id"])
        if operation == "run-preview":
            fields(data, ["id", "reconcile"])
            if self._live() or type(data["reconcile"]) is not bool:
                raise ValueError(
                    "Another local run is active or confirmation is invalid"
                )
            path, content = self._request(data["id"])
            status = authoring.AuthoringClient(content).call("status")
            can_generate = authoring._open(status, content["request"])
            artifacts = self._artifacts(path, content)
            return self._offer(
                "run",
                {
                    "id": content["request"]["id"],
                    "pin": self._pin(content),
                    "reconcile": data["reconcile"],
                    "reconcile_turn_ids": [
                        item["id"]
                        for item in artifacts
                        if item["state"] == "test_uncertain"
                    ],
                },
                {
                    "request": content["request"],
                    "platform_url": content["platform_url"],
                    "model_calls_permitted": can_generate,
                    "source_review": source_review(content["request"]["spec"]),
                    "reconcile_interrupted_test": data["reconcile"],
                    "uncertain_containers": [
                        item["container"]
                        for item in artifacts
                        if item["state"] == "test_uncertain"
                    ],
                    "hardware_authorized": False,
                    "activation_performed": False,
                },
            )
        if operation == "run-confirm":
            selected = self._consume("run", data)
            if self._live():
                raise ValueError("Another local worker is still running")
            path, content = self._request(selected["id"])
            if self._pin(content) != selected["pin"]:
                raise ValueError("Development request changed after preview")
            ticket = {
                "id": str(uuid4()),
                "session_id": selected["id"],
                "fingerprint": content["request"]["fingerprint"],
                "reconcile": selected["reconcile"],
                "reconcile_turn_ids": selected["reconcile_turn_ids"],
                "created_at": datetime.now(UTC).isoformat(),
            }
            authoring._save(path.parent / f"run-{ticket['id']}.json", canonical(ticket))
            self.stop.clear()
            self.job = {
                "id": ticket["id"],
                "session_id": selected["id"],
                "goal": content["request"]["spec"]["goal"],
                "gateway_id": content["request"]["gateway_id"],
                "resource_id": content["request"]["resource_id"],
                "phase": "starting",
                "result": None,
            }
            self.worker = threading.Thread(
                target=self._execute, args=(path, ticket), daemon=True
            )
            self.worker.start()
            return self._state()
        if operation == "pause":
            fields(data, ["id"])
            if not self.job or data["id"] != self.job["id"]:
                raise ValueError("Select this assistant's exact local worker")
            self.pause()
            return {
                "pause_requested": True,
                "worker_alive": self._live(),
                "hardware_authorized": False,
            }
        if operation == "download":
            fields(data, ["id", "kind", "turn_id"])
            path, content = self._request(data["id"])
            if data["kind"] == "authorization" and data["turn_id"] is None:
                return LocalDownload(
                    canonical(content["request"]),
                    f"private-authoring-{content['request']['id']}.json",
                    "application/json",
                )
            turn_id = str(UUID(text(data["turn_id"], 36)))
            selected = next(
                (
                    item
                    for item in self._artifacts(path, content)
                    if item["id"] == turn_id
                ),
                None,
            )
            if selected is None or selected["state"] not in {
                "locally_tested_draft",
                "test_failed",
            }:
                raise ValueError("No validated retained report for this candidate")
            if data["kind"] == "report":
                return LocalDownload(
                    canonical(selected["report"]),
                    f"private-test-{turn_id}.json",
                    "application/json",
                )
            if (
                data["kind"] == "package"
                and selected["state"] == "locally_tested_draft"
            ):
                raw = authoring._blob(path.parent / f"{turn_id}.zip")
                if sha256(raw) != selected["report"]["archive_digest"]:
                    raise ValueError("Package changed before download")
                return LocalDownload(
                    raw, f"private-adapter-{turn_id}.zip", "application/zip"
                )
            raise ValueError("Unsupported artifact")
        raise ValueError("Unsupported development operation")
