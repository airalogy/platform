"""Reviewed standalone POSIX SDK installer; never installs or starts a device driver.

Obtain this script/Python/GitHub CLI from independently trusted sources BEFORE
running it. A program cannot establish trust in its own bytes. No sudo, pip,
dependency download, service registration, global PATH change or shell execution.
"""

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import zipfile
from datetime import UTC, datetime
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

REPOSITORY = "airalogy/platform"
WORKFLOW = f"{REPOSITORY}/.github/workflows/release.yml"
MAX_WHEEL = 64 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024
MAX_PROOF = 4 * 1024 * 1024
MODULES = {
    "setup": "setup_cli",
    "author": "authoring_cli",
    "pair": "pairing_cli",
    "package": "package_cli",
    "installation": "installation_manager_cli",
    "activation": "activation_cli",
    "gateway": "__main__",
}
BOOTSTRAP = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module(sys.argv.pop(1),run_name='__main__')"


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def regular(path, limit=MAX_WHEEL):
    path = Path(path).absolute()
    if path.resolve() != path:
        raise ValueError("Selected files must not use symbolic links")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise ValueError("Select a bounded regular file without hard links")
        raw = source.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("Selected file exceeded its limit")
        return raw


def directory(path):
    path = Path(path).absolute()
    if os.name != "posix" or sys.version_info < (3, 11) or path.resolve() != path:
        raise ValueError("Use Python 3.11+ and a real POSIX directory without symlinks")
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("Select an existing account-owned private directory (0700)")
    return {"path": str(path), "device": info.st_dev, "inode": info.st_ino}


def executable(path):
    path = Path(path).resolve(strict=True)
    info = path.stat()
    if (
        info.st_mode & 0o022
        or info.st_uid not in {0, os.getuid()}
        or not os.access(path, os.X_OK)
    ):
        raise ValueError("Use an independently trusted, non-writable executable")
    return {"path": str(path), "sha256": digest(regular(path, MAX_EXPANDED))}


def unpack(raw, version):
    """Read bounded wheel data only, never import package code or run install hooks."""
    prefix = f"airalogy_instrument_gateway-{version}.dist-info/"
    files, folded, total = {}, set(), 0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if not 1 <= len(archive.infolist()) <= 2048:
            raise ValueError("Unexpected SDK wheel file count")
        for item in archive.infolist():
            name = item.filename
            parts = PurePosixPath(name).parts
            if (
                not parts
                or len(parts) > 16
                or len(name) > 240
                or not re.fullmatch(r"[A-Za-z0-9._/-]+", name)
                or any(part in {".", "..", ""} for part in parts)
                or str(PurePosixPath(name)) != name
                or "\\" in name
                or not name.isascii()
                or name.startswith("/")
                or any(ord(char) < 32 for char in name)
                or name.casefold() in folded
                or item.is_dir()
                or stat.S_IFMT(item.external_attr >> 16) not in {0, stat.S_IFREG}
                or not name.startswith(("airalogy_instrument_gateway/", prefix))
                or name.endswith((".pth", ".pyc"))
                or "__pycache__" in parts
                or item.flag_bits & 1
                or item.file_size > MAX_WHEEL
            ):
                raise ValueError("Unsupported SDK wheel layout or unsafe path")
            folded.add(name.casefold())
            total += item.file_size
            if total > MAX_EXPANDED:
                raise ValueError("Expanded SDK exceeds its limit")
            files[name] = archive.read(item)
    if any(
        str(parent).casefold() in folded
        for name in files
        for parent in PurePosixPath(name).parents
    ):
        raise ValueError("SDK file and directory names conflict")
    metadata = BytesParser().parsebytes(files[prefix + "METADATA"])
    wheel = BytesParser().parsebytes(files[prefix + "WHEEL"])
    if (
        metadata.get_all("Name") != ["airalogy-instrument-gateway"]
        or metadata.get_all("Version") != [version]
        or metadata.get_all("Requires-Dist")
        or wheel.get_all("Root-Is-Purelib") != ["true"]
        or wheel.get_all("Tag") != ["py3-none-any"]
        or any(
            f"airalogy_instrument_gateway/{name}.py" not in files
            for name in MODULES.values()
        )
    ):
        raise ValueError(
            "Bootstrap supports only the exact dependency-free pure Python SDK"
        )
    return files


def inputs(args):
    if not re.fullmatch(
        r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", args.release_tag
    ):
        raise ValueError("Select an exact stable vMAJOR.MINOR.PATCH release")
    if not re.fullmatch(r"[a-f0-9]{40}", args.commit) or not re.fullmatch(
        r"[a-f0-9]{64}", args.wheel_sha256
    ):
        raise ValueError(
            "Supply independently verified release commit and wheel SHA-256"
        )
    destination = Path(args.destination).absolute()
    parent = directory(destination.parent)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}", destination.name):
        raise ValueError("Use a new SDK directory with a portable name")
    for name in ("gateway.json", "state.json"):
        if (destination.parent / name).exists() or (
            destination.parent / name
        ).is_symlink():
            raise ValueError(
                "Keep SDK installation separate from runtime data and credentials"
            )
    raw = regular(args.wheel)
    if digest(raw) != args.wheel_sha256:
        raise ValueError("Selected wheel differs from its independent SHA-256")
    version = args.release_tag[1:]
    files = unpack(raw, version)
    gh = args.gh or shutil.which("gh")
    if not gh:
        raise ValueError("Install a trusted GitHub CLI before verification")
    proof_inputs = {}
    if args.online_verification:
        if args.bundle or args.trusted_root or args.trusted_root_sha256:
            raise ValueError(
                "Choose online verification OR selected offline proof/root"
            )
    else:
        if not args.bundle or not args.trusted_root or not args.trusted_root_sha256:
            raise ValueError(
                "Explicitly permit online verification or supply an offline proof and independently trusted root"
            )
        proof_inputs = {
            "bundle": regular(args.bundle, MAX_PROOF),
            "trusted_root": regular(args.trusted_root, MAX_PROOF),
        }
        if digest(proof_inputs["trusted_root"]) != args.trusted_root_sha256:
            raise ValueError(
                "Offline trusted root differs from its independent SHA-256"
            )
    script = regular(Path(__file__).resolve(), MAX_PROOF)
    plan = {
        "schema": "airalogy.sdk-bootstrap.v1",
        "repository": REPOSITORY,
        "signer_workflow": WORKFLOW,
        "release_tag": args.release_tag,
        "commit": args.commit,
        "wheel_name": f"airalogy_instrument_gateway-{version}-py3-none-any.whl",
        "wheel_sha256": args.wheel_sha256,
        "wheel_bytes": len(raw),
        "files": len(files),
        "destination": str(destination),
        "parent": parent,
        "python": executable(sys.executable),
        "verifier": executable(gh),
        "bootstrap_sha256": digest(script),
        "online_verification": args.online_verification,
        "offline_inputs": {key: digest(value) for key, value in proof_inputs.items()},
        "hardware_authorized": False,
        "driver_startup": False,
        "service_changes": False,
    }
    return plan, raw, files, proof_inputs, script


def preview(args):
    plan, *_ = inputs(args)
    destination = Path(plan["destination"])
    if destination.exists() or destination.is_symlink():
        raise ValueError(
            "Destination exists; inspect it, never overwrite an SDK or runtime"
        )
    return {
        "impact": plan,
        "confirm_digest": digest(canonical(plan)),
        "provenance_verified": False,
    }


def verification_command(plan, wheel, proof):
    command = [
        plan["verifier"]["path"],
        "attestation",
        "verify",
        str(wheel),
        "--hostname",
        "github.com",
        "--repo",
        REPOSITORY,
        "--signer-workflow",
        WORKFLOW,
        "--signer-digest",
        plan["commit"],
        "--source-digest",
        plan["commit"],
        "--source-ref",
        f"refs/tags/{plan['release_tag']}",
        "--cert-identity",
        f"https://github.com/{WORKFLOW}@refs/tags/{plan['release_tag']}",
        "--cert-oidc-issuer",
        "https://token.actions.githubusercontent.com",
        "--deny-self-hosted-runners",
        "--predicate-type",
        "https://slsa.dev/provenance/v1",
        "--limit",
        "5",
        "--format",
        "json",
    ]
    if proof:
        command.extend(
            [
                "--bundle",
                str(proof["bundle"]),
                "--custom-trusted-root",
                str(proof["trusted_root"]),
            ]
        )
    return command


def run_verifier(command):
    """Bound verifier time/output without exposing its private diagnostics."""
    with subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GH_HOST": "github.com", "GH_PROMPT_DISABLED": "1"},
    ) as process:
        collected = []

        def read():
            collected.append(process.stdout.read(MAX_PROOF + 1))
            if len(collected[0]) > MAX_PROOF and process.poll() is None:
                process.kill()

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        try:
            code = process.wait(timeout=90)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            reader.join(timeout=5)
        if reader.is_alive() or not collected or len(collected[0]) > MAX_PROOF:
            raise ValueError("Verifier output exceeded its bounds")
        return subprocess.CompletedProcess(command, code, collected[0])


def verify(plan, raw, proof_inputs):
    """Delegate cryptography to trusted gh; never trust unsigned JSON predicates."""
    with tempfile.TemporaryDirectory(
        prefix=".verify-sdk-", dir=plan["parent"]["path"]
    ) as temporary:
        root = Path(temporary)
        wheel = root / plan["wheel_name"]
        wheel.write_bytes(raw)
        proof = {}
        for key, value in proof_inputs.items():
            proof[key] = root / f"{key}.jsonl"
            proof[key].write_bytes(value)
        result = run_verifier(verification_command(plan, wheel, proof))
        if result.returncode != 0 or not 0 < len(result.stdout) <= MAX_PROOF:
            raise ValueError(
                "Release provenance was not verified; nothing installed. Inspect with the independent GitHub CLI"
            )
        values = json.loads(result.stdout)
        if (
            not isinstance(values, list)
            or not values
            or not any(
                subject.get("digest", {}).get("sha256") == plan["wheel_sha256"]
                for item in values
                for subject in item["verificationResult"]["statement"]["subject"]
            )
        ):
            raise ValueError("Verifier returned no matching verified wheel subject")
        return result.stdout


def inspect(destination):
    root = Path(destination).absolute()
    directory(root)
    receipt = json.loads(regular(root / "receipt.json", MAX_PROOF))
    if (
        not isinstance(receipt, dict)
        or set(receipt) != {"plan", "confirm_digest", "inventory", "installed_at"}
        or not isinstance(receipt["plan"], dict)
        or digest(canonical(receipt["plan"])) != receipt["confirm_digest"]
    ):
        raise ValueError("Invalid SDK receipt")
    if receipt["plan"]["destination"] != str(root) or not isinstance(
        receipt["inventory"], dict
    ):
        raise ValueError("SDK receipt belongs to another directory")
    plan = receipt["plan"]
    if (
        plan["schema"] != "airalogy.sdk-bootstrap.v1"
        or plan["repository"] != REPOSITORY
        or datetime.fromisoformat(receipt["installed_at"]).tzinfo is None
        or receipt["inventory"].get("airalogy-instrument-bootstrap.py")
        != plan["bootstrap_sha256"]
        or receipt["inventory"].get(f"artifacts/{plan['wheel_name']}")
        != plan["wheel_sha256"]
        or "provenance.json" not in receipt["inventory"]
    ):
        raise ValueError("SDK receipt has incomplete origin or installation evidence")
    found = set()
    for count, (current, directories, files) in enumerate(
        os.walk(root, followlinks=False)
    ):
        if count > 32768:
            raise ValueError("SDK directory metadata limit exceeded")
        directory(current)
        for name in directories:
            directory(Path(current) / name)
        for name in files:
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            if relative == "receipt.json":
                continue
            found.add(relative)
            if len(found) > 2055 or relative not in receipt["inventory"]:
                raise ValueError("Unexpected installed SDK file")
            if digest(regular(path, MAX_EXPANDED)) != receipt["inventory"][relative]:
                raise ValueError(
                    "Installed SDK changed; do not launch or silently repair it"
                )
    if found != set(receipt["inventory"]):
        raise ValueError("Installed SDK is incomplete")
    return receipt


def install(args):
    plan, raw, files, proof_inputs, script = inputs(args)
    confirmation = digest(canonical(plan))
    if not args.install_authorized or args.confirm_digest != confirmation:
        raise ValueError(
            "Review the exact preview and explicitly confirm SDK installation"
        )
    destination = Path(plan["destination"])
    if destination.exists() or destination.is_symlink():
        receipt = inspect(destination)
        if receipt["confirm_digest"] != confirmation:
            raise ValueError("Existing SDK belongs to another installation preview")
        return {
            "state": "installed",
            "reused": True,
            "destination": str(destination),
            "hardware_authorized": False,
        }
    verified = verify(plan, raw, proof_inputs)
    if (
        directory(destination.parent) != plan["parent"]
        or executable(sys.executable) != plan["python"]
        or executable(plan["verifier"]["path"]) != plan["verifier"]
    ):
        raise ValueError("Installation environment changed after preview")
    # Exclusive publication path, no in-place upgrade. A crash before the final
    # receipt leaves an explicitly incomplete directory for manual inspection.
    destination.mkdir(mode=0o700)
    content = {f"sdk/{name}": value for name, value in files.items()}
    content.update(
        {
            "airalogy-instrument-bootstrap.py": script,
            "provenance.json": verified,
            f"artifacts/{plan['wheel_name']}": raw,
        }
    )
    inventory = {}
    for name, value in content.items():
        path = destination / name
        parent = destination
        for part in path.relative_to(destination).parts[:-1]:
            parent = parent / part
            parent.mkdir(mode=0o700, exist_ok=True)
        with path.open("xb") as target:
            os.fchmod(target.fileno(), 0o400)
            target.write(value)
            target.flush()
            os.fsync(target.fileno())
        inventory[name] = digest(value)
    for current, _directories, _files in os.walk(destination, topdown=False):
        fd = os.open(current, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    with (destination / "receipt.json").open("xb") as target:
        os.fchmod(target.fileno(), 0o600)
        target.write(
            canonical(
                {
                    "plan": plan,
                    "confirm_digest": confirmation,
                    "inventory": inventory,
                    "installed_at": datetime.now(UTC).isoformat(),
                }
            )
        )
        target.flush()
        os.fsync(target.fileno())
    for parent in (destination, destination.parent):
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    inspect(destination)
    return {
        "state": "installed",
        "reused": False,
        "destination": str(destination),
        "hardware_authorized": False,
    }


def launch(args):
    receipt = inspect(args.destination)
    plan = receipt["plan"]
    if executable(sys.executable) != plan["python"]:
        raise ValueError("Python changed; prepare a separate reviewed SDK installation")
    arguments = args.arguments
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    if not arguments or arguments[0] not in MODULES:
        raise ValueError(
            "Select setup, author, pair, package, installation, activation or gateway"
        )
    command = [
        plan["python"]["path"],
        "-I",
        "-S",
        "-B",
        "-c",
        BOOTSTRAP,
        str(Path(plan["destination"]) / "sdk"),
        f"airalogy_instrument_gateway.{MODULES[arguments[0]]}",
        *arguments[1:],
    ]
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PYTHON", "LD_", "DYLD_"))
    }
    os.execve(command[0], command, environment)


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="operation", required=True)
    for name in ("preview", "install"):
        command = commands.add_parser(name)
        for field in ("wheel", "wheel-sha256", "release-tag", "commit", "destination"):
            command.add_argument(f"--{field}", required=True)
        command.add_argument("--gh", help="Independently trusted GitHub CLI executable")
        command.add_argument("--online-verification", action="store_true")
        command.add_argument("--bundle")
        command.add_argument("--trusted-root")
        command.add_argument("--trusted-root-sha256")
        if name == "install":
            command.add_argument("--confirm-digest", required=True)
            command.add_argument("--install-authorized", action="store_true")
    command = commands.add_parser("inspect")
    command.add_argument("--destination", required=True)
    command = commands.add_parser("launch")
    command.add_argument("--destination", required=True)
    command.add_argument("arguments", nargs=argparse.REMAINDER)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.operation == "launch":
            launch(args)
        else:
            result = {
                "preview": preview,
                "install": install,
                "inspect": lambda args: inspect(args.destination),
            }[args.operation](args)
            print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RuntimeError,
        zipfile.BadZipFile,
        subprocess.SubprocessError,
    ):
        print(
            "SDK operation not confirmed. Preserve existing files; check selected release, provenance, private destination and preview. No device permission was granted.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
