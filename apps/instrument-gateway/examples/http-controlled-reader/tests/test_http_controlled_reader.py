"""Fixed independent controller responses; never generated with adapter source."""

import copy
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from http_controlled_reader import ControlledHttpReader, create_adapter


class FakeClient:
    def __init__(self):
        self.state = {
            "state": "idle",
            "operation_id": None,
            "sample_count": None,
            "ready": True,
            "owner": "gateway",
            "operator_confirmed": True,
            "simulation_only": True,
        }
        self.calls = []
        self.fault = None
        self.value = 19.75

    def call(self, operation, body=None, *, query=None, stop_event=None, **kwargs):
        if stop_event is not None and stop_event.is_set():
            raise RuntimeError("Owned cancellation")
        self.calls.append(operation)
        if operation == "configure":
            self.state.update(body, state="configured")
            value = {
                "accepted": True,
                "operation_id": body["operation_id"],
                "simulation_only": True,
            }
        elif operation in ("start", "stop"):
            self.state["state"] = "complete" if operation == "start" else "stopped"
            value = {
                "accepted": True,
                "operation_id": body["operation_id"],
                "simulation_only": True,
            }
        elif operation == "state":
            value = self.state
        elif operation == "result":
            if query != {"operation_id": self.state["operation_id"]}:
                raise ValueError("Wrong operation query")
            value = {
                "operation_id": self.state["operation_id"],
                "sample_count": self.state["sample_count"],
                "value": self.value,
                "unit": "synthetic_unit",
                "simulation_only": True,
            }
        else:
            value = {
                "target": {
                    k: "owned fixture"
                    for k in (
                        "identity_reference",
                        "firmware",
                        "application",
                        "application_version",
                        "driver_version",
                        "os_version",
                    )
                },
                "simulation_only": True,
            }
        if self.fault:
            self.fault(operation, value)
        return SimpleNamespace(data=copy.deepcopy(value))


class IndependentContractTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.adapter = ControlledHttpReader(self.client)
        self.job = SimpleNamespace(
            job_id=str(uuid4()),
            command_key="reader.measure",
            command_version="1.0.0",
            arguments={"sample_count": 2},
        )
        self.stop = threading.Event()

    def test_original_correlated_result_single_start_and_fresh_conditions(self):
        self.assertTrue(self.adapter.identity())
        self.assertTrue(self.adapter.confirm(self.job))
        self.assertTrue(self.adapter.preflight(self.job)["interlocks"]["reader.ready"])
        result = self.adapter.execute(self.job, self.stop)
        self.assertEqual(result["value"], 19.75)
        self.assertEqual(result["operation_id"], self.job.job_id)
        self.assertEqual(self.client.calls.count("start"), 1)
        with self.assertRaises(RuntimeError):
            self.adapter.execute(self.job, self.stop)
        self.assertEqual(self.client.calls.count("start"), 1)

    def test_parameter_drift_and_false_confirmation_never_start(self):
        def fault(operation, value):
            if operation == "state" and value["state"] == "configured":
                value["sample_count"] = 3

        self.client.fault = fault
        with self.assertRaises(RuntimeError):
            self.adapter.execute(self.job, self.stop)
        self.assertNotIn("start", self.client.calls)
        self.client.state["operator_confirmed"] = False
        self.assertIsNone(self.adapter.confirm(self.job))

    def test_lost_start_receipt_does_not_repeat_start(self):
        def fault(operation, value):
            if operation == "start":
                raise ConnectionError("Owned lost receipt")

        self.client.fault = fault
        with self.assertRaises(ConnectionError):
            self.adapter.execute(self.job, self.stop)
        self.assertEqual(self.client.calls.count("start"), 1)
        self.adapter.safe_stop(self.job, "uncertain start")
        self.adapter.safe_stop(self.job, "recovery")
        self.assertEqual(self.client.calls.count("stop"), 1)

    def test_mismatched_and_unconfirmed_stop_cannot_report_success(self):
        self.client.state.update(
            state="running", operation_id=str(uuid4()), sample_count=2
        )
        with self.assertRaises(RuntimeError):
            self.adapter.safe_stop(self.job, "different operation")
        self.assertNotIn("stop", self.client.calls)
        self.client.state["operation_id"] = self.job.job_id

        def fault(operation, value):
            if operation == "stop":
                self.client.state["state"] = "running"

        self.client.fault = fault
        with self.assertRaises(RuntimeError):
            self.adapter.safe_stop(self.job, "no stop confirmation")

    def test_takeover_after_result_and_wrong_units_are_failures(self):
        for change in ("takeover", "units", "boolean", "sample"):
            self.setUp()

            def fault(operation, value, change=change):
                if operation == "result":
                    if change == "takeover":
                        self.client.state["owner"] = "human"
                    elif change == "units":
                        value["unit"] = "wrong"
                    elif change == "boolean":
                        value["value"] = True
                    else:
                        value["operation_id"] = str(uuid4())

            self.client.fault = fault
            with self.assertRaises((ValueError, RuntimeError)):
                self.adapter.execute(self.job, self.stop)

    def test_cancelled_or_invalid_input_never_writes(self):
        self.stop.set()
        with self.assertRaises(RuntimeError):
            self.adapter.execute(self.job, self.stop)
        self.assertFalse(self.client.calls)
        for value in (True, 0, 97):
            self.job.arguments["sample_count"] = value
            with self.assertRaises(ValueError):
                self.adapter.execute(self.job, self.stop)
        with self.assertRaises(ValueError):
            create_adapter(None)

    def test_result_past_completion_deadline_is_not_accepted(self):
        clock = [0]

        def fault(operation, value):
            if operation == "result":
                clock[0] = 6

        self.client.fault = fault
        with (
            patch(
                "http_controlled_reader.time.monotonic", side_effect=lambda: clock[0]
            ),
            self.assertRaises(RuntimeError),
        ):
            self.adapter.execute(self.job, self.stop)
        self.assertEqual(self.client.calls.count("start"), 1)


if __name__ == "__main__":
    unittest.main()
