"""Inactive, offline installation snapshots. Never import or activate a driver.

This is a local filesystem operation, not Platform approval or qualification.
The runtime journal lock must be shared with the operator's configured Gateway.
"""

import os
import platform
import re
import stat
import sys
import tempfile
import venv
from email.parser import BytesParser
from pathlib import Path

from .package_cli import read_selected
from .package_contract import (
    _zip_files,
    canonical,
    inspect_package,
    sha256,
    strict_json,
    wheel_identity,
)
from .state import StateStore


def _private_root(root: Path) -> Path:
    if os.name != "posix":
        raise ValueError(
            "Inactive installation currently requires POSIX owner permissions"
        )
    absolute = root.absolute()
    info = absolute.lstat()
    if (
        absolute.resolve() != absolute
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("Installation root must be a real owner-only directory (0700)")
    return absolute


def _exact_requirements(wheels):
    """Conservative offline subset; unsupported resolution never uses the network."""
    versions = {item["name"]: item["version"] for item in wheels}
    if len(versions) != len(wheels):
        raise ValueError("An installation cannot contain duplicate distributions")
    for wheel in wheels:
        for requirement in wheel["requirements"]:
            match = re.fullmatch(
                r"\s*([A-Za-z0-9_.-]+)\s*==\s*([A-Za-z0-9_.+!-]+)\s*", requirement
            )
            if not match:
                raise ValueError(
                    "Installer supports only unconditional exact dependency pins"
                )
            name = re.sub(r"[-_.]+", "-", match[1]).lower()
            if versions.get(name) != match[2]:
                raise ValueError("An exact dependency is missing or incompatible")


def _python_requirement(expression):
    current = sys.version_info[:3]
    for item in expression.split(","):
        match = re.fullmatch(
            r"\s*(>=|<=|==|!=|>|<)\s*(\d+)\.(\d+)(?:\.(\d+))?\s*", item
        )
        if not match:
            raise ValueError(
                "Unsupported Requires-Python constraint in offline installer"
            )
        version = (int(match[2]), int(match[3]), int(match[4] or 0))
        if not {
            ">=": current >= version,
            "<=": current <= version,
            "==": current == version,
            "!=": current != version,
            ">": current > version,
            "<": current < version,
        }[match[1]]:
            raise ValueError("Wheel requires a different Python version")


def _contents(raw, sdk_wheel, trusted_sdk_digest):
    inspection = inspect_package(raw)
    if sha256(sdk_wheel) != trusted_sdk_digest:
        raise ValueError("SDK bytes do not match the independently trusted digest")
    sdk = wheel_identity(sdk_wheel)
    manifest = inspection["manifest"]
    if (
        sdk["name"] != "airalogy-instrument-gateway"
        or sdk["version"] not in manifest["compatibility"]["gateway_versions"]
    ):
        raise ValueError("Trusted SDK does not match declared compatibility")
    if (
        f"{sys.version_info.major}.{sys.version_info.minor}"
        not in manifest["compatibility"]["python_versions"]
    ):
        raise ValueError("This Python version is not declared compatible")
    package_files = _zip_files(raw)
    wheel_bytes = [sdk_wheel] + [
        package_files[item["path"]]
        for item in manifest["files"]
        if item["role"] in {"adapter_wheel", "dependency_wheel"}
    ]
    identities, installed = [], {}
    folded = set()
    for value in wheel_bytes:
        identity = wheel_identity(value)
        identities.append(identity)
        files = _zip_files(value)
        wheel_metadata = next(
            value for name, value in files.items() if name.endswith(".dist-info/WHEEL")
        )
        fields = BytesParser().parsebytes(wheel_metadata)
        if fields.get("Root-Is-Purelib", "").lower() != "true" or fields.get_all(
            "Tag"
        ) != ["py3-none-any"]:
            raise ValueError(
                "This installer accepts only pure Python py3-none-any wheels"
            )
        metadata = BytesParser().parsebytes(
            next(
                value
                for name, value in files.items()
                if name.endswith(".dist-info/METADATA")
            )
        )
        if metadata.get("Requires-Python"):
            _python_requirement(metadata["Requires-Python"])
        for name, content in files.items():
            if name.casefold() in folded:
                raise ValueError("Installed wheels must not overwrite each other")
            folded.add(name.casefold())
            installed[name] = content
    _exact_requirements(identities)
    for name in folded:
        parts = name.split("/")
        if any("/".join(parts[:index]) in folded for index in range(1, len(parts))):
            raise ValueError("Installed wheels contain a file/directory collision")
    return inspection, installed


def installation_preview(raw, *, sdk_wheel, trusted_sdk_digest, config, root):
    root = _private_root(root)
    if not isinstance(config, dict) or len(canonical(config)) > 16384:
        raise ValueError("Local adapter configuration must be a bounded JSON object")
    inspection, files = _contents(raw, sdk_wheel, trusted_sdk_digest)
    identity = {
        "schema": "airalogy.inactive-installation.v1",
        "archive_digest": inspection["archive_digest"],
        "manifest_digest": inspection["manifest_digest"],
        "sdk_digest": trusted_sdk_digest,
        "configuration_digest": sha256(canonical(config)),
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "platform": sys.platform,
        "architecture": platform.machine(),
        "interpreter_digest": sha256(read_selected(Path(sys.executable).resolve())),
        "entry_point": inspection["manifest"]["entry_point"],
    }
    installation_id = sha256(canonical(identity))
    plan = {
        **identity,
        "installation_id": installation_id,
        "destination": str(root / installation_id),
        "journal": str(root / "state.json"),
        "installed_file_count": len(files),
        "installed_bytes": sum(map(len, files.values())),
        "source_reviewed": False,
        "platform_authorized": False,
        "hardware_authorized": False,
        "activation_performed": False,
    }
    return {**plan, "preview_digest": sha256(canonical(plan))}


def _write(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as target:
        target.write(value)
        target.flush()
        os.fsync(target.fileno())


def _sync_snapshot(root):
    # Persist directory entries and the stdlib-created interpreter files as well
    # as wheel bytes before publishing a complete snapshot. Do not follow the
    # lib64 alias that venv may create on Linux.
    for directory, _directories, names in os.walk(
        root, topdown=False, followlinks=False
    ):
        for name in names:
            entry = Path(directory) / name
            if entry.is_symlink():
                continue
            fd = os.open(entry, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def verify_installation(path, *, expected_plan=None, expected_files=None):
    """Verify stored payload bytes; this still does not import or qualify the code."""
    path = _private_root(path)
    receipt = strict_json(read_selected(path / "receipt.json", limit=2 * 1024 * 1024))
    if receipt.get("schema") != "airalogy.inactive-installation-receipt.v1":
        raise ValueError("Unknown installation receipt")
    if expected_plan is not None:
        for key, value in expected_plan.items():
            if key not in {"schema", "source_reviewed"} and receipt.get(key) != value:
                raise ValueError(
                    "Installation receipt differs from independently supplied inputs"
                )
    site = path / receipt["site_packages"]
    # Receipt paths are locally untrusted too. Do not read outside this snapshot.
    if site.resolve().is_relative_to(path) is False or site.is_symlink():
        raise ValueError("Installed path escaped its snapshot")
    expected = receipt["files"]
    if expected_files is not None and expected != expected_files:
        raise ValueError(
            "Receipt hashes differ from independently supplied wheel bytes"
        )
    actual = {}
    for directory, directories, names in os.walk(site, followlinks=False):
        for name in [*directories, *names]:
            entry = Path(directory) / name
            info = entry.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
            ):
                raise ValueError("Installed content must remain private and link-free")
        for name in names:
            entry = Path(directory) / name
            if entry.lstat().st_nlink != 1:
                raise ValueError("Installed files must not have hard links")
            actual[entry.relative_to(site).as_posix()] = sha256(read_selected(entry))
    if actual != expected:
        raise ValueError("Installed content differs from its receipt")
    for name in [
        "python",
        "python3",
        f"python{sys.version_info.major}.{sys.version_info.minor}",
    ]:
        interpreter = path / "bin" / name
        if sha256(read_selected(interpreter)) != receipt["interpreter_digest"]:
            raise ValueError("Installed interpreter differs from its receipt")
    return receipt


def install_inactive(
    raw,
    *,
    sdk_wheel,
    trusted_sdk_digest,
    config,
    root,
    preview_digest,
    source_reviewed=False,
):
    if source_reviewed is not True:
        raise ValueError(
            "Explicit local source/dependency review acknowledgement is required"
        )
    root = _private_root(root)
    with StateStore(root / "state.json").exclusive():
        return _install_inactive_locked(
            raw,
            sdk_wheel=sdk_wheel,
            trusted_sdk_digest=trusted_sdk_digest,
            config=config,
            root=root,
            preview_digest=preview_digest,
        )


def _install_inactive_locked(
    raw, *, sdk_wheel, trusted_sdk_digest, config, root, preview_digest
):
    """Trusted manager only: caller holds the configured runtime journal lock."""
    StateStore(root / "state.json").assert_installable()
    plan = installation_preview(
        raw,
        sdk_wheel=sdk_wheel,
        trusted_sdk_digest=trusted_sdk_digest,
        config=config,
        root=root,
    )
    if plan["preview_digest"] != preview_digest:
        raise ValueError("Installation preview changed; inspect and confirm it again")
    destination = root / plan["installation_id"]
    _, files = _contents(raw, sdk_wheel, trusted_sdk_digest)
    file_hashes = {name: sha256(value) for name, value in files.items()}
    if destination.exists():
        return verify_installation(
            destination, expected_plan=plan, expected_files=file_hashes
        )
    staging = Path(tempfile.mkdtemp(prefix=".pending-install-", dir=root))
    # No pip, dependency resolution, build backend, driver import or subprocess
    # of adapter code. A venv isolates dependencies, not hardware permissions.
    builder = venv.EnvBuilder(with_pip=False, symlinks=False)
    builder.create(staging)
    context = builder.ensure_directories(staging)
    site = (
        staging
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    if hasattr(context, "lib_path") and Path(context.lib_path) != site:
        raise ValueError("Unsupported virtual environment library layout")
    for name, value in files.items():
        _write(site / name, value)
    receipt = {
        **plan,
        "schema": "airalogy.inactive-installation-receipt.v1",
        "source_reviewed": True,
        "site_packages": site.relative_to(staging).as_posix(),
        "files": file_hashes,
    }
    _write(staging / "receipt.json", canonical(receipt))
    verify_installation(staging, expected_plan=plan, expected_files=file_hashes)
    _sync_snapshot(staging)
    # No active pointer is changed. Partial staging directories remain private
    # and unusable after failure; a retry can create a fresh staging directory.
    os.rename(staging, destination)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return receipt
