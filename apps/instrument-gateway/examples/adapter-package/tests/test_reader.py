import threading
import unittest
from types import SimpleNamespace

from airalogy_instrument_gateway.adapters import load_adapter


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.adapter = load_adapter("synthetic.reader", None)
        self.job = SimpleNamespace(command_key="reader.measure", command_version="1.0.0", arguments={"sample_count": 2})

    def test_independent_expected_measurement(self):
        self.assertEqual(self.adapter.execute(self.job, threading.Event()), {"value": 0.84, "unit": "synthetic_unit", "simulation_only": True})

    def test_rejects_out_of_range_and_boolean(self):
        for value in [0, 97, True, 1.5]:
            self.job.arguments["sample_count"] = value
            with self.assertRaises(ValueError):
                self.adapter.execute(self.job, threading.Event())

    def test_unknown_command_and_stop(self):
        self.job.command_version = "other"
        self.assertFalse(self.adapter.supports(self.job))
        with self.assertRaises(ValueError):
            self.adapter.execute(self.job, threading.Event())
        self.job.command_version = "1.0.0"
        stopped = threading.Event()
        stopped.set()
        with self.assertRaises(RuntimeError):
            self.adapter.execute(self.job, stopped)
