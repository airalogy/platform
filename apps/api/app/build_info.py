"""Resolve immutable product build identity for diagnostics and support."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class BuildInfo:
    version: str
    tag: str | None
    commit: str
    build_time: str | None
    dirty: bool
    release_manifest_sha256: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _repository_version() -> str | None:
    version_path = Path(__file__).resolve().parents[3] / "VERSION"
    try:
        value = version_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _configured_bool(value: str | None, fallback: bool) -> bool:
    if value is None:
        return fallback
    return value.strip().lower() in {"1", "true", "yes"}


def resolve_build_info() -> BuildInfo:
    built = _read_json(Path(__file__).with_name("build-info.json"))
    built_tag = built.get("tag")
    built_time = built.get("build_time") or built.get("buildTime")

    return BuildInfo(
        version=(
            str(built.get("version") or "").strip()
            or os.getenv("PLATFORM_VERSION", "").strip()
            or _repository_version()
            or "development"
        ),
        tag=(
            (str(built_tag).strip() if built_tag else None)
            or os.getenv("GIT_TAG", "").strip()
            or None
        ),
        commit=(
            str(built.get("commit") or "").strip()
            or os.getenv("GIT_COMMIT", "").strip()
            or "unknown"
        ),
        build_time=(
            (str(built_time).strip() if built_time else None)
            or os.getenv("BUILD_TIME", "").strip()
            or None
        ),
        dirty=(
            _configured_bool(str(built["dirty"]), False)
            if "dirty" in built
            else _configured_bool(os.getenv("BUILD_DIRTY"), False)
        ),
        release_manifest_sha256=(
            os.getenv("AIRALOGY_RELEASE_MANIFEST_SHA256", "").strip() or None
        ),
    )
