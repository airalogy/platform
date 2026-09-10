"""Authenticated loopback setup UI. Never binds a LAN interface or opens a browser."""

import argparse
import hmac
import json
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .client import GatewayAPIError
from .package_contract import MAX_ARCHIVE_BYTES, strict_json
from .setup_workspace import SetupWorkspace, fields


class SetupServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, workspace, port=0):
        self.workspace = workspace
        self.token = secrets.token_urlsafe(32)
        self.expires_at = time.monotonic() + 3600
        self.slots = threading.BoundedSemaphore(4)
        super().__init__(("127.0.0.1", port), SetupHandler)
        self.host = f"127.0.0.1:{self.server_port}"
        self.origin = f"http://{self.host}"

    @property
    def url(self):
        return f"{self.origin}/#{self.token}"

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class SetupHandler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(10)
        super().setup()

    def log_message(self, _format, *args):
        # No URLs, pairing codes, token headers, paths or remote bodies in logs.
        pass

    def _send(self, code, value, content_type="application/json"):
        raw = (
            json.dumps(value, ensure_ascii=True).encode()
            if content_type == "application/json"
            else value
        )
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        self.end_headers()
        self.wfile.write(raw)

    def _host(self):
        return self.headers.get_all("Host") == [self.server.host]

    def do_GET(self):
        if not self._host():
            self._send(421, {"error": "Open the exact local setup address"})
            return
        assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/style.css": ("style.css", "text/css; charset=utf-8"),
        }
        if self.path not in assets:
            self._send(404, {"error": "Not found"})
            return
        name, mime = assets[self.path]
        self._send(200, (Path(__file__).parent / "setup_ui" / name).read_bytes(), mime)

    def do_POST(self):
        if not self._host() or self.headers.get_all("Origin") != [self.server.origin]:
            self._send(
                403,
                {"error": "Use the local setup page; cross-origin requests are denied"},
            )
            return
        token = self.headers.get("X-Airalogy-Setup", "")
        if (
            len(self.headers.get_all("X-Airalogy-Setup", [])) != 1
            or time.monotonic() >= self.server.expires_at
            or not hmac.compare_digest(token.encode(), self.server.token.encode())
        ):
            self._send(
                401,
                {
                    "error": "Setup session expired or unauthorized. Restart the local assistant; saved files remain."
                },
            )
            return
        kind = {
            "/upload/package": "package",
            "/upload/sdk_wheel": "sdk_wheel",
            "/upload/config": "config",
        }.get(self.path)
        expected_type = "application/octet-stream" if kind else "application/json"
        if (
            (self.path != "/api" and not kind)
            or self.headers.get("Content-Type") != expected_type
            or self.headers.get("Transfer-Encoding")
        ):
            self._send(400, {"error": "Unsupported request"})
            return
        try:
            lengths = self.headers.get_all("Content-Length", [])
            limit = (
                (16384 if kind == "config" else MAX_ARCHIVE_BYTES) if kind else 32768
            )
            if (
                len(lengths) != 1
                or not lengths[0].isdigit()
                or not 0 < int(lengths[0]) <= limit
            ):
                raise ValueError("Setup request size is invalid")
            size = int(lengths[0])
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError("Incomplete setup request")
            if kind:
                self._send(200, self.server.workspace.upload(kind, raw))
                return
            body = strict_json(raw)
            fields(body, ["operation", "data"])
            result = self.server.workspace.dispatch(body["operation"], body["data"])
            self._send(200, result)
        except GatewayAPIError:
            # API error bodies may contain arbitrary/private details. Do not
            # forward them, transport exceptions, or credentials to the browser.
            self._send(
                409,
                {
                    "code": "platformFailed",
                    "error": "Platform did not confirm this operation. Check the saved pairing or installation status before retrying; do not create another identity.",
                    "uncertain": True,
                },
            )
        except (ValueError, TypeError, KeyError, OSError, RuntimeError):
            # Filenames and validation errors can embed selected private content.
            self._send(
                409,
                {
                    "code": "fileFailed" if kind else "setupFailed",
                    "error": "Setup could not confirm this operation. Check the selected scope, files, permissions and fresh preview. Preserve saved requests and refresh status before retrying.",
                    "uncertain": True,
                },
            )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Existing private service directory (0700), shared with the Gateway journal",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Loopback port; default chooses an available port",
    )
    args = parser.parse_args(argv)
    try:
        workspace = SetupWorkspace(args.root)
        with SetupServer(workspace, args.port) as server:
            print(
                "Open this private local address in your browser. Do not share it; the session expires in one hour.",
                flush=True,
            )
            print(server.url, flush=True)
            print(
                "No browser, driver, model or instrument is started automatically. Ctrl-C closes the assistant, not any independently running Gateway.",
                flush=True,
            )
            server.serve_forever()
        return 0
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError):
        print(
            "Setup could not start. Use a real owner-only service directory and an available local port.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
