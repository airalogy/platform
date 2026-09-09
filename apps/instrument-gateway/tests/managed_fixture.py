"""Synthetic fixtures only. Never qualification evidence for actual equipment."""

import json

from airalogy_instrument_gateway.package_builder import build_package
from test_packages import EXAMPLE

TARGET = dict.fromkeys(
    (
        "identity_reference",
        "firmware",
        "application",
        "application_version",
        "driver_version",
        "os_version",
    ),
    "Synthetic policy fixture, no hardware",
)


def package(*, physical_policy=False, file_outputs=False):
    manifest = json.loads((EXAMPLE / "manifest.json").read_text())
    manifest["id"] = "synthetic.managed-policy-fixture"
    # Exercise the real-qualification policy branch in disposable tests only.
    # The published example remains simulation-only and cannot be activated.
    if physical_policy:
        manifest["commands"][0]["output_schema"]["properties"]["simulation_only"] = {
            "type": "boolean"
        }
    if file_outputs:
        manifest["id"] = "synthetic.managed-file-policy-fixture"
        manifest["commands"][0]["outputs"] = [
            {
                "name": "synthetic.csv",
                "media_type": "text/csv",
                "max_bytes": 4096,
                "required": True,
            }
        ]
    source = (EXAMPLE / "source/synthetic_reader.py").read_text()
    source = source.replace(
        "    def supports(self, job):",
        f"    def identity(self):\n        return {TARGET!r}\n\n    def supports(self, job):",
    )
    source = (
        source[: source.index("def create_adapter(config_path):")]
        + "def create_adapter(config_path):\n    return SyntheticReader()\n"
    )
    if file_outputs:
        source = (
            source[: source.index("def create_adapter(config_path):")]
            + """
import hashlib
import json
from pathlib import Path
from airalogy_instrument_gateway import InstrumentResult

class SyntheticFileReader(SyntheticReader):
    def __init__(self, root):
        self.root = root

    def execute(self, job, stop_event):
        result = super().execute(job, stop_event)
        content = b"sample,signal\\nsynthetic,0.84\\n"
        (self.root / "synthetic.csv").write_bytes(content)
        return InstrumentResult(result, [{
            "name": "synthetic.csv", "path": "synthetic.csv",
            "sha256": hashlib.sha256(content).hexdigest(),
            "write_complete_confirmed": True,
            "captured_at": "2026-09-09T12:34:56+08:00",
            "original_units": ["signal: synthetic_unit"], "conversion_rules": [],
            "completion_reference": "Synthetic closed file, no equipment",
        }])

def create_adapter(config_path):
    root = Path(json.loads(config_path.read_text())["output_root"])
    marker = root.parent / "synthetic-driver-initialized"
    # A second initialization would fail the recovery acceptance test.
    with marker.open("x") as handle:
        handle.write("Synthetic fixture; no equipment")
    return SyntheticFileReader(root)
"""
        )
    payloads = {
        name: (EXAMPLE / name).read_bytes()
        for name in ("tests/test_reader.py", "licenses/LICENSE.txt")
    }
    payloads["source/synthetic_reader.py"] = source.encode()
    return build_package(
        manifest, factory="synthetic_reader:create_adapter", payloads=payloads
    )[0]
