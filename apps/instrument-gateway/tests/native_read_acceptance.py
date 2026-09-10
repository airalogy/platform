"""Independent installed-copy acceptance for a caller-owned running simulator."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from native_read_fixture import package
from test_package_installation import sdk

from airalogy_instrument_gateway.interface_process import NativeReadProcessClient
from airalogy_instrument_gateway.package_contract import sha256
from airalogy_instrument_gateway.package_installation import (
    install_inactive,
    installation_preview,
)

SCRIPT = """
import json,sys,threading
from pathlib import Path
from types import SimpleNamespace
from airalogy_instrument_gateway import load_adapter
adapter=load_adapter('synthetic.native-read',Path(sys.argv[1]))
job=SimpleNamespace(job_id=sys.argv[2],command_key='native.status.read',command_version='1.0.0',arguments={},timeout_seconds=30)
assert adapter.preflight(job)['interlocks']['native.read_access']
print(json.dumps(adapter.execute(job,threading.Event())))
"""


def installed_acceptance(config_path):
    client = NativeReadProcessClient.from_file(config_path)
    raw, wheel = package(), sdk()
    for _ in range(2):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            args = {
                "root": root,
                "sdk_wheel": wheel,
                "trusted_sdk_digest": sha256(wheel),
                "config": client.config,
            }
            preview = installation_preview(raw, **args)
            receipt = install_inactive(
                raw,
                **args,
                preview_digest=preview["preview_digest"],
                source_reviewed=True,
            )
            path = root / "config.json"
            path.write_text(json.dumps(client.config))
            path.chmod(0o600)
            identifier = str(uuid4())
            output = subprocess.run(
                [
                    str(Path(receipt["destination"]) / "bin/python"),
                    "-I",
                    "-B",
                    "-c",
                    SCRIPT,
                    str(path),
                    identifier,
                ],
                capture_output=True,
                check=True,
                timeout=30,
            )
            result = json.loads(output.stdout)
            assert result["operation_id"] == identifier
            assert result["values"] == {
                "reader.status": "Ready",
                "reader.result": "No result",
            }
            assert (
                result["observation_only"] is True and result["simulation_only"] is True
            )
    return {
        "independent_installs": 2,
        "actual_native_reads": 2,
        "hardware_qualified": False,
    }


if __name__ == "__main__":
    print(json.dumps(installed_acceptance(Path(sys.argv[1]))))
