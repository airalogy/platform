"""Synthetic reference adapter. No instruments, networking or model calls."""

from airalogy_instrument_gateway.adapters import InstrumentAdapter


class SyntheticReader(InstrumentAdapter):
    def supports(self, job):
        return (job.command_key, job.command_version) == ("reader.measure", "1.0.0")

    def confirm(self, job):
        return None

    def execute(self, job, stop_event):
        if not self.supports(job):
            raise ValueError("Unknown command/version")
        count = job.arguments.get("sample_count")
        if type(count) is not int or not 1 <= count <= 96:
            raise ValueError("sample_count must be an integer from 1 to 96")
        if stop_event.is_set():
            raise RuntimeError("Simulation stopped")
        return {"value": round(0.42 * count, 2), "unit": "synthetic_unit", "simulation_only": True}

    def safe_stop(self, job, reason):
        # No physical process exists in this synthetic implementation.
        return None


def create_adapter(config_path):
    if config_path is not None:
        raise ValueError("Synthetic adapter does not accept device configuration")
    return SyntheticReader()
