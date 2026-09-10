"""Receipt-only delivery of pinned instrument snapshots to the signed scope.

No driver import, physical retry, file discovery, conversion or Record submission.
The caller holds the runtime lock. Unconfirmed receipts and snapshots are retained.
"""

import json
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid5

from .models import InstrumentResult
from .output_capture import CaptureStore, source_root_identity
from .output_contract import (
    SHA256,
    canonical,
    declarations,
    validate_plan,
    validate_sources,
)

RECEIPT_PHASES = {"completion_pending", "outputs_pending", "completion_unresolved"}
ASSET_KEYS = ("research_file_id", "data_asset_id", "data_asset_version_id")


def authorize_source(root, state_file):
    root, outbox = Path(root), Path(state_file).parent / "instrument-output-outbox"
    if root == outbox or root in outbox.parents or outbox in root.parents:
        raise ValueError("Source and private outbox directories must not overlap")
    return {"path": str(root), "identity": source_root_identity(root)}


def receipt_only(state):
    # Both plain JSON and file-producing acquisitions have already finished.
    # Importing a driver merely to acknowledge either result could initialize
    # equipment. Invalid/missing completion data must halt without loading it.
    return state is not None and state.phase in RECEIPT_PHASES


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Invalid scoped file receipt identity")
    return value


def bundle(job):
    value = job.raw.get("file_outputs")
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"plan", "destination"}:
        raise ValueError("Invalid signed output bundle")
    plan = validate_plan(value["plan"])
    destination = value["destination"]
    if (
        plan["job_id"] != job.job_id
        or not plan["outputs"]
        or not isinstance(destination, dict)
        or set(destination)
        != {
            "activation_id",
            "scope_type",
            "lab_id",
            "project_id",
            "task_id",
            "visibility",
            "asset_state",
            "record_association",
        }
        or destination["task_id"] != job.task_id
        or destination["scope_type"] != "project"
        or destination["visibility"] != "project"
        or destination["asset_state"] != "draft"
        or destination["record_association"] != "awaiting_review"
        or destination["activation_id"] != job.raw.get("activation", {}).get("id")
    ):
        raise ValueError("Output receiving scope differs from the signed job")
    for key in ("activation_id", "lab_id", "project_id", "task_id"):
        _uuid(destination[key])
    return {"plan": plan, "destination": destination}


def selection(plan, files):
    if not isinstance(files, list) or len(files) > 16:
        raise ValueError("Acquisition must explicitly declare its selected files")
    hashes, sources = {}, []
    for item in files:
        if not isinstance(item, dict):
            raise TypeError("Invalid acquisition file metadata")
        checksum = item.get("sha256")
        if not isinstance(checksum, str) or not SHA256.fullmatch(checksum):
            raise ValueError("Acquisition must pin each original file digest")
        hashes[item.get("name")] = checksum
        sources.append({key: value for key, value in item.items() if key != "sha256"})
    return validate_sources(plan, sources), hashes


def completed_result(job, value):
    receiving = bundle(job)
    result = value.result if isinstance(value, InstrumentResult) else value
    if not isinstance(result, dict):
        raise TypeError("Instrument result must be a JSON object")
    raw = canonical(result)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError("Instrument result exceeds its limit")
    result = json.loads(raw)
    files = []
    if receiving:
        if not isinstance(value, InstrumentResult):
            raise ValueError("File-producing acquisition must return InstrumentResult")
        sources, hashes = selection(receiving["plan"], value.files)
        files = json.loads(
            canonical([{**item, "sha256": hashes[item["name"]]} for item in sources])
        )
    elif isinstance(value, InstrumentResult) and value.files:
        raise ValueError("This signed job has no file receiving authority")
    return result, files


class OutputDelivery:
    def __init__(self, config, client, state_store, state, job):
        self.config, self.client, self.store, self.state, self.job = (
            config,
            client,
            state_store,
            state,
            job,
        )
        self.receiving = bundle(job)
        if self.receiving is None:
            raise ValueError("No signed file receiving plan")
        self.plan = self.receiving["plan"]
        self.outbox = CaptureStore(state_store.path.parent / "instrument-output-outbox")

    def capture(self):
        sources, hashes = selection(
            self.plan, self.state.metadata.get("output_sources")
        )
        root = self.state.metadata.get("output_root")
        if (
            not isinstance(root, dict)
            or set(root) != {"path", "identity"}
            or self.config.output_root != Path(root["path"])
        ):
            raise ValueError("Restore the originally authorized output-root selection")
        try:
            capture = self.outbox.inspect(self.plan)
        except FileNotFoundError:
            if source_root_identity(root["path"]) != root["identity"]:
                raise ValueError("Original output directory identity changed")
            self.outbox.prepare(
                self.plan,
                root["path"],
                sources,
                expected_hashes=hashes,
                expected_root_identity=root["identity"],
            )
            capture = self.outbox.capture(self.plan)
        if {item["name"]: item["sha256"] for item in capture["files"]} != hashes:
            raise ValueError("Snapshot differs from the acquisition-time file digests")
        # Check all provenance too, not only file content.
        by_name = {item["name"]: item for item in sources}
        for item in capture["files"]:
            if any(
                item[key] != value
                for key, value in by_name[item["name"]].items()
                if key not in {"path", "write_complete_confirmed"}
            ):
                raise ValueError("Snapshot differs from acquisition provenance")
        return capture

    def _remember(self, name, receipt):
        saved = self.state.metadata.setdefault("delivery_receipts", {})
        if name in saved and saved[name] != receipt:
            raise ValueError("Platform changed a previously acknowledged file identity")
        saved[name] = receipt
        self.store.save(self.state)

    def _receipt(self, item, captured):
        expected_id = str(uuid5(UUID(self.job.job_id), captured["name"]))
        result = {
            "output_id": item.get("output_id", item.get("id")),
            **{key: item.get(key) for key in (*ASSET_KEYS, "sha256", "byte_size")},
        }
        if (
            result["output_id"] != expected_id
            or any(result[key] != captured[key] for key in ("sha256", "byte_size"))
            or type(result["byte_size"]) is not int
        ):
            raise ValueError("Platform file receipt differs from the pinned capture")
        for key in ASSET_KEYS:
            _uuid(result[key])
        return result

    def _snapshot(self, snapshot, capture, *, final=False):
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("job_id") != self.job.job_id
            or snapshot.get("plan") != self.plan
            or snapshot.get("destination") != self.receiving["destination"]
            or snapshot.get("execution_status") != "completed"
            or snapshot.get("state")
            not in ({"delivered"} if final else {"awaiting_files", "delivered"})
        ):
            raise ValueError(
                "Platform delivery acknowledgment differs from the approved job"
            )
        items = snapshot.get("items")
        validate_plan(snapshot["plan"])
        if (
            not isinstance(items, list)
            or len(items) != len(self.plan["outputs"])
            or any(not isinstance(item, dict) for item in items)
        ):
            raise ValueError("Platform delivery output inventory differs")
        captured = {item["name"]: item for item in capture["files"]}
        remaining = []
        for declaration in self.plan["outputs"]:
            matches = [
                item for item in items if item.get("name") == declaration["name"]
            ]
            if len(matches) != 1:
                raise ValueError(
                    "Platform returned missing or duplicate output identities"
                )
            item = matches[0]
            name = declaration["name"]
            declarations([{key: item.get(key) for key in declaration}])
            if item.get("id") != str(uuid5(UUID(self.job.job_id), name)) or any(
                item.get(key) != value for key, value in declaration.items()
            ):
                raise ValueError("Platform output declaration differs")
            if name not in captured:
                if item.get("state") != "omitted":
                    raise ValueError("Optional output omission was not acknowledged")
            elif item.get("state") == "registered":
                if any(item.get(key) != value for key, value in captured[name].items()):
                    raise ValueError("Platform changed captured file provenance")
                self._remember(name, self._receipt(item, captured[name]))
            elif (
                item.get("state") == "awaiting_upload"
                and not final
                and snapshot["state"] != "delivered"
            ):
                if name in self.state.metadata.get("delivery_receipts", {}):
                    raise ValueError("Platform lost a previously acknowledged file")
                remaining.append(captured[name])
            else:
                raise ValueError("Platform did not acknowledge the captured output")
        if snapshot["state"] == "delivered":
            stamp = snapshot.get("finalized_at")
            if (
                not isinstance(stamp, str)
                or datetime.fromisoformat(stamp).tzinfo is None
            ):
                raise ValueError("Delivery lacks its finalization timestamp")
        return remaining

    def deliver(self, capture):
        job_id, token = self.job.job_id, self.state.lease_token
        snapshot = self.client.report_capture(job_id, token, capture)
        remaining = self._snapshot(snapshot, capture)
        for captured in remaining:
            output_id = str(uuid5(UUID(job_id), captured["name"]))
            with self.outbox.open_output(self.plan, captured["name"]) as (
                receipt,
                stream,
            ):
                response = self.client.upload_output(
                    job_id, token, output_id, receipt, stream
                )
                if (
                    not isinstance(response, dict)
                    or response.get("status") != "registered"
                ):
                    raise ValueError("Platform did not acknowledge the file upload")
                self._remember(captured["name"], self._receipt(response, captured))
        final = self.client.finalize_outputs(job_id, token, capture)
        self._snapshot(final, capture, final=True)
        self.state.metadata["delivery_finalized_at"] = final["finalized_at"]
        self.store.save(self.state)
