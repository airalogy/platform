import unittest
from threading import Event
from types import SimpleNamespace

from interface_workflow import OwnedInterfaceWorkflow


class FixedWorker:
    def __init__(self):
        self.calls = []
        self.source_kind = "file"
        self.value = "19.75"

    def call(self, operation, **kwargs):
        self.calls.append((operation, kwargs))
        if operation == "probe":
            return {
                "data": {
                    "source_kind": self.source_kind,
                    "initial_matches": True,
                    "target": {"independent": "target"},
                }
            }
        return {
            "job_id": kwargs["job_id"],
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
        job = SimpleNamespace(
            command_key="interface.workflow.run",
            command_version="1.0.0",
            arguments={},
            job_id="11111111-1111-1111-1111-111111111111",
            timeout_seconds=30,
        )
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
        for value in ("nan", "inf", "not-a-result"):
            client.value = value
            with self.assertRaises(ValueError):
                adapter.execute(job, Event())
        client.source_kind = "url"
        with self.assertRaises(ValueError):
            adapter.identity()


if __name__ == "__main__":
    unittest.main()
