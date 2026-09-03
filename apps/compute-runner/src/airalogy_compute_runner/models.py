"""Strict local view of the signed Compute Job contract."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

IMAGE_DIGEST_RE = re.compile(
    r"^(?![^@]*://)[a-z0-9][a-z0-9._:/-]{0,1975}@sha256:[0-9a-f]{64}$"
)
MOUNT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
MEDIA_TYPE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$"
)
EGRESS_HOST_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?|\[[0-9a-f:]+\])(?::[1-9][0-9]{0,4})?$"
)
MAX_SOURCE_BYTES = 200_000
MAX_OUTPUT_FILE_BYTES = 2_147_483_647


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"Compute Job {name} must be an object")
    return value


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"Compute Job {name} must be an array")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Compute Job {name} is required")
    return value.strip()


def _identifier(value: Any, name: str) -> str:
    raw = _text(value, name)
    try:
        return str(UUID(raw))
    except ValueError as error:
        raise ValueError(f"Compute Job {name} must be a UUID") from error


def _integer(
    value: Any,
    name: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        bounds = f"between {minimum} and {maximum}" if maximum else f">= {minimum}"
        raise ValueError(f"Compute Job {name} must be an integer {bounds}")
    return value


def _instant(value: Any, name: str) -> datetime:
    raw = _text(value, name)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise ValueError(f"Compute Job {name} is not an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"Compute Job {name} must include a timezone")
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class ComputeInput:
    id: str
    mount_name: str
    download_path: str
    checksum_sha256: str
    byte_size: int

    @classmethod
    def parse(cls, raw: Any) -> ComputeInput:
        value = _mapping(raw, "input")
        mount_name = _text(value.get("mount_name"), "input.mount_name")
        if not MOUNT_NAME_RE.fullmatch(mount_name):
            raise ValueError("Compute Job input.mount_name is unsafe")
        path = _text(value.get("download_path"), "input.download_path")
        if not path.startswith("/compute-runner/v1/jobs/") or "://" in path:
            raise ValueError("Compute Job input.download_path is unsafe")
        checksum = _text(value.get("checksum_sha256"), "input.checksum_sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("Compute Job input checksum is invalid")
        return cls(
            id=_identifier(value.get("id"), "input.id"),
            mount_name=mount_name,
            download_path=path,
            checksum_sha256=checksum,
            byte_size=_integer(value.get("byte_size"), "input.byte_size"),
        )


@dataclass(frozen=True)
class ComputeOutput:
    id: str
    mount_name: str
    upload_path: str
    asset_name: str
    description: str
    kind: str
    media_type: str
    max_bytes: int
    required: bool
    data_schema: dict[str, Any]
    metadata: dict[str, Any]

    @classmethod
    def parse(cls, raw: Any) -> ComputeOutput:
        value = _mapping(raw, "output")
        mount_name = _text(value.get("mount_name"), "output.mount_name")
        if not MOUNT_NAME_RE.fullmatch(mount_name):
            raise ValueError("Compute Job output.mount_name is unsafe")
        path = _text(value.get("upload_path"), "output.upload_path")
        if not path.startswith("/compute-runner/v1/jobs/") or "://" in path:
            raise ValueError("Compute Job output.upload_path is unsafe")
        media_type = _text(value.get("media_type"), "output.media_type").lower()
        if not MEDIA_TYPE_RE.fullmatch(media_type):
            raise ValueError("Compute Job output.media_type is invalid")
        kind = _text(value.get("kind"), "output.kind")
        if kind not in {"file", "table", "image", "model", "archive"}:
            raise ValueError("Compute Job output.kind is unsupported")
        required = value.get("required")
        if not isinstance(required, bool):
            raise TypeError("Compute Job output.required must be a boolean")
        return cls(
            id=_identifier(value.get("id"), "output.id"),
            mount_name=mount_name,
            upload_path=path,
            asset_name=_text(value.get("asset_name"), "output.asset_name"),
            description=(
                value.get("description").strip()
                if isinstance(value.get("description"), str)
                else ""
            ),
            kind=kind,
            media_type=media_type,
            max_bytes=_integer(
                value.get("max_bytes"),
                "output.max_bytes",
                minimum=1,
                maximum=MAX_OUTPUT_FILE_BYTES,
            ),
            required=required,
            data_schema=_mapping(value.get("data_schema"), "output.data_schema"),
            metadata=_mapping(value.get("metadata"), "output.metadata"),
        )


@dataclass(frozen=True)
class ComputeJobEnvelope:
    raw: dict[str, Any]
    job_id: str
    action_id: str
    task_id: str
    run_id: str
    issued_at: datetime
    lease_expires_at: datetime
    environment_id: str
    environment_revision_id: str
    environment_revision: int
    image_ref: str
    runtime_version: str
    language: str
    cpu_millis: int
    memory_mb: int
    gpu_count: int
    timeout_seconds: int
    max_output_bytes: int
    network_policy: str
    allowed_egress_hosts: tuple[str, ...]
    source_code: str
    source_sha256: str
    input_payload: dict[str, Any]
    inputs: tuple[ComputeInput, ...]
    outputs: tuple[ComputeOutput, ...]
    result_schema: dict[str, Any]

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> ComputeJobEnvelope:
        if raw.get("schema") != "airalogy.compute-job.v1":
            raise ValueError("Unsupported Compute Job envelope schema")
        now = datetime.now(UTC)
        issued_at = _instant(raw.get("issued_at"), "issued_at")
        expires_at = _instant(raw.get("lease_expires_at"), "lease_expires_at")
        if issued_at > now + timedelta(seconds=30):
            raise ValueError("Compute Job was issued in the future")
        if not issued_at < expires_at or expires_at > issued_at + timedelta(minutes=5):
            raise ValueError("Compute Job lease window is invalid")
        environment = _mapping(raw.get("environment"), "environment")
        image_ref = _text(environment.get("image_ref"), "environment.image_ref")
        if not IMAGE_DIGEST_RE.fullmatch(image_ref):
            raise ValueError("Compute Job image_ref must be an immutable sha256 digest")
        language = _text(environment.get("language"), "environment.language")
        if language not in {"python", "r"}:
            raise ValueError("Compute Job language is unsupported")
        limits = _mapping(environment.get("resource_limits"), "resource_limits")
        network_policy = _text(
            environment.get("network_policy"), "environment.network_policy"
        )
        if network_policy not in {"none", "egress_allowlist"}:
            raise ValueError("Compute Job network policy is unsupported")
        hosts = _list(
            environment.get("allowed_egress_hosts") or [],
            "environment.allowed_egress_hosts",
        )
        if not all(isinstance(host, str) and host.strip() for host in hosts):
            raise ValueError("Compute Job egress hosts are invalid")
        normalized_hosts = tuple(sorted({host.strip().lower() for host in hosts}))
        for host in normalized_hosts:
            if not EGRESS_HOST_RE.fullmatch(host):
                raise ValueError(f"Compute Job egress host is invalid: {host}")
            if ":" in host and not host.startswith("["):
                port = int(host.rsplit(":", 1)[1])
                if port > 65_535:
                    raise ValueError(f"Compute Job egress port is invalid: {host}")
        if network_policy == "none" and normalized_hosts:
            raise ValueError("Network-disabled Compute Job cannot allow egress hosts")
        if network_policy == "egress_allowlist" and not normalized_hosts:
            raise ValueError("Compute Job egress allowlist cannot be empty")
        source = _mapping(raw.get("source"), "source")
        source_code = source.get("code")
        if not isinstance(source_code, str) or not source_code.strip():
            raise ValueError("Compute Job source.code is required")
        if len(source_code.encode("utf-8")) > MAX_SOURCE_BYTES:
            raise ValueError("Compute Job source.code exceeds the maximum size")
        source_digest = _text(source.get("sha256"), "source.sha256")
        if hashlib.sha256(source_code.encode("utf-8")).hexdigest() != source_digest:
            raise ValueError("Compute Job source digest does not match")
        inputs = tuple(
            ComputeInput.parse(value) for value in _list(raw.get("inputs"), "inputs")
        )
        mount_names = {item.mount_name for item in inputs}
        if len(mount_names) != len(inputs) or len(inputs) > 32:
            raise ValueError("Compute Job input mount names must be unique and bounded")
        job_id = _identifier(raw.get("job_id"), "job_id")
        for item in inputs:
            expected_path = f"/compute-runner/v1/jobs/{job_id}/inputs/{item.id}"
            if item.download_path != expected_path:
                raise ValueError(
                    "Compute Job input.download_path does not match its job and input"
                )
        outputs = tuple(
            ComputeOutput.parse(value)
            for value in _list(raw.get("outputs") or [], "outputs")
        )
        output_mounts = {item.mount_name for item in outputs}
        if len(output_mounts) != len(outputs) or len(outputs) > 16:
            raise ValueError(
                "Compute Job output mount names must be unique and bounded"
            )
        for item in outputs:
            expected_path = f"/compute-runner/v1/jobs/{job_id}/outputs/{item.id}"
            if item.upload_path != expected_path:
                raise ValueError(
                    "Compute Job output.upload_path does not match its job and output"
                )
        max_output_bytes = _integer(
            limits.get("max_output_bytes"),
            "max_output_bytes",
            minimum=1024,
            maximum=10 * 1024 * 1024 * 1024,
        )
        if sum(item.max_bytes for item in outputs) > max_output_bytes - 1024:
            raise ValueError("Compute Job output declarations exceed the output limit")
        return cls(
            raw=dict(raw),
            job_id=job_id,
            action_id=_identifier(raw.get("action_id"), "action_id"),
            task_id=_identifier(raw.get("task_id"), "task_id"),
            run_id=_identifier(raw.get("run_id"), "run_id"),
            issued_at=issued_at,
            lease_expires_at=expires_at,
            environment_id=_identifier(environment.get("id"), "environment.id"),
            environment_revision_id=_identifier(
                environment.get("revision_id"), "environment.revision_id"
            ),
            environment_revision=_integer(
                environment.get("revision"), "environment.revision", minimum=1
            ),
            image_ref=image_ref,
            runtime_version=_text(
                environment.get("runtime_version"), "environment.runtime_version"
            ),
            language=language,
            cpu_millis=_integer(
                limits.get("cpu_millis"), "cpu_millis", minimum=100, maximum=64_000
            ),
            memory_mb=_integer(
                limits.get("memory_mb"), "memory_mb", minimum=128, maximum=1_048_576
            ),
            gpu_count=_integer(limits.get("gpu_count"), "gpu_count", maximum=8),
            timeout_seconds=_integer(
                limits.get("timeout_seconds"),
                "timeout_seconds",
                minimum=1,
                maximum=86_400,
            ),
            max_output_bytes=max_output_bytes,
            network_policy=network_policy,
            allowed_egress_hosts=normalized_hosts,
            source_code=source_code,
            source_sha256=source_digest,
            input_payload=_mapping(raw.get("input_payload"), "input_payload"),
            inputs=inputs,
            outputs=outputs,
            result_schema=_mapping(raw.get("result_schema"), "result_schema"),
        )

    @property
    def workspace_bytes(self) -> int:
        return (
            sum(item.byte_size for item in self.inputs)
            + len(self.source_code.encode("utf-8"))
            + len(
                json.dumps(
                    self.input_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            + self.max_output_bytes
            + 16 * 1024 * 1024
        )

    @property
    def egress_key(self) -> str:
        return ",".join(self.allowed_egress_hosts)
