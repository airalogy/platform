"""Stateful, in-memory control reference. Never connects to physical equipment."""

import math
import time

from airalogy_instrument_gateway import InstrumentAdapter


class SyntheticController:
    """Owned simulation transport; values are not physical device observations."""

    def __init__(self):
        self.state = "idle"
        self.owner = "gateway"
        self.operator_confirmed = True
        self.ready = True
        self.count = None
        self.polls = 0

    def identity(self):
        return {
            "identity_reference": "owned-memory-controlled-reader",
            "firmware": "simulation",
            "application": "controlled_reader",
            "application_version": "1.0.0",
            "driver_version": "1.0.0",
            "os_version": "in-memory-simulation",
        }

    def configure(self, count):
        self.count = count

    def parameters(self):
        return {"sample_count": self.count}

    def start(self):
        if self.state != "idle":
            raise RuntimeError("Synthetic controller is already busy")
        self.state = "running"
        self.polls = 0

    def poll(self):
        if self.state == "running":
            self.polls += 1
            if self.polls >= 2:
                self.state = "complete"
        return self.state

    def result(self):
        if self.state != "complete":
            raise RuntimeError("Synthetic measurement is not complete")
        return {
            "sample_count": self.count,
            "value": round(0.42 * self.count, 2),
            "unit": "synthetic_unit",
            "simulation_only": True,
        }

    def stop(self):
        self.state = "stopped"


class ControlledReader(InstrumentAdapter):
    def __init__(self, controller):
        self.controller = controller

    def supports(self, job):
        return (job.command_key, job.command_version) == ("reader.measure", "1.0.0")

    def identity(self):
        return self.controller.identity()

    def confirm(self, job):
        return (
            "Owned simulation operator confirmation"
            if self.controller.operator_confirmed is True
            else None
        )

    def preflight(self, job):
        return {
            "interlocks": {
                "reader.ready": self.controller.ready is True
                and self.controller.owner == "gateway"
                and self.controller.state == "idle"
            },
            "operator_present": self.controller.operator_confirmed is True,
            "emergency_stop_available": False,
            "reference": "Fresh owned simulation observation, not physical interlocks",
        }

    def _check(self, stop_event):
        if stop_event.is_set():
            raise RuntimeError("Controlled simulation cancelled; reconcile stopping")
        if (
            self.controller.owner != "gateway"
            or self.controller.ready is not True
            or self.controller.operator_confirmed is not True
        ):
            raise RuntimeError("Control ownership or local conditions changed")

    def _parameters_match(self, count):
        value = self.controller.parameters()
        return (
            isinstance(value, dict)
            and set(value) == {"sample_count"}
            and type(value["sample_count"]) is int
            and value["sample_count"] == count
        )

    def execute(self, job, stop_event):
        if (
            not self.supports(job)
            or not isinstance(job.arguments, dict)
            or set(job.arguments) != {"sample_count"}
        ):
            raise ValueError("Select the exact controlled simulation command")
        count = job.arguments["sample_count"]
        if type(count) is not int or not 1 <= count <= 96:
            raise ValueError("sample_count must be an integer from 1 to 96")
        self._check(stop_event)
        if self.controller.state != "idle":
            raise RuntimeError("Unknown or busy controller state")
        self.controller.configure(count)
        if not self._parameters_match(count):
            raise RuntimeError("Parameter readback differs; do not start")
        self._check(stop_event)
        if self.controller.state != "idle":
            raise RuntimeError("Controller state changed before start")
        self.controller.start()  # Exactly once; a lost response is never retried.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self._check(stop_event)
            state = self.controller.poll()
            self._check(stop_event)
            if state == "complete":
                value = self.controller.result()
                self._check(stop_event)
                if (
                    not isinstance(value, dict)
                    or set(value)
                    != {"sample_count", "value", "unit", "simulation_only"}
                    or type(value["sample_count"]) is not int
                    or value["sample_count"] != count
                    or not self._parameters_match(count)
                    or type(value["value"]) not in (int, float)
                    or not math.isfinite(value["value"])
                    or value["unit"] != "synthetic_unit"
                    or value["simulation_only"] is not True
                ):
                    raise ValueError(
                        "Completion, sample or units differ from the contract"
                    )
                self._check(stop_event)
                return value
            if state != "running":
                raise RuntimeError("Unexpected controller state; reconcile stopping")
            stop_event.wait(0.01)
        raise RuntimeError("Completion deadline exceeded; do not restart")

    def safe_stop(self, job, reason):
        # Device-specific ONLY for this owned in-memory simulation. No generic
        # shutdown, process termination or physical safety claim is implemented.
        if self.controller.state not in ("idle", "stopped"):
            self.controller.stop()
        if self.controller.state not in ("idle", "stopped"):
            raise RuntimeError("Synthetic stop remains unconfirmed")
        return "Owned simulation reached its declared stopped/idle state"


def create_adapter(config_path):
    if config_path is not None:
        raise ValueError("The reference accepts no production configuration")
    return ControlledReader(SyntheticController())
