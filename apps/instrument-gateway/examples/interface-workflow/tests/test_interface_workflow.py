import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from interface_workflow import OwnedInterfaceWorkflow, create_adapter

from airalogy_instrument_gateway.interface_process import (
    InterfaceProcessClient,
    InterfaceProcessError,
)


def selected_job():
    return SimpleNamespace(
        command_key="interface.workflow.run",
        command_version="1.0.0",
        arguments={},
        job_id="11111111-1111-1111-1111-111111111111",
        timeout_seconds=30,
    )


class FixedWorker:
    def __init__(self):
        self.calls = []
        self.source_kind = "file"
        self.value = "19.75"
        self.initial_matches = True
        self.result_job = None
        self.failure = False

    def call(self, operation, **kwargs):
        self.calls.append((operation, kwargs))
        if self.failure or (
            kwargs.get("stop_event") is not None and kwargs["stop_event"].is_set()
        ):
            raise InterfaceProcessError("Independent uncertain worker failure")
        if operation == "probe":
            return {
                "data": {
                    "source_kind": self.source_kind,
                    "initial_matches": self.initial_matches,
                    "target": {"independent": "target"},
                }
            }
        return {
            "job_id": self.result_job or kwargs["job_id"],
            "workflow_digest": "a" * 64,
            "data": {
                "source_kind": self.source_kind,
                "values": {"result.value": self.value},
            },
        }


class WorkflowTests(unittest.TestCase):
    def test_actual_readback_correlation_and_no_claimed_physical_stop(self):
        client = FixedWorker()
        adapter = OwnedInterfaceWorkflow(client)
        job = selected_job()
        self.assertEqual(adapter.identity(), {"independent": "target"})
        self.assertIsNone(adapter.confirm(job))
        self.assertTrue(adapter.preflight(job)["interlocks"]["interface.initial"])
        result = adapter.execute(job, Event())
        self.assertEqual(result["value"], 19.75)
        self.assertEqual(result["operation_id"], job.job_id)
        self.assertEqual(sum(op == "execute" for op, _ in client.calls), 1)
        with self.assertRaises(RuntimeError):
            adapter.safe_stop(job, "cancelled")
        job.arguments = {"arbitrary_code": "not permitted"}
        with self.assertRaises(ValueError):
            adapter.execute(job, Event())
        job.arguments = {}
        for value in ("nan", "inf", "not-a-result", True, 19.75, None):
            client.value = value
            with self.assertRaises(ValueError):
                adapter.execute(job, Event())
        client.source_kind = "url"
        with self.assertRaises(ValueError):
            adapter.identity()

    def test_factory_keeps_separate_private_sdk_boundary_and_exact_command(self):
        client = FixedWorker()
        path = Path("/synthetic/private/worker.json")
        with patch.object(
            InterfaceProcessClient, "from_file", return_value=client
        ) as load:
            adapter = create_adapter(path)
        load.assert_called_once_with(path)
        with self.assertRaises(ValueError):
            create_adapter(None)
        job = selected_job()
        self.assertTrue(adapter.supports(job))
        job.command_version = "2.0.0"
        self.assertFalse(adapter.supports(job))
        with self.assertRaises(ValueError):
            adapter.execute(job, Event())
        self.assertEqual(client.calls, [])
        job.command_version = "1.0.0"
        job.command_key = "native.status.read"
        self.assertFalse(adapter.supports(job))
        client.initial_matches = False
        checks = adapter.preflight(job)
        self.assertIs(checks["interlocks"]["interface.initial"], False)
        self.assertIs(checks["operator_present"], False)
        self.assertIs(checks["emergency_stop_available"], False)

    def test_independent_readbacks_identity_and_uncertainty_are_not_replaced(self):
        client = FixedWorker()
        adapter = OwnedInterfaceWorkflow(client)
        job = selected_job()
        event = Event()
        job.timeout_seconds = 7
        for text in ("0", "-2.875", "6.02e2"):
            client.value = text
            self.assertEqual(
                adapter.execute(job, event),
                {
                    "operation_id": job.job_id,
                    "workflow_digest": "a" * 64,
                    "value": float(text),
                    "unit": "synthetic_unit",
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
        client.failure = True
        before = len(client.calls)
        with self.assertRaises(InterfaceProcessError):
            adapter.execute(job, event)
        self.assertEqual(len(client.calls), before + 1)
        client.failure = False
        client.result_job = None
        event.set()
        with self.assertRaises(InterfaceProcessError):
            adapter.execute(job, event)


if __name__ == "__main__":
    unittest.main()
