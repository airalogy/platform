"""Bounded, data-only GUI rehearsal contract. No OS, network or code execution.

This is the authored source; scripts/sync-instrument-contract.mjs copies it into
the API build context. Rehearsal evidence NEVER grants hardware authority.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

SCHEMA = "airalogy.gui-rehearsal.v1"
MAX_BYTES = 262_144
KEY = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{0,95}$")


def canonical(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (ValueError, TypeError, RecursionError) as error:
        raise ValueError("Expected finite, bounded JSON") from error
    if len(encoded.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Rehearsal exceeds the 256 KiB limit")
    return encoded


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _object(value: Any, required: set[str], optional: set[str] | None = None) -> dict:
    if not isinstance(value, dict) or not required <= value.keys():
        raise ValueError(f"Required object fields: {', '.join(sorted(required))}")
    if value.keys() - required - (optional or set()):
        raise ValueError("Unknown fields are not allowed")
    return value


def _text(value: Any, *, limit: int = 255, key: bool = False) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("Expected nonempty bounded text")
    if key and not KEY.fullmatch(value):
        raise ValueError("Invalid identifier")
    return value


def _list(value: Any, limit: int, minimum: int = 1) -> list:
    if not isinstance(value, list) or not minimum <= len(value) <= limit:
        raise ValueError(f"Expected {minimum} to {limit} items")
    return value


def _scalar(value: Any) -> None:
    if value is not None and type(value) not in {str, int, float, bool}:
        raise ValueError("Only scalar values are supported")
    if isinstance(value, str) and len(value) > 4096:
        raise ValueError("Value is too long")
    canonical(value)


def validate_package(value: Any) -> dict:
    canonical(value)
    package = _object(
        value,
        {"schema", "id", "version", "target", "commands", "source", "limitations"},
    )
    if package["schema"] != SCHEMA:
        raise ValueError("Only data-only GUI rehearsal packages are supported")
    _text(package["id"], key=True)
    _text(package["version"], key=True)
    target = _object(package["target"], {"application", "version", "os", "locale"})
    for item in target.values():
        _text(item)
    source = _object(package["source"], {"kind", "reference"})
    if source["kind"] not in {"manual", "aira", "demonstration"}:
        raise ValueError("Invalid draft source")
    _text(source["reference"], limit=2000)
    for item in _list(package["limitations"], 20):
        _text(item, limit=2000)
    identities = set()
    for command in _list(package["commands"], 10):
        _object(command, {"key", "version", "name", "steps"})
        _text(command["key"], key=True)
        _text(command["version"], key=True)
        _text(command["name"])
        identity = (command["key"], command["version"])
        if identity in identities:
            raise ValueError("Duplicate command version")
        identities.add(identity)
        outputs = set()
        previous_state = None
        for step in _list(command["steps"], 40):
            _object(
                step,
                {"operation", "control_id", "before", "after"},
                {"value", "output_key"},
            )
            if step["operation"] not in {"observe", "read", "invoke", "set_value"}:
                raise ValueError("Operation is not in the rehearsal allowlist")
            _text(step["control_id"])
            _text(step["before"])
            _text(step["after"])
            if previous_state is not None and step["before"] != previous_state:
                raise ValueError("Steps must form a continuous bounded sequence")
            previous_state = step["after"]
            if (
                step["operation"] in {"observe", "read"}
                and step["before"] != step["after"]
            ):
                raise ValueError("Observation cannot change the application state")
            if step["operation"] == "set_value":
                if "value" not in step:
                    raise ValueError("set_value requires a literal value")
                _scalar(step["value"])
            elif "value" in step:
                raise ValueError("Only set_value accepts a value")
            if step["operation"] == "read":
                _text(step.get("output_key"), key=True)
                if step["output_key"] in outputs:
                    raise ValueError("Duplicate output key")
                outputs.add(step["output_key"])
            elif "output_key" in step:
                raise ValueError("Only read produces an output")
    return package


def _snapshot(
    value: Any, target: dict, window: str, state: str, control_id: str
) -> dict:
    _object(
        value,
        {
            "target",
            "window_id",
            "session",
            "control_owner",
            "blocking_dialog",
            "state",
            "controls",
        },
    )
    if value["target"] != target or value["window_id"] != window:
        raise ValueError("Target application, version or window changed")
    if (
        value["session"] != "interactive"
        or value["control_owner"] != "gateway"
        or value["blocking_dialog"] is not False
    ):
        raise ValueError("Locked, disconnected, taken-over or blocked session")
    if value["state"] != state:
        raise ValueError("Application state does not match the reviewed step")
    matches = []
    for control in _list(value["controls"], 200):
        _object(control, {"id", "enabled", "value"})
        _text(control["id"])
        if type(control["enabled"]) is not bool:
            raise ValueError("Control enabled must be a boolean")
        _scalar(control["value"])
        if control["id"] == control_id:
            matches.append(control)
    if len(matches) != 1:
        raise ValueError("Control must resolve to exactly one element")
    return matches[0]


def rehearse(package: dict, scenarios: Any) -> dict:
    """Interpret supplied observations only; never import drivers or perform actions."""
    validate_package(package)
    canonical(scenarios)
    _list(scenarios, 20)
    catalog = {(c["key"], c["version"]): c for c in package["commands"]}
    cases = []
    covered = set()
    names = set()
    for case in scenarios:
        _object(
            case,
            {
                "name",
                "command_key",
                "command_version",
                "window_id",
                "observations",
                "expected_output",
            },
        )
        _text(case["name"])
        if case["name"] in names:
            raise ValueError("Scenario names must be unique")
        names.add(case["name"])
        _text(case["window_id"])
        _text(case["command_key"], key=True)
        _text(case["command_version"], key=True)
        identity = (case["command_key"], case["command_version"])
        if identity not in catalog:
            raise ValueError("Scenario command is not declared")
        command = catalog[identity]
        observations = _list(case["observations"], 80)
        if len(observations) != 2 * len(command["steps"]):
            raise ValueError("Each step requires before and after observations")
        if not isinstance(case["expected_output"], dict):
            raise ValueError("Expected output must be an object")  # noqa: TRY004 - uniform input-validation error
        output = {}
        trace = []
        failure = None
        for index, step in enumerate(command["steps"]):
            try:
                before = _snapshot(
                    observations[2 * index],
                    package["target"],
                    case["window_id"],
                    step["before"],
                    step["control_id"],
                )
                if (
                    step["operation"] in {"invoke", "set_value"}
                    and not before["enabled"]
                ):
                    raise ValueError("Target control is disabled")
                after = _snapshot(
                    observations[2 * index + 1],
                    package["target"],
                    case["window_id"],
                    step["after"],
                    step["control_id"],
                )
                if step["operation"] == "set_value" and canonical(
                    after["value"]
                ) != canonical(step["value"]):
                    raise ValueError(
                        "Parameter readback differs from the requested value"
                    )
                if step["operation"] == "read":
                    output[step["output_key"]] = after["value"]
                trace.append(
                    {
                        "step": index + 1,
                        "operation": step["operation"],
                        "status": "observations_matched",
                    }
                )
            except ValueError as error:
                failure = {"step": index + 1, "reason": str(error)}
                break
        if failure is None and canonical(output) != canonical(case["expected_output"]):
            failure = {
                "step": len(command["steps"]),
                "reason": "Output differs from expected evidence",
            }
        if failure is None:
            covered.add(identity)
        cases.append(
            {
                "name": case["name"],
                "passed": failure is None,
                "failure": failure,
                "trace": trace,
                "output": output,
            }
        )
    missing = sorted(set(catalog) - covered)
    return {
        "schema": "airalogy.gui-rehearsal-report.v1",
        "simulation_only": True,
        "hardware_authorized": False,
        "package_digest": digest(package),
        "scenarios_digest": digest(scenarios),
        "passed": all(c["passed"] for c in cases) and not missing,
        "uncovered_commands": [f"{key}@{version}" for key, version in missing],
        "cases": cases,
    }


def example_bundle() -> dict:
    """Synthetic control software; no claim about a vendor's actual application."""
    target = {
        "application": "Airalogy Simulated Reader",
        "version": "1.0",
        "os": "simulation",
        "locale": "en-US",
    }
    package = {
        "schema": SCHEMA,
        "id": "example.reader",
        "version": "v1",
        "target": target,
        "source": {"kind": "manual", "reference": "Synthetic example"},
        "limitations": [
            "Simulation only; no physical device or OS automation backend."
        ],
        "commands": [
            {
                "key": "read.result",
                "version": "v1",
                "name": "Read simulated result",
                "steps": [
                    {
                        "operation": "read",
                        "control_id": "result.value",
                        "before": "completed",
                        "after": "completed",
                        "output_key": "value",
                    }
                ],
            }
        ],
    }
    snapshot = {
        "target": target,
        "window_id": "simulated-reader",
        "session": "interactive",
        "control_owner": "gateway",
        "blocking_dialog": False,
        "state": "completed",
        "controls": [{"id": "result.value", "enabled": True, "value": 0.42}],
    }
    scenarios = [
        {
            "name": "Synthetic result",
            "command_key": "read.result",
            "command_version": "v1",
            "window_id": "simulated-reader",
            "observations": [copy.deepcopy(snapshot), copy.deepcopy(snapshot)],
            "expected_output": {"value": 0.42},
        }
    ]
    return {"package": package, "scenarios": scenarios}
