"""Owned loopback stateful service. No physical device or external I/O."""

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

TARGET = {
    "identity_reference": "owned-http-controlled-reader",
    "firmware": "simulation-1",
    "application": "owned-controlled-service",
    "application_version": "1.0.0",
    "driver_version": "1.0.0",
    "os_version": "synthetic-service-v1",
}


class Controller:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = "idle"
        self.identifier, self.count = None, None
        self.starts, self.stops, self.polls = 0, 0, 0
        self.owner, self.ready, self.operator = "gateway", True, True
        self.value = 1.25  # Independent supplied result, not calculated by adapter.

    def handle(self, method, path, body=None):
        with self.lock:
            return self._handle(method, path, body)

    def _handle(self, method, path, body):
        if method == "GET" and path == "/v1/identity":
            return 200, {"target": TARGET, "simulation_only": True}
        if method == "GET" and path == "/v1/state":
            if self.state == "running":
                self.polls += 1
                if self.polls >= 2:
                    self.state = "complete"
            return 200, {
                "state": self.state,
                "operation_id": self.identifier,
                "sample_count": self.count,
                "ready": self.ready,
                "owner": self.owner,
                "operator_confirmed": self.operator,
                "simulation_only": True,
            }
        selected = urlsplit(path)
        if method == "GET" and selected.path == "/v1/result":
            if self.state != "complete" or parse_qs(selected.query) != {
                "operation_id": [self.identifier]
            }:
                return 409, {"error": "not_complete_or_wrong_operation"}
            return 200, {
                "operation_id": self.identifier,
                "sample_count": self.count,
                "value": self.value,
                "unit": "synthetic_unit",
                "simulation_only": True,
            }
        if not isinstance(body, dict):
            return 400, {"error": "json_object_required"}
        identifier = body.get("operation_id")
        try:
            if type(identifier) is not str or str(UUID(identifier)) != identifier:
                raise ValueError
        except (ValueError, TypeError):
            return 400, {"error": "exact_operation_required"}
        accepted = {
            "accepted": True,
            "operation_id": identifier,
            "simulation_only": True,
        }
        if method == "PUT" and path == "/v1/parameters":
            if (
                set(body) != {"operation_id", "sample_count"}
                or type(body["sample_count"]) is not int
                or not 1 <= body["sample_count"] <= 96
            ):
                return 400, {"error": "invalid_parameters"}
            if (
                self.state != "idle"
                or self.owner != "gateway"
                or not self.ready
                or not self.operator
            ):
                return 409, {"error": "not_ready"}
            self.identifier, self.count, self.state = (
                identifier,
                body["sample_count"],
                "configured",
            )
            return 200, accepted
        if method != "POST" or set(body) != {"operation_id"}:
            return 404, {"error": "unknown_operation"}
        if identifier != self.identifier:
            return 409, {"error": "wrong_operation"}
        if path == "/v1/start":
            if (
                self.state != "configured"
                or self.owner != "gateway"
                or not self.ready
                or not self.operator
            ):
                return 409, {"error": "not_ready"}
            self.starts += 1
            self.state = "running"
            return 202, accepted
        if path == "/v1/stop":
            if self.state != "stopped":
                self.stops += 1
                self.state = "stopped"
            return 200, accepted
        return 404, {"error": "unknown_operation"}


def make_server(port=0, controller=None):
    selected = controller or Controller()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def dispatch(self):
            body = None
            try:
                if self.command != "GET":
                    size = int(self.headers.get("Content-Length", "0"))
                    if (
                        not 2 <= size <= 65536
                        or self.headers.get("Transfer-Encoding")
                        or self.headers.get("Content-Type") != "application/json"
                    ):
                        raise ValueError
                    self.connection.settimeout(3)
                    body = json.loads(self.rfile.read(size))
                status, result = selected.handle(self.command, self.path, body)
            except (ValueError, OSError):
                status, result = 400, {"error": "invalid_input"}
            raw = json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

        do_GET = dispatch
        do_POST = dispatch
        do_PUT = dispatch

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    port = parser.parse_args().port
    if not 0 <= port <= 65535:
        parser.error("Select port 0 or an available port 1..65535")
    with make_server(port) as service:
        print(
            json.dumps(
                {
                    "origin": f"http://127.0.0.1:{service.server_port}",
                    "simulation_only": True,
                }
            ),
            flush=True,
        )
        try:
            service.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
