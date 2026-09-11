import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from native_read import OwnedNativeReader, create_adapter

from airalogy_instrument_gateway.interface_process import (
    InterfaceProcessError,
    NativeReadProcessClient,
)


def selected_job():
    return SimpleNamespace(
        command_key="native.status.read",
        command_version="1.0.0",
        arguments={},
        job_id="11111111-1111-1111-1111-111111111111",
        timeout_seconds=30,
    )


class FixedClient:
    def __init__(self):
        self.calls = []
        self.values = {"reader.status": "Independent state", "reader.result": "19.75"}
        self.owned = True
        self.read_access = True
        self.actions = 0
        self.result_job = None
        self.failure = False

    def call(self, operation, **kwargs):
        self.calls.append((operation, kwargs))
        if self.failure or (
            kwargs.get("stop_event") is not None and kwargs["stop_event"].is_set()
        ):
            raise InterfaceProcessError("Independent uncertain native failure")
        return {
            "job_id": self.result_job or kwargs.get("job_id"),
            "definition_digest": "a" * 64,
            "data": {
                "source_kind": "native_macos",
                "owned_simulator": self.owned,
                "actions_executed": self.actions,
                "read_access": self.read_access,
                "target": {"independent": "identity"},
                "values": self.values,
            },
        }


class NativeReadTests(unittest.TestCase):
    def test_readback_without_invented_science_actions_or_physical_stop(self):
        client = FixedClient()
        adapter = OwnedNativeReader(client)
        job = selected_job()
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
            {"reader.status": "Complete", "reader.result": 1},
            {"reader.status": "Complete", "reader.result": "研" * 1366},
        ):
            client.values = value
            with self.assertRaises(ValueError):
                adapter.execute(job, Event())
        job.arguments = {"click": "not allowed"}
        with self.assertRaises(ValueError):
            adapter.execute(job, Event())

    def test_factory_uses_native_read_only_sdk_and_preserves_unavailable_diagnostics(
        self,
    ):
        client = FixedClient()
        path = Path("/synthetic/private/native.json")
        with patch.object(
            NativeReadProcessClient, "from_file", return_value=client
        ) as load:
            adapter = create_adapter(path)
        load.assert_called_once_with(path)
        with self.assertRaises(ValueError):
            create_adapter(None)
        job = selected_job()
        self.assertTrue(adapter.supports(job))
        for key, version in (
            ("interface.workflow.run", "1.0.0"),
            ("native.status.read", "2.0.0"),
        ):
            job.command_key, job.command_version = key, version
            self.assertFalse(adapter.supports(job))
            with self.assertRaises(ValueError):
                adapter.execute(job, Event())
        self.assertEqual(client.calls, [])
        job = selected_job()
        client.read_access = False
        checks = adapter.preflight(job)
        self.assertIs(checks["interlocks"]["native.read_access"], False)
        self.assertIs(checks["operator_present"], False)
        self.assertIs(checks["emergency_stop_available"], False)
        with self.assertRaises(ValueError):
            adapter.execute(job, Event())
        self.assertFalse(any(op == "execute" for op, _ in client.calls))
        client.read_access = True
        for actions in (True, 1, "0"):
            client.actions = actions
            with self.assertRaises(ValueError):
                adapter.execute(job, Event())
        self.assertFalse(any(op == "execute" for op, _ in client.calls))

    def test_text_is_preserved_without_inference_or_retry(self):
        client = FixedClient()
        adapter = OwnedNativeReader(client)
        job = selected_job()
        job.timeout_seconds = 7
        event = Event()
        for values in (
            {"reader.status": "Complete", "reader.result": ""},
            {"reader.status": "未完成", "reader.result": " 6.2?\ncheck sample "},
        ):
            client.values = values
            self.assertEqual(
                adapter.execute(job, event),
                {
                    "operation_id": job.job_id,
                    "definition_digest": "a" * 64,
                    "values": values,
                    "observation_only": True,
                    "simulation_only": True,
                },
            )
            self.assertEqual(
                client.calls[-1],
                (
                    "execute",
                    {
                        "job_id": job.job_id,
                        "timeout_seconds": 7,
                        "stop_event": event,
                    },
                ),
            )
        client.result_job = "22222222-2222-2222-2222-222222222222"
        with self.assertRaises(ValueError):
            adapter.execute(job, event)
        client.result_job = None
        event.set()
        reads_before = sum(op == "execute" for op, _ in client.calls)
        with self.assertRaises(InterfaceProcessError):
            adapter.execute(job, event)
        self.assertEqual(sum(op == "execute" for op, _ in client.calls), reads_before)
        event.clear()
        original_call = client.call

        def uncertain_execute(operation, **kwargs):
            client.failure = operation == "execute"
            return original_call(operation, **kwargs)

        client.call = uncertain_execute
        with self.assertRaises(InterfaceProcessError):
            adapter.execute(job, event)
        self.assertEqual(
            sum(op == "execute" for op, _ in client.calls), reads_before + 1
        )


if __name__ == "__main__":
    unittest.main()
