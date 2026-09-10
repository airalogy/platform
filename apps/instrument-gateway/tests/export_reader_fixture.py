"""Source-included export reader plus owned synthetic completed files for tests."""

import json
import runpy
from pathlib import Path

from airalogy_instrument_gateway.package_builder import build_package

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/export-reader"
PROJECT = Path(__file__).resolve().parents[3]


def package():
    manifest = json.loads((EXAMPLE / "manifest.json").read_text())
    payloads = {
        name: (EXAMPLE / name).read_bytes()
        for name in ("source/export_reader.py", "tests/test_export_reader.py")
    }
    payloads["licenses/LICENSE.txt"] = (PROJECT / "LICENSE").read_bytes()
    return build_package(
        manifest, factory="export_reader:create_adapter", payloads=payloads
    )[0]


def target(root):
    from test_export_read import config

    from airalogy_instrument_gateway.export_read import ExportReadClient

    module = runpy.run_path(str(EXAMPLE / "source/export_reader.py"))
    return module["ExportInboxReader"](
        ExportReadClient(config(root), module["OUTPUTS"])
    ).identity()
