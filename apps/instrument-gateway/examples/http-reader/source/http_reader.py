"""Reference for the owned loopback simulator ONLY, never a vendor adapter."""

import ipaddress
import math

from airalogy_instrument_gateway import InstrumentAdapter
from airalogy_instrument_gateway.http_read import (
    HttpReadClient,
    HttpReadOperation,
    read_http_read_config,
)

OPERATIONS = {
    "identity": HttpReadOperation("/v1/identity", max_response_bytes=4096),
    "result": HttpReadOperation("/v1/result", ("sample_id",), 4096),
}
TARGET_FIELDS = {
    "identity_reference",
    "firmware",
    "application",
    "application_version",
    "driver_version",
    "os_version",
}


class ReferenceHttpReader(InstrumentAdapter):
    def __init__(self, client):
        self.client = client

    def supports(self, job):
        return (job.command_key, job.command_version) == ("reader.result.read", "1.0.0")

    def identity(self):
        data = self.client.get("identity", timeout_seconds=3).data
        if (
            set(data) != {"simulation_only", "target"}
            or data["simulation_only"] is not True
        ):
            raise ValueError("Expected the owned synthetic API identity")
        target = data["target"]
        if (
            not isinstance(target, dict)
            or set(target) != TARGET_FIELDS
            or any(
                not isinstance(value, str) or not value.strip() or len(value) > 255
                for value in target.values()
            )
        ):
            raise ValueError("Invalid synthetic identity response")
        return target

    def confirm(self, job):
        return None

    def execute(self, job, stop_event):
        if not self.supports(job) or set(job.arguments) != {"sample_id"}:
            raise ValueError("Unknown command or arguments")
        sample_id = job.arguments["sample_id"]
        if sample_id not in {"sample-A", "sample-B"}:
            raise ValueError("Select a documented synthetic sample")
        result = self.client.get(
            "result", {"sample_id": sample_id}, stop_event=stop_event, timeout_seconds=3
        ).data
        if (
            set(result) != {"sample_id", "value", "unit", "simulation_only"}
            or result["sample_id"] != sample_id
            or result["unit"] != "synthetic_unit"
            or result["simulation_only"] is not True
            or type(result["value"]) not in {int, float}
            or not math.isfinite(result["value"])
            or not 0 <= result["value"] <= 100
        ):
            raise ValueError(
                "Synthetic output does not match the fixed sample/schema/units"
            )
        return result

    def safe_stop(self, job, reason):
        # This reference only retrieves pre-existing synthetic constants. It never
        # starts a physical process. Do not copy this into a real device adapter.
        return None


def create_adapter(config_path):
    if config_path is None:
        raise ValueError("Select the private configuration for the owned API fixture")
    config = read_http_read_config(config_path)
    if not ipaddress.ip_address(config["address"]).is_loopback:
        raise ValueError("The synthetic example accepts a loopback fixture only")
    return ReferenceHttpReader(HttpReadClient(config, OPERATIONS))
