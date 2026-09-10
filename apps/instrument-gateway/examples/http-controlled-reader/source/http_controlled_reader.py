"""Owned loopback controlled service ONLY. Not a vendor driver or safety system."""

import ipaddress
import math
import time
from uuid import UUID

from airalogy_instrument_gateway import InstrumentAdapter
from airalogy_instrument_gateway.http_control import (
    HttpControlClient,
    HttpControlOperation,
    read_http_control_config,
)

OPERATIONS = {
    "identity": HttpControlOperation("GET", "/v1/identity", max_response_bytes=4096),
    "state": HttpControlOperation("GET", "/v1/state", max_response_bytes=4096),
    "configure": HttpControlOperation(
        "PUT",
        "/v1/parameters",
        ("operation_id", "sample_count"),
        max_response_bytes=4096,
    ),
    "start": HttpControlOperation(
        "POST", "/v1/start", ("operation_id",), max_response_bytes=4096, statuses=(202,)
    ),
    "result": HttpControlOperation(
        "GET", "/v1/result", query_fields=("operation_id",), max_response_bytes=4096
    ),
    "stop": HttpControlOperation(
        "POST", "/v1/stop", ("operation_id",), max_response_bytes=4096
    ),
}
TARGET_FIELDS = {
    "identity_reference",
    "firmware",
    "application",
    "application_version",
    "driver_version",
    "os_version",
}


def operation_id(job):
    value = str(job.job_id)
    if str(UUID(value)) != value:
        raise ValueError("Expected the exact job UUID")
    return value


class ControlledHttpReader(InstrumentAdapter):
    def __init__(self, client):
        self.client = client

    def supports(self, job):
        return (job.command_key, job.command_version) == ("reader.measure", "1.0.0")

    def identity(self):
        value = self.client.call("identity", timeout_seconds=3).data
        target = value.get("target")
        if (
            set(value) != {"target", "simulation_only"}
            or value["simulation_only"] is not True
            or not isinstance(target, dict)
            or set(target) != TARGET_FIELDS
            or any(
                type(v) is not str or not v.strip() or len(v) > 255
                for v in target.values()
            )
        ):
            raise ValueError("Expected the independently selected synthetic identity")
        return target

    def _state(self, stop_event=None, *, timeout_seconds=3):
        value = self.client.call(
            "state", stop_event=stop_event, timeout_seconds=timeout_seconds
        ).data
        if (
            set(value)
            != {
                "state",
                "operation_id",
                "sample_count",
                "ready",
                "owner",
                "operator_confirmed",
                "simulation_only",
            }
            or value["simulation_only"] is not True
            or value["state"]
            not in ("idle", "configured", "running", "complete", "stopped")
            or type(value["ready"]) is not bool
            or type(value["operator_confirmed"]) is not bool
            or value["owner"] not in ("gateway", "human")
        ):
            raise ValueError("Unknown synthetic state")
        if value["state"] == "idle":
            if value["operation_id"] is not None or value["sample_count"] is not None:
                raise ValueError("Idle state carries an unresolved operation")
        elif (
            type(value["operation_id"]) is not str
            or str(UUID(value["operation_id"])) != value["operation_id"]
            or type(value["sample_count"]) is not int
            or not 1 <= value["sample_count"] <= 96
        ):
            raise ValueError("Uncorrelated synthetic state")
        return value

    @staticmethod
    def _conditions(state):
        if (
            state["owner"] != "gateway"
            or state["ready"] is not True
            or state["operator_confirmed"] is not True
        ):
            raise RuntimeError("Ownership or local conditions changed")

    @staticmethod
    def _receipt(result, identifier):
        if (
            result
            != {"accepted": True, "operation_id": identifier, "simulation_only": True}
            or type(result.get("accepted")) is not bool
            or type(result.get("simulation_only")) is not bool
        ):
            raise ValueError("Unconfirmed synthetic command receipt")

    def confirm(self, job):
        state = self._state()
        return (
            "Owned service operator confirmation"
            if state["operator_confirmed"] is True
            else None
        )

    def preflight(self, job):
        state = self._state()
        return {
            "interlocks": {
                "reader.ready": state["ready"]
                and state["owner"] == "gateway"
                and state["state"] == "idle"
            },
            "operator_present": state["operator_confirmed"],
            "emergency_stop_available": False,
            "reference": "Fresh owned-service simulation state, not physical safety evidence",
        }

    def execute(self, job, stop_event):
        if (
            not self.supports(job)
            or not isinstance(job.arguments, dict)
            or set(job.arguments) != {"sample_count"}
        ):
            raise ValueError("Unknown command or arguments")
        identifier, count = operation_id(job), job.arguments["sample_count"]
        if type(count) is not int or not 1 <= count <= 96:
            raise ValueError("Select integer sample_count 1..96")
        state = self._state(stop_event)
        self._conditions(state)
        if state["state"] != "idle":
            raise RuntimeError("Existing operation must be reconciled")
        self._receipt(
            self.client.call(
                "configure",
                {"operation_id": identifier, "sample_count": count},
                stop_event=stop_event,
            ).data,
            identifier,
        )
        state = self._state(stop_event)
        self._conditions(state)
        if (
            state["state"] != "configured"
            or state["operation_id"] != identifier
            or state["sample_count"] != count
        ):
            raise RuntimeError("Parameter readback changed; do not start")
        # A 202 response acknowledges this request only. Never retry a start or
        # treat acceptance, a closed socket or a process exit as completion.
        self._receipt(
            self.client.call(
                "start", {"operation_id": identifier}, stop_event=stop_event
            ).data,
            identifier,
        )
        deadline = time.monotonic() + 5

        def remaining():
            seconds = deadline - time.monotonic()
            if seconds < 0.1 or stop_event.is_set():
                raise RuntimeError(
                    "Completion deadline or cancellation; reconcile without restart"
                )
            return min(3, seconds)

        while time.monotonic() < deadline:
            state = self._state(stop_event, timeout_seconds=remaining())
            self._conditions(state)
            if state["operation_id"] != identifier or state["sample_count"] != count:
                raise RuntimeError("Operation or parameters changed")
            if state["state"] == "complete":
                value = self.client.call(
                    "result",
                    query={"operation_id": identifier},
                    stop_event=stop_event,
                    timeout_seconds=remaining(),
                ).data
                if (
                    set(value)
                    != {
                        "operation_id",
                        "sample_count",
                        "value",
                        "unit",
                        "simulation_only",
                    }
                    or value["operation_id"] != identifier
                    or type(value["sample_count"]) is not int
                    or value["sample_count"] != count
                    or type(value["value"]) not in (int, float)
                    or not math.isfinite(value["value"])
                    or value["unit"] != "synthetic_unit"
                    or value["simulation_only"] is not True
                ):
                    raise ValueError("Uncorrelated result or wrong units")
                final = self._state(stop_event, timeout_seconds=remaining())
                self._conditions(final)
                if (
                    final["state"] != "complete"
                    or final["operation_id"] != identifier
                    or final["sample_count"] != count
                ):
                    raise RuntimeError("Completion changed during readback")
                remaining()
                return value
            if state["state"] != "running":
                raise RuntimeError("Unconfirmed completion")
            stop_event.wait(0.02)
        raise RuntimeError("Completion deadline exceeded; reconcile without restart")

    def safe_stop(self, job, reason):
        identifier = operation_id(job)
        state = self._state()
        if state["state"] == "idle":
            return "Observed idle owned simulation"
        if state["operation_id"] != identifier:
            raise RuntimeError("Cannot stop a different operation")
        if state["state"] != "stopped":
            self._receipt(
                self.client.call(
                    "stop", {"operation_id": identifier}, timeout_seconds=3
                ).data,
                identifier,
            )
        state = self._state()
        if state["state"] != "stopped" or state["operation_id"] != identifier:
            raise RuntimeError("Stop remains uncertain")
        return "Observed stopped owned simulation; not physical safe-stop evidence"


def create_adapter(config_path):
    if config_path is None:
        raise ValueError("Select the private owned-service control configuration")
    value = read_http_control_config(config_path)
    if not ipaddress.ip_address(value["address"]).is_loopback or set(
        value["enabled_operations"]
    ) != set(OPERATIONS):
        raise ValueError("The reference requires loopback and its exact operations")
    return ControlledHttpReader(HttpControlClient(value, OPERATIONS))
