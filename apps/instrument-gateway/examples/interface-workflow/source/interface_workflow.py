"""Owned browser workflow reference; no vendor GUI or physical safety proof."""

import math
from uuid import UUID

from airalogy_instrument_gateway import InstrumentAdapter
from airalogy_instrument_gateway.interface_process import InterfaceProcessClient


class OwnedInterfaceWorkflow(InstrumentAdapter):
    def __init__(self, client):
        self.client = client

    def supports(self, job):
        return (job.command_key, job.command_version) == (
            "interface.workflow.run",
            "1.0.0",
        )

    def _probe(self):
        value = self.client.call("probe")["data"]
        if (
            value.get("source_kind") != "file"
            or type(value.get("initial_matches")) is not bool
        ):
            raise ValueError("The reference supports owned simulation HTML only")
        return value

    def identity(self):
        return self._probe()["target"]

    def confirm(self, job):
        # No invented operator-presence or per-job confirmation attestation.
        return None

    def preflight(self, job):
        return {
            "interlocks": {"interface.initial": self._probe()["initial_matches"]},
            "operator_present": False,
            "emergency_stop_available": False,
            "reference": "Fresh owned HTML initial readbacks, not physical interlocks",
        }

    def execute(self, job, stop_event):
        if (
            not self.supports(job)
            or job.arguments != {}
            or str(UUID(job.job_id)) != job.job_id
        ):
            raise ValueError("Select the exact fixed workflow command and Job UUID")
        response = self.client.call(
            "execute",
            job_id=job.job_id,
            timeout_seconds=min(20, job.timeout_seconds),
            stop_event=stop_event,
        )
        data = response["data"]
        if (
            response["job_id"] != job.job_id
            or data.get("source_kind") != "file"
            or set(data.get("values", {})) != {"result.value"}
        ):
            raise ValueError("Uncorrelated or unsupported workflow result")
        result = float(data["values"]["result.value"])
        if not math.isfinite(result):
            raise ValueError("Expected a finite actual readback")
        return {
            "operation_id": job.job_id,
            "workflow_digest": response["workflow_digest"],
            "value": result,
            "unit": "synthetic_unit",
            "simulation_only": True,
        }

    def safe_stop(self, job, reason):
        # Worker termination stops local computation only. Preserve Gateway's
        # stop/reconciliation lock instead of pretending to certify hardware.
        raise RuntimeError(
            "No physical stop is qualified; reconcile the original interface operation"
        )


def create_adapter(config_path):
    if config_path is None:
        raise ValueError(
            "Select an independently prepared private worker configuration"
        )
    return OwnedInterfaceWorkflow(InterfaceProcessClient.from_file(config_path))
