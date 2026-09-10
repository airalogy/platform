"""Data-only inbox collector, not an adapter for live vendor hardware."""

import platform

from airalogy_instrument_gateway import InstrumentAdapter
from airalogy_instrument_gateway.export_read import ExportReadClient, read_export_config

OUTPUTS = [
    {
        "name": "result.csv",
        "media_type": "text/csv",
        "max_bytes": 1048576,
        "required": True,
    },
    {
        "name": "export.json",
        "media_type": "application/json",
        "max_bytes": 131072,
        "required": True,
    },
]


class ExportInboxReader(InstrumentAdapter):
    def __init__(self, client):
        self.client = client

    def supports(self, job):
        return (job.command_key, job.command_version) == (
            "export.files.collect",
            "1.0.0",
        )

    def identity(self):
        device, inode = self.client.identity()
        return {
            "identity_reference": f"local-export-inbox:{device}:{inode}",
            "firmware": "not-observed",
            "application": "airalogy-export-inbox",
            "application_version": "1.0.0",
            "driver_version": "1.0.0",
            "os_version": f"{platform.system()}:{platform.release()}",
        }

    def confirm(self, job):
        return None

    def execute(self, job, stop_event):
        if not self.supports(job) or set(job.arguments) != {
            "export_id",
            "sample_reference",
        }:
            raise ValueError("Select the exact file export command and explicit sample")
        return self.client.read(
            job.arguments["export_id"],
            job.arguments["sample_reference"],
            stop_event=stop_event,
            timeout_seconds=20,
        )

    def safe_stop(self, job, reason):
        # No physical process is ever started here. The runtime sets the read
        # cancellation event and separately requires the worker to finish.
        return None


def create_adapter(config_path):
    if config_path is None:
        raise ValueError(
            "Select the private, identity-pinned export inbox configuration"
        )
    return ExportInboxReader(ExportReadClient(read_export_config(config_path), OUTPUTS))
