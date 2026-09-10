"""Owned native read reference. No vendor operations or scientific inference."""

from uuid import UUID

from airalogy_instrument_gateway import InstrumentAdapter
from airalogy_instrument_gateway.interface_process import NativeReadProcessClient


class OwnedNativeReader(InstrumentAdapter):
    def __init__(self, client):
        self.client = client

    def supports(self, job):
        return (job.command_key, job.command_version) == ("native.status.read", "1.0.0")

    def _owned(self, data):
        if (
            data.get("source_kind") != "native_macos"
            or data.get("owned_simulator") is not True
            or type(data.get("actions_executed")) is not int
            or data["actions_executed"] != 0
        ):
            raise ValueError("The reference requires the exact owned native simulator")
        return data

    def _probe(self, stop_event=None):
        data = self._owned(self.client.call("probe", stop_event=stop_event)["data"])
        if type(data.get("read_access")) is not bool:
            raise ValueError("Expected existing native read permission diagnostics")
        return data

    def identity(self):
        return self._probe()["target"]

    def confirm(self, job):
        return None

    def preflight(self, job):
        return {
            "interlocks": {"native.read_access": self._probe()["read_access"]},
            "operator_present": False,
            "emergency_stop_available": False,
            "reference": "Existing Accessibility and graphical session, not physical readiness",
        }

    def execute(self, job, stop_event):
        if (
            not self.supports(job)
            or job.arguments != {}
            or str(UUID(job.job_id)) != job.job_id
        ):
            raise ValueError("Select the exact fixed native read command and Job UUID")
        # Refuse another app before any UI capture, including direct SDK use
        # that did not go through the Gateway identity/preflight sequence.
        if not self._probe(stop_event)["read_access"]:
            raise ValueError("Existing native read permission and session required")
        response = self.client.call(
            "execute",
            job_id=job.job_id,
            timeout_seconds=min(20, job.timeout_seconds),
            stop_event=stop_event,
        )
        data = self._owned(response["data"])
        values = data.get("values")
        if (
            response["job_id"] != job.job_id
            or not isinstance(values, dict)
            or set(values) != {"reader.status", "reader.result"}
            or any(
                not isinstance(value, str) or len(value.encode()) > 4096
                for value in values.values()
            )
        ):
            raise ValueError("Expected exact selected native text readbacks")
        return {
            "operation_id": job.job_id,
            "definition_digest": response["definition_digest"],
            "values": values,
            "observation_only": True,
            "simulation_only": True,
        }

    def safe_stop(self, job, reason):
        # Reading stops local helper work only. Never certify the selected
        # application's or an attached instrument's physical state.
        raise RuntimeError("Reconcile the native read; physical stop is not qualified")


def create_adapter(config_path):
    if config_path is None:
        raise ValueError("Select an independently prepared private native read config")
    return OwnedNativeReader(NativeReadProcessClient.from_file(config_path))
