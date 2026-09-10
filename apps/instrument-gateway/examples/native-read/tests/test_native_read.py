import unittest
from threading import Event
from types import SimpleNamespace

from native_read import OwnedNativeReader


class FixedClient:
    def __init__(self):
        self.calls = []
        self.values = {"reader.status": "Independent state", "reader.result": "19.75"}
        self.owned = True

    def call(self, operation, **kwargs):
        self.calls.append((operation, kwargs))
        return {
            "job_id": kwargs.get("job_id"),
            "definition_digest": "a" * 64,
            "data": {
                "source_kind": "native_macos",
                "owned_simulator": self.owned,
                "actions_executed": 0,
                "read_access": True,
                "target": {"independent": "identity"},
                "values": self.values,
            },
        }


class NativeReadTests(unittest.TestCase):
    def test_readback_without_invented_science_actions_or_physical_stop(self):
        client = FixedClient()
        adapter = OwnedNativeReader(client)
        job = SimpleNamespace(
            command_key="native.status.read",
            command_version="1.0.0",
            arguments={},
            job_id="11111111-1111-1111-1111-111111111111",
            timeout_seconds=30,
        )
        self.assertEqual(adapter.identity(), {"independent": "identity"})
        self.assertTrue(adapter.preflight(job)["interlocks"]["native.read_access"])
        result = adapter.execute(job, Event())
        self.assertEqual(result["values"], client.values)
        self.assertTrue(result["observation_only"])
        self.assertTrue(result["simulation_only"])
        self.assertIsNone(adapter.confirm(job))
        with self.assertRaises(RuntimeError):
            adapter.safe_stop(job, "cancelled")
        client.owned = False
        reads_before = sum(operation == "execute" for operation, _ in client.calls)
        with self.assertRaises(ValueError):
            adapter.execute(job, Event())
        self.assertEqual(
            sum(operation == "execute" for operation, _ in client.calls), reads_before
        )
        client.owned = True
        for value in (
            {"extra": "private"},
            {"reader.status": True, "reader.result": "1"},
        ):
            client.values = value
            with self.assertRaises(ValueError):
                adapter.execute(job, Event())
        job.arguments = {"click": "not allowed"}
        with self.assertRaises(ValueError):
            adapter.execute(job, Event())


if __name__ == "__main__":
    unittest.main()
