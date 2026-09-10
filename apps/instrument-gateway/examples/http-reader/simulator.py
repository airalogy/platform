"""Owned HTTP reader fixture. No device, filesystem, model or external network access."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def payload(path):
    if path == "/v1/identity":
        return {
            "simulation_only": True,
            "target": {
                "identity_reference": "owned-http-reader-fixture",
                "firmware": "synthetic-1",
                "application": "owned-http-reader",
                "application_version": "1.0.0",
                "driver_version": "1.0.0",
                "os_version": "synthetic-service-v1",
            },
        }
    for sample, value in (("sample-A", 1.25), ("sample-B", 4.75)):
        if path == f"/v1/result?sample_id={sample}":
            return {
                "sample_id": sample,
                "value": value,
                "unit": "synthetic_unit",
                "simulation_only": True,
            }
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        result = payload(self.path)
        raw = json.dumps(result if result is not None else {}).encode()
        self.send_response(200 if result is not None else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("Choose port 0 (automatic) or an available port 1..65535")
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as service:
        # No secrets: this public fixture has no authentication or real data.
        print(
            json.dumps(
                {
                    "simulation_only": True,
                    "origin": f"http://127.0.0.1:{service.server_port}",
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
