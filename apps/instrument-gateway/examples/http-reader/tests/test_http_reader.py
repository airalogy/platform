"""Fixed package tests: no network. Actual loopback/installed tests live in SDK CI."""

import copy
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from http_reader import ReferenceHttpReader


class HttpReaderContractTests(unittest.TestCase):
    def setUp(self):
        self.expected = {
            "sample_id": "sample-A",
            "value": 1.25,
            "unit": "synthetic_unit",
            "simulation_only": True,
        }
        self.client = Mock()
        self.client.get.return_value = SimpleNamespace(data=self.expected)
        self.adapter = ReferenceHttpReader(self.client)
        self.job = SimpleNamespace(
            command_key="reader.result.read",
            command_version="1.0.0",
            arguments={"sample_id": "sample-A"},
        )

    def test_returns_received_data_not_a_locally_invented_measurement(self):
        stopped = threading.Event()
        self.assertEqual(self.adapter.execute(self.job, stopped), self.expected)
        self.client.get.assert_called_once_with(
            "result", {"sample_id": "sample-A"}, stop_event=stopped, timeout_seconds=3
        )
        self.client.get.return_value.data = {**self.expected, "value": 4.75}
        self.assertEqual(self.adapter.execute(self.job, stopped)["value"], 4.75)

    def test_rejects_unknown_commands_parameters_and_extra_fields_before_io(self):
        for changes in [
            {"command_key": "reader.start"},
            {"command_version": "2"},
            {"arguments": {"sample_id": "other"}},
            {"arguments": {"sample_id": "sample-A", "url": "https://other.invalid"}},
        ]:
            job = SimpleNamespace(**{**vars(self.job), **changes})
            with self.assertRaises(ValueError):
                self.adapter.execute(job, threading.Event())
        self.client.get.assert_not_called()

    def test_rejects_wrong_sample_units_types_and_fabricated_completion(self):
        for changes in [
            {"sample_id": "sample-B"},
            {"value": True},
            {"value": float("nan")},
            {"value": -1},
            {"unit": "wrong"},
            {"simulation_only": False},
            {"download_url": "https://never-contact.invalid"},
        ]:
            self.client.get.return_value.data = {**self.expected, **changes}
            with self.assertRaises(ValueError):
                self.adapter.execute(self.job, threading.Event())

    def test_identity_is_observed_and_does_not_accept_a_partial_target(self):
        fields = (
            "identity_reference",
            "firmware",
            "application",
            "application_version",
            "driver_version",
            "os_version",
        )
        target = dict.fromkeys(fields, "synthetic-only")
        self.client.get.return_value.data = {"simulation_only": True, "target": target}
        self.assertEqual(self.adapter.identity(), target)
        self.client.get.assert_called_once_with("identity", timeout_seconds=3)
        invalid = copy.deepcopy(target)
        invalid.pop("firmware")
        self.client.get.return_value.data = {"simulation_only": True, "target": invalid}
        with self.assertRaises(ValueError):
            self.adapter.identity()


if __name__ == "__main__":
    unittest.main()
