import hashlib
import json
import os
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from airalogy_instrument_gateway.http_read import (
    HttpReadClient,
    HttpReadError,
    HttpReadOperation,
    validate_http_read_config,
)


def config(port=1, **changes):
    return {
        "schema": "airalogy.http-read-config.v1",
        "origin": f"http://127.0.0.1:{port}",
        "address": "127.0.0.1",
        "allow_plaintext": True,
        "headers": {},
        **changes,
    }


@contextmanager
def server(responder, *, tls=None):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass

        def do_GET(self):
            calls.append((self.path, dict(self.headers)))
            try:
                responder(self)
            except (BrokenPipeError, ConnectionResetError):
                pass

    instance = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    instance.daemon_threads = True
    if tls:
        instance.socket = tls.wrap_socket(instance.socket, server_side=True)
    worker = threading.Thread(target=instance.serve_forever, daemon=True)
    worker.start()
    try:
        yield instance.server_port, calls
    finally:
        instance.shutdown()
        instance.server_close()
        worker.join(timeout=2)


def response(
    handler, raw=b'{"value":0.42,"unit":"synthetic_unit"}', *, status=200, headers=None
):
    handler.send_response(status)
    for key, value in headers or [
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(raw))),
    ]:
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(raw)


class HttpReadTests(unittest.TestCase):
    def test_configuration_is_explicit_canonical_and_does_not_connect(self):
        with patch(
            "socket.create_connection", side_effect=AssertionError("unexpected network")
        ):
            HttpReadClient(config(), {"result": HttpReadOperation("/result")})
            for override in [
                {"origin": "https://reader.example.test", "allow_plaintext": False},
                {"origin": "https://[::1]", "address": "::1", "allow_plaintext": False},
            ]:
                validate_http_read_config(config(**override))
        for changes in [
            {"origin": "http://127.0.0.1:1/"},
            {"origin": "http://user:secret@127.0.0.1:1"},
            {"origin": "http://127.0.0.1:1?secret=1"},
            {"origin": "http://127.0.0.1:1#x"},
            {"origin": "file:///private/secret"},
            {"origin": "http://127.0.0.1:01"},
            {"origin": "http://127.0.0.1:0"},
            {"origin": "http://127.0.0.1:65536"},
            {"origin": "http://reader..example.test"},
            {"origin": "https://Reader.example.test"},
            {"origin": "http://127.0.0.2", "address": "127.0.0.1"},
            {"address": "localhost"},
            {"address": "127.000.0.1"},
            {"address": "0.0.0.0"},
            {"address": "224.0.0.1"},
            {"address": "fe80::1%en0"},
            {"allow_plaintext": False},
            {"allow_plaintext": 1},
            {"extra": "field"},
            {"headers": {"Host": "other.invalid"}},
            {"headers": {"Cookie": "private"}},
            {"headers": {"X-Api-Key": "private\r\nHost: other.invalid"}},
            {"headers": {"Authorization": "aigw_" + "A" * 43}},
            {"headers": {"X-API-Key": "one", "x-api-key": "two"}},
        ]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_http_read_config(config(**changes))

    def test_reviewed_operations_reject_urls_traversal_and_dynamic_paths(self):
        for path in [
            "//other.invalid",
            "https://other.invalid/x",
            "/../x",
            "/x/./y",
            "/x?token=a",
            "/x#y",
            "/%2e%2e/x",
            "/x\\y",
            "/x/{id}",
            "/x\r\ny",
        ]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                HttpReadOperation(path)
        for options in [
            {"query_fields": ["sample"]},
            {"query_fields": ("sample", "sample")},
            {"query_fields": ("a&b",)},
            {"max_response_bytes": True},
            {"max_response_bytes": 0},
            {"max_response_bytes": 1048577},
        ]:
            with self.assertRaises(ValueError):
                HttpReadOperation("/result", **options)
        with self.assertRaises(ValueError):
            HttpReadClient(config(), {"result": {"path": "/result"}})

    def test_real_get_has_exact_path_query_headers_and_original_bytes_without_proxy_or_dns(
        self,
    ):
        raw = '{"value":0.42,"unit":"合成单位"}'.encode()
        with server(lambda h: response(h, raw)) as (port, calls):
            settings = config(
                port,
                origin=f"http://reader.example.test:{port}",
                headers={"X-Api-Key": "synthetic-private-key"},
            )
            client = HttpReadClient(
                settings, {"result": HttpReadOperation("/v1/result", ("sample",))}
            )
            settings["origin"] = "http://other.invalid"
            settings["headers"]["X-Api-Key"] = "changed"
            original = socket.getaddrinfo

            def numeric_only(host, *args, **kwargs):
                self.assertEqual(host, "127.0.0.1")
                return original(host, *args, **kwargs)

            with (
                patch.dict(
                    os.environ,
                    {
                        "http_proxy": "http://never-contact.invalid:1",
                        "HTTP_PROXY": "http://never-contact.invalid:1",
                    },
                ),
                patch("socket.getaddrinfo", numeric_only),
            ):
                result = client.get("result", {"sample": "A & /?值"})
            self.assertEqual(result.raw, raw)
            self.assertEqual(result.data["unit"], "合成单位")
            self.assertEqual(result.sha256, hashlib.sha256(raw).hexdigest())
            self.assertTrue(result.received_at.endswith("+00:00"))
            self.assertNotIn("合成单位", repr(result))
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], "/v1/result?sample=A+%26+%2F%3F%E5%80%BC")
            self.assertEqual(calls[0][1]["Host"], f"reader.example.test:{port}")
            self.assertEqual(calls[0][1]["X-Api-Key"], "synthetic-private-key")

    def test_unknown_queries_operations_and_cancelled_inputs_do_not_contact_server(
        self,
    ):
        with server(response) as (port, calls):
            client = HttpReadClient(
                config(port), {"result": HttpReadOperation("/result", ("sample",))}
            )
            for operation, query, timeout in [
                ("start", {"sample": "A"}, 5),
                ("result", {}, 5),
                ("result", {"sample": "A", "path": "/start"}, 5),
                ("result", {"sample": 1}, 5),
                ("result", {"sample": "x\n"}, 5),
                ("result", {"sample": "\ud800"}, 5),
                ("result", {"sample": "x"}, float("nan")),
                ("result", {"sample": "x"}, 31),
                ("result", {"sample": "aiinterface_" + "A" * 43}, 5),
            ]:
                with self.assertRaises(HttpReadError) as error:
                    client.get(operation, query, timeout_seconds=timeout)
                self.assertFalse(error.exception.request_may_have_been_sent)
            stop = threading.Event()
            stop.set()
            with self.assertRaises(HttpReadError) as error:
                client.get("result", {"sample": "A"}, stop_event=stop)
            self.assertEqual(error.exception.code, "cancelled")
            self.assertFalse(calls)

    def test_no_redirect_auth_retry_or_response_secret_in_errors(self):
        for status in [301, 302, 307, 308, 401, 429, 500]:
            with (
                self.subTest(status=status),
                server(
                    lambda h, status=status: response(
                        h,
                        b"private-server-diagnostic",
                        status=status,
                        headers=[
                            ("Location", "http://never-contact.invalid"),
                            ("Set-Cookie", "private-cookie"),
                            ("Content-Length", "25"),
                        ],
                    )
                ) as (port, calls),
            ):
                client = HttpReadClient(
                    config(port), {"read": HttpReadOperation("/read")}
                )
                with self.assertRaises(HttpReadError) as error:
                    client.get("read")
                self.assertTrue(error.exception.request_may_have_been_sent)
                self.assertEqual(error.exception.code, "http_status")
                self.assertEqual(
                    str(error.exception), "Instrument HTTP read failed: http_status"
                )
                self.assertEqual(len(calls), 1)

    def test_response_headers_size_encoding_and_strict_json(self):
        cases = [
            (b"{}", [("Content-Type", "text/html")]),
            (
                b"{}",
                [("Content-Type", "application/json"), ("Content-Encoding", "gzip")],
            ),
            (
                b"{}",
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", "2"),
                    ("Content-Length", "2"),
                ],
            ),
            (
                b"{}",
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", "2"),
                    ("Transfer-Encoding", "chunked"),
                ],
            ),
            (
                b"{}",
                [("Content-Type", "application/json"), ("Content-Length", "10000000")],
            ),
            (b"{}", [("Content-Type", "application/json"), ("Content-Length", "20")]),
            (b"x" * 100, [("Content-Type", "application/json")]),
            (b'{"a":1,"a":2}', None),
            (b'{"x":NaN}', None),
            (b'{"x":1e9999}', None),
            (b'{"x":' + b"[" * 70 + b"0" + b"]" * 70 + b"}", None),
            (b"[]", None),
            ('{"x":1}'.encode("utf-16"), None),
        ]
        for raw, headers in cases:

            def respond(handler, raw=raw, headers=headers):
                response(handler, raw, headers=headers)
                handler.close_connection = True

            with (
                self.subTest(raw=raw, headers=headers),
                server(respond) as (port, calls),
            ):
                with self.assertRaises(HttpReadError) as error:
                    HttpReadClient(
                        config(port),
                        {"read": HttpReadOperation("/read", max_response_bytes=64)},
                    ).get("read")
                self.assertTrue(error.exception.request_may_have_been_sent)
                self.assertEqual(len(calls), 1)

    def test_chunked_read_is_bounded_and_does_not_collect_server_cookies(self):
        with server(
            lambda h: response(
                h,
                b"2\r\n{}\r\n0\r\n\r\n",
                headers=[
                    ("Content-Type", "application/json"),
                    ("Transfer-Encoding", "chunked"),
                    ("Set-Cookie", "private=secret"),
                ],
            )
        ) as (port, calls):
            client = HttpReadClient(config(port), {"read": HttpReadOperation("/read")})
            self.assertEqual(client.get("read").data, {})
            self.assertEqual(client.get("read").data, {})
            self.assertEqual(
                len(calls), 2
            )  # Two explicit invocations, no implicit retry.
            self.assertTrue(all("Cookie" not in headers for _, headers in calls))

    def test_cancel_during_json_validation_does_not_return_a_success(self):
        stop = threading.Event()

        def parse(_raw):
            stop.set()
            return {"value": 0.42}

        with server(response) as (port, calls):
            client = HttpReadClient(config(port), {"read": HttpReadOperation("/read")})
            with (
                patch("airalogy_instrument_gateway.http_read._json_result", parse),
                self.assertRaises(HttpReadError) as error,
            ):
                client.get("read", stop_event=stop)
            self.assertEqual(error.exception.code, "cancelled")
            self.assertTrue(error.exception.request_may_have_been_sent)
            self.assertEqual(len(calls), 1)

    def test_deadline_cancels_slow_response_and_client_is_not_left_busy(self):
        def slow(handler):
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            for _ in range(100):
                handler.wfile.write(b" ")
                handler.wfile.flush()
                time.sleep(0.03)

        with server(slow) as (port, calls):
            client = HttpReadClient(config(port), {"read": HttpReadOperation("/read")})
            start = time.monotonic()
            with self.assertRaises(HttpReadError) as error:
                client.get("read", timeout_seconds=0.2)
            self.assertLess(time.monotonic() - start, 1.5)
            self.assertEqual(error.exception.code, "deadline")
            self.assertTrue(error.exception.request_may_have_been_sent)
            self.assertEqual(len(calls), 1)
            self.assertTrue(client._lock.acquire(blocking=False))
            client._lock.release()

    def test_cancellation_interrupts_headers_and_parallel_read_fails_without_new_request(
        self,
    ):
        entered, release, stop = threading.Event(), threading.Event(), threading.Event()

        def blocked(handler):
            entered.set()
            release.wait(3)
            response(handler)

        with server(blocked) as (port, calls):
            client = HttpReadClient(config(port), {"read": HttpReadOperation("/read")})
            errors = []

            def read():
                try:
                    client.get("read", stop_event=stop)
                except HttpReadError as error:
                    errors.append(error)

            worker = threading.Thread(target=read, daemon=True)
            worker.start()
            self.assertTrue(entered.wait(2))
            with self.assertRaises(HttpReadError) as busy:
                client.get("read")
            self.assertEqual(busy.exception.code, "busy")
            self.assertFalse(busy.exception.request_may_have_been_sent)
            stop.set()
            worker.join(timeout=1)
            release.set()
            self.assertFalse(worker.is_alive())
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0].code, "cancelled")
            self.assertTrue(errors[0].request_may_have_been_sent)
            self.assertEqual(len(calls), 1)

    @unittest.skipUnless(os.name == "posix", "Private POSIX configuration")
    def test_configuration_file_is_private_not_a_credential_or_ambiguous_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path = root / "http.json"
            path.write_text(json.dumps(config()))
            path.chmod(0o600)
            HttpReadClient.from_file(path, {"read": HttpReadOperation("/read")})
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                HttpReadClient.from_file(path, {"read": HttpReadOperation("/read")})
            path.chmod(0o600)
            path.write_text(
                json.dumps(config()).replace(
                    '"headers": {}', '"headers": {}, "headers": {}'
                )
            )
            with self.assertRaises(ValueError):
                HttpReadClient.from_file(path, {"read": HttpReadOperation("/read")})

    def test_tls_untrusted_certificate_fails_before_sending_http_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            certificate, key = root / "cert.pem", root / "key.pem"
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-subj",
                    "/CN=synthetic.invalid",
                    "-keyout",
                    str(key),
                    "-out",
                    str(certificate),
                ],
                check=True,
                capture_output=True,
                timeout=15,
            )
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certificate, key)
            with server(response, tls=context) as (port, calls):
                client = HttpReadClient(
                    config(
                        port,
                        origin=f"https://127.0.0.1:{port}",
                        allow_plaintext=False,
                        headers={"Authorization": "Bearer synthetic-secret"},
                    ),
                    {"read": HttpReadOperation("/read")},
                )
                with self.assertRaises(HttpReadError) as error:
                    client.get("read")
                self.assertFalse(error.exception.request_may_have_been_sent)
                self.assertFalse(calls)

    def test_tls_verifies_original_hostname_with_explicit_test_trust_and_pinned_ip(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            certificate, key = root / "cert.pem", root / "key.pem"
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-subj",
                    "/CN=reader.example.test",
                    "-addext",
                    "subjectAltName=DNS:reader.example.test",
                    "-keyout",
                    str(key),
                    "-out",
                    str(certificate),
                ],
                check=True,
                capture_output=True,
                timeout=15,
            )
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certificate, key)
            names = []
            context.set_servername_callback(lambda sock, name, ctx: names.append(name))
            with (
                server(response, tls=context) as (port, calls),
                patch.dict(
                    os.environ,
                    {"SSL_CERT_FILE": str(certificate), "SSL_CERT_DIR": str(root)},
                ),
            ):
                for host in ("wrong.example.test", "reader.example.test"):
                    client = HttpReadClient(
                        config(
                            port,
                            origin=f"https://{host}:{port}",
                            allow_plaintext=False,
                            headers={"X-API-Key": "synthetic-private-key"},
                        ),
                        {"read": HttpReadOperation("/read")},
                    )
                    if host == "wrong.example.test":
                        with self.assertRaises(HttpReadError) as error:
                            client.get("read")
                        self.assertFalse(error.exception.request_may_have_been_sent)
                        self.assertFalse(calls)
                    else:
                        self.assertEqual(client.get("read").data["value"], 0.42)
                self.assertEqual(names, ["wrong.example.test", "reader.example.test"])
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0][1]["Host"], f"reader.example.test:{port}")
                self.assertEqual(calls[0][1]["X-API-Key"], "synthetic-private-key")


if __name__ == "__main__":
    unittest.main()
