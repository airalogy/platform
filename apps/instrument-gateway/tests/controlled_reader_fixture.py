"""Independent stateful control reference for source-only development tests."""

import json
from pathlib import Path

from test_packages import contents

from airalogy_instrument_gateway.package_contract import sha256

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/controlled-reader"
PROJECT = Path(__file__).resolve().parents[3]


def spec():
    manifest = json.loads((EXAMPLE / "manifest.json").read_text())
    manifest["provenance"]["kind"] = "aira"
    return {
        "goal": "Develop controlled-command source against the owned in-memory reference only",
        "manifest": manifest,
        "factory": "controlled_reader:create_adapter",
        "materials": [
            {
                "name": "controlled-reader-api.txt",
                "text": (EXAMPLE / "api-specification.md").read_text(),
            }
        ],
        "tests": {
            "tests/test_controlled_reader.py": (
                EXAMPLE / "tests/test_controlled_reader.py"
            ).read_text()
        },
        "licenses": {"licenses/LICENSE.txt": (PROJECT / "LICENSE").read_text()},
        "initial_sources": {},
    }


def proposal(*, broken=False):
    source = (EXAMPLE / "source/controlled_reader.py").read_text()
    if broken:
        source = source.replace(
            "self.controller.start()  # Exactly once;",
            "self.controller.start()\n        self.controller.start()  # Incorrect duplicate start;",
        )
    return {
        "sources": {"source/controlled_reader.py": source},
        "summary": "Owned simulation control draft; not hardware qualification",
        "assumptions": [],
        "missing_information": [],
    }


def fixture_test(raw, **kwargs):
    # Coordinator/API acceptance substitutes only a known fixture test outcome.
    # Actual independent fake-transport tests run in the separate real sandbox.
    passed = (
        b"Incorrect duplicate start" not in contents(raw)["source/controlled_reader.py"]
    )
    return {
        "archive_digest": sha256(raw),
        "sdk_digest": kwargs["trusted_sdk_digest"],
        "image": kwargs["image"],
        "passed": passed,
        "failure_reason": None if passed else "package_tests",
        "untrusted_test_output": "Independent controlled-source test outcome fixture",
    }
