"""Bounded Docker test runner. It never falls back to executing on the host."""

import base64
import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

from .package_contract import inspect_package, sha256, wheel_identity


class SandboxError(RuntimeError):
    pass


def sandbox_command(executable, image, name):
    if not re.fullmatch(r"(?:[a-zA-Z0-9._:/-]+@)?sha256:[a-f0-9]{64}", image):
        raise ValueError(
            "Sandbox requires an immutable, locally available image digest"
        )
    return [
        executable,
        "run",
        "--pull",
        "never",
        "--name",
        name,
        "--rm",
        "--interactive",
        "--log-driver",
        "none",
        "--init",
        "--user",
        "65532:65532",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "64",
        "--memory",
        "512m",
        "--memory-swap",
        "512m",
        "--cpus",
        "1",
        "--tmpfs",
        "/work:rw,nosuid,nodev,size=536870912,uid=65532,gid=65532,mode=0700",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=67108864,uid=65532,gid=65532,mode=0700",
        "--workdir",
        "/work",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--entrypoint",
        "python",
        image,
        "-I",
        "-c",
        Path(__file__).with_name("_sandbox_runner.py").read_text(),
    ]


def test_package(raw, *, sdk_wheel, trusted_sdk_digest, image, timeout_seconds=60):
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
        raise ValueError("Sandbox timeout must be between 1 and 300 seconds")
    inspection = inspect_package(raw)
    if sha256(sdk_wheel) != trusted_sdk_digest:
        raise ValueError(
            "Gateway SDK artifact does not match the separately trusted digest"
        )
    sdk = wheel_identity(sdk_wheel)
    if (
        sdk["name"] != "airalogy-instrument-gateway"
        or sdk["version"]
        not in inspection["manifest"]["compatibility"]["gateway_versions"]
    ):
        raise ValueError(
            "Package does not declare compatibility with the trusted Gateway SDK"
        )
    executable = shutil.which("docker")
    if not executable:
        raise SandboxError(
            "Docker is unavailable; adapter code will not run on the host"
        )
    name = "airalogy-adapter-test-" + uuid4().hex
    command = sandbox_command(executable, image, name)
    probe = subprocess.run(
        [executable, "image", "inspect", image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
        check=False,
    )
    if probe.returncode:
        raise SandboxError("Trusted sandbox image is not installed locally")
    packet = json.dumps(
        {
            "package": base64.b64encode(raw).decode(),
            "sdk": base64.b64encode(sdk_wheel).decode(),
            "sdk_name": f"airalogy_instrument_gateway-{sdk['version']}-py3-none-any.whl",
        }
    ).encode()
    started = time.monotonic()
    timed_out = False
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    stream = process.stdout
    process.stdout = None  # communicate handles stdin; the bounded reader owns stdout.
    captured = bytearray()
    overflow = threading.Event()

    def drain():
        while chunk := stream.read(8192):
            remaining = 32768 - len(captured)
            captured.extend(chunk[:remaining])
            if len(chunk) > remaining:
                overflow.set()

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        process.communicate(input=packet, timeout=timeout_seconds)
        exit_code = process.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        exit_code = None
    finally:
        # Remove only this invocation's uniquely named container, then establish
        # terminal state. A lost daemon response is not proof of termination.
        cleanup = subprocess.run(
            [executable, "rm", "--force", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        reader.join(timeout=10)
        stream.close()
        if reader.is_alive():
            raise SandboxError("Sandbox output stream did not terminate")
        if cleanup.returncode:
            check = subprocess.run(
                [
                    executable,
                    "container",
                    "ls",
                    "--all",
                    "--filter",
                    f"name=^/{name}$",
                    "--format",
                    "{{.ID}}",
                ],
                capture_output=True,
                timeout=15,
                check=False,
            )
            if check.returncode or check.stdout.strip():
                raise SandboxError(
                    f"Sandbox termination could not be established; inspect {name} before retrying"
                )
    try:
        diagnostic = json.loads(captured) if captured else {}
        if not isinstance(diagnostic, dict):
            diagnostic = {}
    except (ValueError, UnicodeDecodeError):
        diagnostic = {}
    return {
        "schema": "airalogy.adapter-test-report.v1",
        "archive_digest": inspection["archive_digest"],
        "manifest_digest": inspection["manifest_digest"],
        "sdk_digest": trusted_sdk_digest,
        "image": image,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "exit_code": exit_code,
        "passed": exit_code == 0 and not timed_out and not overflow.is_set(),
        "failure_reason": "timeout"
        if timed_out
        else "output_limit"
        if overflow.is_set()
        else {
            0: None,
            21: "python_compatibility",
            22: "wheel_installation",
            23: "dependency_check",
            24: "package_tests",
        }.get(exit_code, "sandbox_process"),
        "untrusted_test_output": str(diagnostic.get("untrusted_test_output", ""))[
            :8000
        ],
        "simulation_only": True,
        "hardware_authorized": False,
        "test_provenance": "package-supplied; not independent physical qualification",
        "isolation": {
            "network": "none",
            "host_mounts": [],
            "capabilities": [],
            "read_only_root": True,
            "memory_mb": 512,
            "pids": 64,
        },
    }
