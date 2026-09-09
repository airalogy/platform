"""Trusted container bootstrap; invoked as source, before importing any adapter."""

import base64
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import zipfile


def main():
    packet = json.loads(sys.stdin.buffer.read(180 * 1024 * 1024))
    root = pathlib.Path("/work")
    sdk_path = root / "sdk.whl"
    sdk_path.write_bytes(base64.b64decode(packet["sdk"], validate=True))
    # Host checks every path, digest, member size and wheel RECORD before launch.
    with zipfile.ZipFile(
        io.BytesIO(base64.b64decode(packet["package"], validate=True))
    ) as archive:
        archive.extractall(root / "bundle")
    manifest = json.loads((root / "bundle/manifest.json").read_bytes())
    if (
        f"{sys.version_info.major}.{sys.version_info.minor}"
        not in manifest["compatibility"]["python_versions"]
    ):
        return 21
    # Preserve the valid SDK wheel filename required by pip.
    sdk_path = sdk_path.rename(root / packet["sdk_name"])
    wheel_paths = [
        str(root / "bundle" / entry["path"])
        for entry in manifest["files"]
        if entry["role"].endswith("wheel")
    ]
    environment = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": "/work/site",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PIP_CONFIG_FILE": "/dev/null",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "HOME": "/work",
    }
    install = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--no-compile",
            "--target",
            "/work/site",
            str(sdk_path),
            *wheel_paths,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
        check=False,
    )
    if install.returncode:
        return 22
    check = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
        check=False,
    )
    if check.returncode:
        return 23
    # Test contents/results are package-supplied. Exit zero is not independent
    # scientific validation and never grants source trust or hardware authority.
    with tempfile.TemporaryFile(dir="/work") as diagnostics:
        tests = subprocess.run(
            [
                sys.executable,
                "-c",
                "import unittest; suite=unittest.defaultTestLoader.discover('/work/bundle/tests'); assert suite.countTestCases() > 0, 'No tests'; result=unittest.TextTestRunner().run(suite); raise SystemExit(not result.wasSuccessful())",
            ],
            stdout=diagnostics,
            stderr=diagnostics,
            env=environment,
            check=False,
        )
        diagnostics.seek(0, 2)
        length = diagnostics.tell()
        diagnostics.seek(max(0, length - 8000))
        print(
            json.dumps(
                {
                    "untrusted_test_output": diagnostics.read().decode(
                        "utf-8", errors="replace"
                    ),
                    "truncated": length > 8000,
                }
            ),
            flush=True,
        )
    return 0 if tests.returncode == 0 else 24


if __name__ == "__main__":
    raise SystemExit(main())
