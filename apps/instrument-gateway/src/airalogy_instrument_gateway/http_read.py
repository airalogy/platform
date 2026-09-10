"""Explicit, pinned GET/JSON transport for independently reviewed adapters.

Not an InstrumentAdapter, device discovery, capability grant or network sandbox.
GET is a transport method, not proof that an endpoint has no physical effects.
"""

from __future__ import annotations

import http.client
import ipaddress
import math
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from .credentials import read_private_json
from .package_contract import canonical, sha256, strict_json
from .package_installation import _private_root

_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_PATH = re.compile(r"/(?:[A-Za-z0-9_.~-]+/)*[A-Za-z0-9_.~-]*")
_CREDENTIAL = re.compile(r"(?:aigw|aiinstall|aiauthor|aiinterface)_[A-Za-z0-9_-]{43}")


class HttpReadError(RuntimeError):
    """Sanitized diagnostics; never include addresses, credentials or response text."""

    def __init__(self, code, *, request_may_have_been_sent=False):
        super().__init__(f"Instrument HTTP read failed: {code}")
        self.code = code
        self.request_may_have_been_sent = request_may_have_been_sent


@dataclass(frozen=True)
class HttpReadOperation:
    path: str
    query_fields: tuple[str, ...] = ()
    max_response_bytes: int = 65536

    def __post_init__(self):
        if (
            not isinstance(self.path, str)
            or len(self.path) > 1024
            or not _PATH.fullmatch(self.path)
            or any(part in {".", ".."} for part in self.path.split("/"))
            or type(self.query_fields) is not tuple
            or len(self.query_fields) > 16
            or any(
                not isinstance(key, str) or not _KEY.fullmatch(key)
                for key in self.query_fields
            )
            or len(set(self.query_fields)) != len(self.query_fields)
            or type(self.max_response_bytes) is not int
            or not 1 <= self.max_response_bytes <= 1048576
        ):
            raise ValueError("Invalid fixed HTTP read operation")


@dataclass(frozen=True)
class HttpReadResult:
    data: dict = field(repr=False)
    raw: bytes = field(repr=False)
    sha256: str
    received_at: str


def validate_http_read_config(value):
    """Validate only; no DNS, connection, environment lookup or device access."""
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "origin", "address", "allow_plaintext", "headers"}
        or value["schema"] != "airalogy.http-read-config.v1"
        or len(canonical(value)) > 16384
        or _CREDENTIAL.search(canonical(value).decode())
        or type(value["allow_plaintext"]) is not bool
    ):
        raise ValueError("Invalid private HTTP read configuration")
    try:
        origin = value["origin"]
        if not isinstance(origin, str) or len(origin) > 512 or not origin.isascii():
            raise ValueError
        selected = urlsplit(origin)
        host = selected.hostname
        address = ipaddress.ip_address(value["address"])
        if (
            str(address) != value["address"]
            or address.is_unspecified
            or address.is_multicast
            or "%" in value["address"]
            or not host
            or selected.username is not None
            or selected.password is not None
            or selected.path
            or selected.query
            or selected.fragment
            or selected.scheme not in {"http", "https"}
            or (selected.scheme == "http" and not value["allow_plaintext"])
        ):
            raise ValueError
        try:
            host_address = ipaddress.ip_address(host)
        except ValueError:
            if (
                len(host) > 253
                or all(char in "0123456789." for char in host)
                or any(
                    not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                    for label in host.split(".")
                )
            ):
                raise ValueError from None
        else:
            if str(host_address) != host or host_address != address:
                raise ValueError
        port = selected.port
        authority = f"[{host}]" if ":" in host else host
        authority += f":{port}" if port is not None else ""
        if origin != f"{selected.scheme}://{authority}" or (
            port is not None and not 1 <= port <= 65535
        ):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError(
            "Select one canonical origin and an explicit unicast IP address"
        ) from None
    headers = value["headers"]
    if not isinstance(headers, dict) or len(headers) > 8:
        raise ValueError("Invalid private HTTP authentication headers")
    lowered = set()
    for key, content in headers.items():
        if (
            not isinstance(key, str)
            or not _KEY.fullmatch(key)
            or key.lower() in lowered
            or key.lower() not in {"authorization", "x-api-key"}
            or not isinstance(content, str)
            or not 1 <= len(content) <= 4096
            or any(ord(char) < 32 or ord(char) > 126 for char in content)
            or not content.strip()
        ):
            raise ValueError(
                "Only bounded explicit Authorization or X-API-Key headers are supported"
            )
        lowered.add(key.lower())
    return strict_json(canonical(value))


class _PinnedConnection(http.client.HTTPConnection):
    def __init__(self, config, timeout):
        parsed = urlsplit(config["origin"])
        super().__init__(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            timeout=timeout,
        )
        self.address = config["address"]
        self.use_tls = parsed.scheme == "https"
        self.transport_socket = None

    def connect(self):
        # Numeric address only: do not resolve server-supplied or DNS targets.
        self.sock = socket.create_connection((self.address, self.port), self.timeout)
        self.transport_socket = self.sock
        if self.use_tls:
            context = ssl.create_default_context()
            context.set_alpn_protocols(["http/1.1"])
            self.sock = context.wrap_socket(
                self.sock, server_hostname=self.host, do_handshake_on_connect=False
            )
            self.transport_socket = self.sock
            self.sock.do_handshake()

    def interrupt(self):
        sock = self.transport_socket
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _json_result(raw):
    raw.decode("utf-8")  # Do not auto-detect a different response encoding.
    result = strict_json(raw)
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object")  # noqa: TRY004 - untrusted response validation
    pending = [(result, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > 64 or (type(value) is float and not math.isfinite(value)):
            raise ValueError("Invalid JSON depth or numeric value")
        if isinstance(value, (dict, list)):
            pending.extend(
                (item, depth + 1)
                for item in (value.values() if isinstance(value, dict) else value)
            )
    return result


def read_http_read_config(path: Path):
    selected = Path(path)
    if not selected.is_absolute():
        raise ValueError("Select an absolute private HTTP configuration file")
    _private_root(selected.parent)
    return validate_http_read_config(read_private_json(selected, strict=True))


class HttpReadClient:
    """One non-retrying request at a time, using only code-reviewed operations.

    The explicit IP and origin are local configuration, not job/model arguments.
    Transport cancellation never establishes a physical safe stop.
    """

    def __init__(self, config: dict, operations: dict[str, HttpReadOperation]):
        self._config = validate_http_read_config(config)
        if (
            not isinstance(operations, dict)
            or not 1 <= len(operations) <= 32
            or any(
                not isinstance(key, str)
                or not _KEY.fullmatch(key)
                or type(value) is not HttpReadOperation
                for key, value in operations.items()
            )
        ):
            raise ValueError("Select fixed HTTP operations in reviewed adapter code")
        self._operations = dict(operations)
        self._lock = threading.Lock()

    @classmethod
    def from_file(cls, path: Path, operations: dict[str, HttpReadOperation]):
        return cls(read_http_read_config(path), operations)

    def get(
        self,
        operation: str,
        query: dict[str, str] | None = None,
        *,
        timeout_seconds: float = 5,
        stop_event: threading.Event | None = None,
    ) -> HttpReadResult:
        contract = (
            self._operations.get(operation) if isinstance(operation, str) else None
        )
        query = {} if query is None else query
        if (
            contract is None
            or not isinstance(query, dict)
            or set(query) != set(contract.query_fields)
            or any(
                not isinstance(value, str)
                or any(
                    ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF
                    for char in value
                )
                or len(value.encode()) > 1024
                or _CREDENTIAL.search(value)
                for value in query.values()
            )
            or type(timeout_seconds) not in {int, float}
            or not math.isfinite(timeout_seconds)
            or not 0.1 <= timeout_seconds <= 30
        ):
            raise HttpReadError("invalid_operation")
        if stop_event is not None and not isinstance(stop_event, threading.Event):
            raise HttpReadError("invalid_stop_event")
        if not self._lock.acquire(blocking=False):
            raise HttpReadError("busy")
        finished = threading.Event()
        deadline = time.monotonic() + timeout_seconds
        connection = _PinnedConnection(self._config, timeout_seconds)
        sent = False

        def check():
            if stop_event is not None and stop_event.is_set():
                raise HttpReadError("cancelled", request_may_have_been_sent=sent)
            if time.monotonic() >= deadline:
                raise HttpReadError("deadline", request_may_have_been_sent=sent)

        def watch():
            while not finished.wait(0.02):
                if (
                    stop_event is not None and stop_event.is_set()
                ) or time.monotonic() >= deadline:
                    connection.interrupt()
                    # Keep checking until the worker unwinds: connect/handshake
                    # may be between acquiring and publishing a socket.

        watcher = threading.Thread(target=watch, daemon=True)
        try:
            check()
            path = contract.path
            if query:
                path += "?" + urlencode(sorted(query.items()))
            headers = {
                **self._config["headers"],
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Connection": "close",
                "Host": urlsplit(self._config["origin"]).netloc,
            }
            watcher.start()
            connection.connect()
            check()
            sent = True  # Conservative: errors do not prove that GET was unsent.
            connection.request("GET", path, headers=headers)
            with connection.getresponse() as response:
                check()
                if response.status != 200:
                    raise HttpReadError("http_status", request_may_have_been_sent=True)
                content_type = response.headers.get_all("Content-Type", [])
                lengths = response.headers.get_all("Content-Length", [])
                transfer = response.headers.get_all("Transfer-Encoding", [])
                encoding = response.headers.get_all("Content-Encoding", [])
                if (
                    len(content_type) != 1
                    or not re.fullmatch(
                        r'application/(?:[a-z0-9.-]+\+)?json(?:\s*;\s*charset=(?:utf-8|"utf-8"))?',
                        content_type[0],
                        re.IGNORECASE,
                    )
                    or len(lengths) > 1
                    or (
                        lengths
                        and (
                            not re.fullmatch(r"0|[1-9][0-9]*", lengths[0])
                            or int(lengths[0]) > contract.max_response_bytes
                        )
                    )
                    or (transfer and (transfer != ["chunked"] or lengths))
                    or (encoding and encoding != ["identity"])
                ):
                    raise HttpReadError(
                        "response_headers", request_may_have_been_sent=True
                    )
                raw = bytearray()
                while True:
                    check()
                    chunk = response.read1(
                        min(16384, contract.max_response_bytes + 1 - len(raw))
                    )
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > contract.max_response_bytes:
                        raise HttpReadError(
                            "response_size", request_may_have_been_sent=True
                        )
                check()
                if lengths and len(raw) != int(lengths[0]):
                    raise HttpReadError(
                        "response_incomplete", request_may_have_been_sent=True
                    )
                result = _json_result(bytes(raw))
                check()
                return HttpReadResult(
                    result, bytes(raw), sha256(raw), datetime.now(UTC).isoformat()
                )
        except HttpReadError:
            raise
        except (ValueError, UnicodeError, OSError, http.client.HTTPException):
            check()
            raise HttpReadError(
                "invalid_or_unavailable_response", request_may_have_been_sent=sent
            ) from None
        finally:
            finished.set()
            connection.close()
            if watcher.ident is not None:
                watcher.join(timeout=0.1)
            self._lock.release()
