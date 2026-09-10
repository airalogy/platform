"""Fixed JSON operations for reviewed adapters, never a device-control grant.

Uses the same pinned, bounded, non-retrying transport as HttpReadClient. A separate
configuration explicitly selects operation names; read-only configs cannot enable
writes. Instrument Jobs, source review, installation and qualification remain
independent requirements. This helper is not a network or physical safety sandbox.
"""

import math
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from .credentials import read_private_json
from .http_read import (
    _CREDENTIAL,
    _KEY,
    HttpReadClient,
    HttpReadError,
    HttpReadOperation,
    HttpReadResult,
    validate_http_read_config,
)
from .package_contract import canonical
from .package_installation import _private_root


class HttpControlError(HttpReadError):
    def __init__(self, code, *, request_may_have_been_sent=False):
        RuntimeError.__init__(self, f"Instrument HTTP operation failed: {code}")
        self.code = code
        self.request_may_have_been_sent = request_may_have_been_sent


@dataclass(frozen=True)
class HttpControlOperation:
    method: str
    path: str
    body_fields: tuple[str, ...] = ()
    query_fields: tuple[str, ...] = ()
    max_request_bytes: int = 65536
    max_response_bytes: int = 65536
    statuses: tuple[int, ...] = (200,)

    def __post_init__(self):
        HttpReadOperation(self.path, self.query_fields, self.max_response_bytes)
        if (
            self.method not in ("GET", "POST", "PUT")
            or type(self.body_fields) is not tuple
            or len(self.body_fields) > 32
            or any(
                not isinstance(k, str) or not _KEY.fullmatch(k)
                for k in self.body_fields
            )
            or len(set(self.body_fields)) != len(self.body_fields)
            or (self.method == "GET" and self.body_fields)
            or type(self.max_request_bytes) is not int
            or not 2 <= self.max_request_bytes <= 65536
            or type(self.statuses) is not tuple
            or not 1 <= len(self.statuses) <= 3
            or any(
                type(s) is not int or s not in (200, 201, 202) for s in self.statuses
            )
            or len(set(self.statuses)) != len(self.statuses)
        ):
            raise ValueError("Select a bounded fixed HTTP JSON operation")


def validate_http_control_config(value):
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema",
            "origin",
            "address",
            "allow_plaintext",
            "headers",
            "enabled_operations",
        }
        or value["schema"] != "airalogy.http-control-config.v1"
        or not isinstance(value["enabled_operations"], list)
        or not 1 <= len(value["enabled_operations"]) <= 32
        or any(
            not isinstance(k, str) or not _KEY.fullmatch(k)
            for k in value["enabled_operations"]
        )
        or len(set(value["enabled_operations"])) != len(value["enabled_operations"])
    ):
        raise ValueError(
            "Select explicit operations in a separate private control configuration"
        )
    copied = validate_http_read_config(
        {
            k: v
            for k, v in {**value, "schema": "airalogy.http-read-config.v1"}.items()
            if k != "enabled_operations"
        }
    )
    return {
        **copied,
        "schema": value["schema"],
        "enabled_operations": list(value["enabled_operations"]),
    }


def read_http_control_config(path: Path):
    selected = Path(path)
    if not selected.is_absolute():
        raise ValueError("Select an absolute private HTTP control configuration")
    _private_root(selected.parent)
    return validate_http_control_config(read_private_json(selected, strict=True))


def _body(value, contract):
    if not isinstance(value, dict) or set(value) != set(contract.body_fields):
        raise ValueError("Wrong operation fields")
    # Check structure before encoding, including cycles, non-JSON values and huge
    # collections. This is transport validation, not the vendor parameter schema.
    pending, visited = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if depth > 16 or visited > 4096:
            raise ValueError("Request structure exceeds limits")
        if isinstance(item, (dict, list)):
            if len(item) > 1024:
                raise ValueError("Request collection exceeds limits")
            if isinstance(item, dict):
                if any(type(k) is not str for k in item):
                    raise ValueError("Request keys must be strings")
                pending.extend((k, depth + 1) for k in item)
            pending.extend(
                (v, depth + 1)
                for v in (item.values() if isinstance(item, dict) else item)
            )
        elif type(item) is str:
            if (
                len(item) > 65536
                or any(
                    ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF
                    for c in item
                )
                or _CREDENTIAL.search(item)
            ):
                raise ValueError("Invalid request string")
        elif item is not None and (
            type(item) not in (int, float, bool)
            or (type(item) is float and not math.isfinite(item))
        ):
            raise ValueError("Invalid request value")
    raw = canonical(value)
    if len(raw) > contract.max_request_bytes:
        raise ValueError("Request bytes exceed limits")
    return raw


class HttpControlClient:
    def __init__(self, config: dict, operations: dict[str, HttpControlOperation]):
        settings = validate_http_control_config(config)
        if (
            not isinstance(operations, dict)
            or not 1 <= len(operations) <= 32
            or any(
                not isinstance(k, str)
                or not _KEY.fullmatch(k)
                or type(v) is not HttpControlOperation
                for k, v in operations.items()
            )
            or not set(settings["enabled_operations"]) <= set(operations)
        ):
            raise ValueError("Select fixed code-reviewed control operations")
        self._operations = {k: operations[k] for k in settings["enabled_operations"]}
        self._transport = HttpReadClient(
            {
                k: v
                for k, v in {
                    **settings,
                    "schema": "airalogy.http-read-config.v1",
                }.items()
                if k != "enabled_operations"
            },
            {
                k: HttpReadOperation(v.path, v.query_fields, v.max_response_bytes)
                for k, v in self._operations.items()
            },
        )

    @classmethod
    def from_file(cls, path: Path, operations: dict[str, HttpControlOperation]):
        return cls(read_http_control_config(path), operations)

    def call(
        self,
        operation: str,
        body: dict | None = None,
        *,
        query: dict[str, str] | None = None,
        timeout_seconds: float = 5,
        stop_event: threading.Event | None = None,
    ) -> HttpReadResult:
        contract = (
            self._operations.get(operation) if isinstance(operation, str) else None
        )
        query = {} if query is None else query
        try:
            if (
                contract is None
                or not isinstance(query, dict)
                or set(query) != set(contract.query_fields)
                or any(
                    not isinstance(v, str)
                    or len(v) > 1024
                    or len(v.encode()) > 1024
                    or re.search(r"[\x00-\x1f\x7f]", v)
                    or _CREDENTIAL.search(v)
                    for v in query.values()
                )
                or type(timeout_seconds) not in (int, float)
                or not math.isfinite(timeout_seconds)
                or not 0.1 <= timeout_seconds <= 30
                or (
                    stop_event is not None
                    and not isinstance(stop_event, threading.Event)
                )
            ):
                raise ValueError("Invalid operation")
            if contract.method == "GET":
                if body is not None:
                    raise ValueError("GET cannot carry a body")
                raw = None
            else:
                raw = _body(body, contract)
        except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError):
            raise HttpControlError("invalid_operation") from None
        return self._transport._exchange(
            contract,
            query,
            timeout_seconds=timeout_seconds,
            stop_event=stop_event,
            method=contract.method,
            body=raw,
            statuses=contract.statuses,
            error=HttpControlError,
        )
