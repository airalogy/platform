"""Run with the built wheel's isolated Python; no source PYTHONPATH or hardware."""

import http.client
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import airalogy_instrument_gateway.setup_cli as setup
from airalogy_instrument_gateway.authoring_workspace import AuthoringWorkspace
from airalogy_instrument_gateway.setup_workspace import SetupWorkspace


def main():
    assert Path(setup.__file__).is_relative_to(Path(sys.prefix).resolve())
    for command in (
        ["airalogy-instrument-setup", "--help"],
        ["airalogy-instrument-authoring", "serve", "--help"],
    ):
        subprocess.run(
            [str(Path(sys.executable).parent / command[0]), *command[1:]],
            check=True,
            stdout=subprocess.DEVNULL,
            timeout=10,
        )
    check(SetupWorkspace, b"identity-form", b"installation-confirm", "scope", None)
    check(AuthoringWorkspace, b"prepare-form", b"run-confirm", "sessions", [])
    print(
        "Installed setup/development entry points, UI assets and authenticated loopback state passed"
    )


def check(workspace, html_marker, js_marker, state_key, expected):
    with tempfile.TemporaryDirectory(prefix="airalogy-wheel-setup-") as directory:
        server = setup.SetupServer(workspace(Path(directory).resolve()))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            for path, marker in (
                ("/", html_marker),
                ("/app.js", js_marker),
                ("/style.css", b"@media"),
            ):
                connection = http.client.HTTPConnection(server.host, timeout=5)
                connection.request("GET", path)
                response = connection.getresponse()
                assert response.status == 200
                assert marker in response.read()
                assert response.getheader("Cache-Control") == "no-store"
                connection.close()
            connection = http.client.HTTPConnection(server.host, timeout=5)
            connection.request(
                "POST",
                "/api",
                json.dumps({"operation": "state", "data": {}}),
                {
                    "Origin": server.origin,
                    "Content-Type": "application/json",
                    "X-Airalogy-Setup": server.token,
                },
            )
            response = connection.getresponse()
            assert response.status == 200
            state = json.loads(response.read())
            connection.close()
            assert state[state_key] == expected
            assert state["activation_performed"] is False
            assert list(Path(directory).iterdir()) == []
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


if __name__ == "__main__":
    main()
