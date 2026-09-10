"""Built SDK + actual isolated launch/HTTP checks; no device or Platform request.

Ordinary CI injects ONLY the verifier response (not signature acceptance). Official
release CI must opt into --verify-release, which invokes the real GitHub verifier.
"""

import argparse
import http.client
import importlib.util
import json
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

SPEC = importlib.util.spec_from_file_location(
    "gateway_bootstrap", Path(__file__).parents[1] / "bootstrap.py"
)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def serve(destination, root, arguments, html_marker):
    command = [
        sys.executable,
        "-I",
        "-S",
        "-B",
        str(destination / "airalogy-instrument-bootstrap.py"),
        "launch",
        "--destination",
        str(destination),
        "--",
        *arguments,
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    lines = queue.Queue()

    def read():
        for line in process.stdout:
            lines.put(line)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        address = None
        for _ in range(3):
            line = lines.get(timeout=15).strip()
            if line.startswith("http://127.0.0.1:"):
                address = urlsplit(line)
                break
        assert address and address.fragment
        connection = http.client.HTTPConnection(
            address.hostname, address.port, timeout=5
        )
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 200 and html_marker in response.read()
        connection.close()
        connection = http.client.HTTPConnection(
            address.hostname, address.port, timeout=5
        )
        connection.request(
            "POST",
            "/api",
            json.dumps({"operation": "state", "data": {}}),
            {
                "Content-Type": "application/json",
                "Origin": f"http://{address.netloc}",
                "X-Airalogy-Setup": address.fragment,
            },
        )
        response = connection.getresponse()
        assert response.status == 200
        state = json.loads(response.read())
        assert (
            state["hardware_authorized"] is False
            and state["activation_performed"] is False
        )
        assert list(root.iterdir()) == []
        connection.close()
    finally:
        # Only the owned, empty setup/development server, never a hardware worker.
        process.terminate()
        process.wait(timeout=5)
        reader.join(timeout=5)
        process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--verify-release", action="store_true")
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--commit")
    selected = parser.parse_args()
    if selected.verify_release and not selected.commit:
        parser.error("Real verification requires the exact release commit")
    with tempfile.TemporaryDirectory(
        prefix="airalogy-sdk-bootstrap-test-"
    ) as temporary:
        root = Path(temporary).resolve()
        destination = root / "sdk"
        args = argparse.Namespace(
            wheel=str(selected.wheel.resolve()),
            wheel_sha256=bootstrap.digest(selected.wheel.read_bytes()),
            release_tag=selected.release_tag,
            commit=selected.commit or "a" * 40,
            destination=str(destination),
            gh=shutil.which("gh") if selected.verify_release else sys.executable,
            online_verification=True,
            bundle=None,
            trusted_root=None,
            trusted_root_sha256=None,
            install_authorized=True,
            confirm_digest=None,
        )
        preview = bootstrap.preview(args)
        args.confirm_digest = preview["confirm_digest"]
        if selected.verify_release:
            # Verify the separate bootstrap asset too, before trusting a release
            # attachment rather than this reviewed CI checkout.
            plan, _raw, _files, _proof, script = bootstrap.inputs(args)
            bootstrap.verify(
                {
                    **plan,
                    "wheel_name": "airalogy-instrument-bootstrap.py",
                    "wheel_sha256": bootstrap.digest(script),
                },
                script,
                {},
            )
            bootstrap.install(args)
        else:
            synthetic = subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    [
                        {
                            "verificationResult": {
                                "statement": {
                                    "subject": [
                                        {"digest": {"sha256": args.wheel_sha256}}
                                    ],
                                }
                            }
                        }
                    ]
                ).encode(),
            )
            with patch.object(bootstrap, "run_verifier", return_value=synthetic):
                bootstrap.install(args)
        for name in ("service", "development"):
            (root / name).mkdir(mode=0o700)
        serve(
            destination,
            root / "service",
            ["setup", "--root", str(root / "service")],
            b"identity-form",
        )
        serve(
            destination,
            root / "development",
            ["author", "serve", "--workspace", str(root / "development")],
            b"prepare-form",
        )
        bootstrap.inspect(destination)
        print(
            "Built SDK isolated installation and both authenticated local guides passed; "
            + (
                "REAL release provenance verified"
                if selected.verify_release
                else "SYNTHETIC verifier response, not release provenance"
            )
        )


if __name__ == "__main__":
    main()
