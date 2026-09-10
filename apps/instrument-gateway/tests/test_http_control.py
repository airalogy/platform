import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_http_read import config as read_config
from test_http_read import response, server

from airalogy_instrument_gateway.http_control import (
    HttpControlClient,
    HttpControlError,
    HttpControlOperation,
    validate_http_control_config,
)
from airalogy_instrument_gateway.http_read import HttpReadClient, HttpReadOperation


def config(port=1, *, enabled=("start",), **extra):
    return {
        **read_config(port),
        "schema": "airalogy.http-control-config.v1",
        "enabled_operations": list(enabled),
        **extra,
    }


class HttpControlTests(unittest.TestCase):
    def test_read_only_config_cannot_enable_writes_and_allowlist_is_explicit(self):
        ops = {"start": HttpControlOperation("POST", "/start", ("id",))}
        with patch(
            "socket.create_connection", side_effect=AssertionError("unexpected I/O")
        ):
            HttpControlClient(config(), ops)
            for value in (
                read_config(),
                config(enabled=()),
                config(enabled=("unknown",)),
                config(enabled=("start", "start")),
            ):
                with self.assertRaises(ValueError):
                    HttpControlClient(value, ops)
            with self.assertRaises(ValueError):
                HttpReadClient(config(), {"start": HttpReadOperation("/start")})
            for method, path, changes in (
                ("DELETE", "/start", {}),
                ("POST", "/../start", {}),
                ("GET", "/read", {"body_fields": ("id",)}),
                ("POST", "/start", {"statuses": (204,)}),
                ("POST", "/start", {"max_request_bytes": 65537}),
            ):
                with self.assertRaises(ValueError):
                    HttpControlOperation(method, path, **changes)
        self.assertEqual(
            validate_http_control_config(config())["enabled_operations"], ["start"]
        )

    def test_actual_post_put_receipts_preserve_bytes_with_fixed_method_and_no_dns(self):
        writes = []
        raw = b'{"accepted":true,"operation_id":"fixed"}'

        def responder(h):
            writes.append(
                (
                    h.command,
                    h.rfile.read(int(h.headers["Content-Length"])),
                    dict(h.headers),
                )
            )
            response(h, raw, status=202)

        with server(responder) as (port, calls):
            client = HttpControlClient(
                config(
                    port,
                    enabled=("configure", "start"),
                    origin=f"http://device.example.test:{port}",
                ),
                {
                    "configure": HttpControlOperation(
                        "PUT", "/parameters", ("count",), statuses=(202,)
                    ),
                    "start": HttpControlOperation(
                        "POST", "/start", ("id",), statuses=(202,)
                    ),
                },
            )
            original = socket.getaddrinfo

            def resolve(host, *args, **kwargs):
                self.assertEqual(host, "127.0.0.1")
                return original(host, *args, **kwargs)

            with patch("socket.getaddrinfo", resolve):
                client.call("configure", {"count": 2})
                result = client.call("start", {"id": "fixed"})
            self.assertEqual(result.raw, raw)
            self.assertEqual(result.status, 202)
            self.assertNotIn("accepted", repr(result))
            self.assertEqual([item[0] for item in writes], ["PUT", "POST"])
            self.assertEqual(json.loads(writes[1][1]), {"id": "fixed"})
            self.assertEqual(writes[1][2]["Host"], f"device.example.test:{port}")
            self.assertEqual(writes[1][2]["Content-Type"], "application/json")
            self.assertEqual(len(calls), 2)

    def test_invalid_payload_and_disabled_operation_do_not_contact_server(self):
        with server(response) as (port, calls):
            client = HttpControlClient(
                config(port),
                {
                    "start": HttpControlOperation(
                        "POST", "/start", ("id",), max_request_bytes=100
                    ),
                    "read": HttpControlOperation("GET", "/state"),
                },
            )
            cyclic = {}
            cyclic["cycle"] = cyclic
            for body in (
                None,
                {},
                {"id": "x", "extra": 1},
                {"id": float("nan")},
                {"id": "x" * 100},
                {"id": "aigw_" + "A" * 43},
                {"id": "\ud800"},
                {"id": cyclic},
                {"id": {1: "bad"}},
                {"id": [1] * 2000},
            ):
                with self.assertRaises(HttpControlError) as error:
                    client.call("start", body)
                self.assertFalse(error.exception.request_may_have_been_sent)
            with self.assertRaises(HttpControlError):
                client.call("read")
            stopped = threading.Event()
            stopped.set()
            with self.assertRaises(HttpControlError):
                client.call("start", {"id": "x"}, stop_event=stopped)
            self.assertFalse(calls)

    def test_lost_write_redirect_and_invalid_body_never_retry_or_leak(self):
        for mode in ("lost", "redirect", "bad_json", "rejected"):

            def responder(h, mode=mode):
                h.rfile.read(int(h.headers["Content-Length"]))
                if mode == "lost":
                    h.connection.shutdown(socket.SHUT_RDWR)
                    h.connection.close()
                elif mode == "redirect":
                    response(
                        h,
                        b"private_response",
                        status=307,
                        headers=[
                            ("Location", "https://never-contact.invalid"),
                            ("Content-Length", "16"),
                        ],
                    )
                else:
                    response(
                        h,
                        b"private_response",
                        status=200 if mode == "bad_json" else 401,
                    )

            with self.subTest(mode=mode), server(responder) as (port, calls):
                client = HttpControlClient(
                    config(port),
                    {"start": HttpControlOperation("POST", "/start", ("id",))},
                )
                with self.assertRaises(HttpControlError) as error:
                    client.call("start", {"id": "x"})
                self.assertTrue(error.exception.request_may_have_been_sent)
                self.assertNotIn("private_response", str(error.exception))
                self.assertEqual(len(calls), 1)

    def test_write_cancellation_and_busy_client_do_not_repeat_transmission(self):
        entered, stop = threading.Event(), threading.Event()

        def responder(h):
            h.rfile.read(int(h.headers["Content-Length"]))
            entered.set()
            time.sleep(0.4)
            response(h)

        with server(responder) as (port, calls):
            client = HttpControlClient(
                config(port), {"start": HttpControlOperation("POST", "/start", ("id",))}
            )
            errors = []

            def run():
                try:
                    client.call("start", {"id": "x"}, stop_event=stop)
                except HttpControlError as error:
                    errors.append(error)

            thread = threading.Thread(target=run)
            thread.start()
            self.assertTrue(entered.wait(2))
            with self.assertRaises(HttpControlError) as busy:
                client.call("start", {"id": "x"})
            self.assertEqual(busy.exception.code, "busy")
            stop.set()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors[0].code, "cancelled")
            self.assertTrue(errors[0].request_may_have_been_sent)
            self.assertEqual(len(calls), 1)

    def test_private_configuration_and_copied_allowlist(self):
        value = config()
        client = HttpControlClient(
            value,
            {
                "start": HttpControlOperation("POST", "/start", ()),
                "stop": HttpControlOperation("POST", "/stop", ()),
            },
        )
        value["enabled_operations"].append("stop")
        with self.assertRaises(HttpControlError):
            client.call("stop", {})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "control.json"
            path.write_text(json.dumps(config()))
            path.chmod(0o600)
            HttpControlClient.from_file(
                path, {"start": HttpControlOperation("POST", "/start", ())}
            )
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                HttpControlClient.from_file(
                    path, {"start": HttpControlOperation("POST", "/start", ())}
                )
