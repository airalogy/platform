"""Deterministic pure-Python wheel assembly without running build scripts.

External prebuilt wheels can be imported instead. This convenience builder is for
Python source-only adapters; native/OS driver builds need their own reviewed tools.
"""

import base64
import csv
import io
import json
import re
import zipfile

from .package_contract import (
    ENTRY_POINT,
    canonical,
    inspect_package,
    pack,
    safe_path,
    sha256,
)


def source_wheel(
    *, distribution, version, entry_name, factory, sources, requirements=()
):
    if (
        not re.fullmatch(r"[a-z][a-z0-9_]+", distribution)
        or not re.fullmatch(r"\d+\.\d+\.\d+", version)
        or not ENTRY_POINT.fullmatch(factory)
    ):
        raise ValueError(
            "Builder requires a normalized distribution, stable version and module:factory"
        )
    if not sources or any(not name.endswith(".py") for name in sources):
        raise ValueError("Source builder accepts explicit Python files only")
    files = {safe_path(name): value for name, value in sources.items()}
    if factory.split(":")[0].replace(".", "/") + ".py" not in files:
        raise ValueError("Factory module is not in the supplied sources")
    metadata = f"Metadata-Version: 2.3\nName: {distribution}\nVersion: {version}\nRequires-Python: >=3.11\n"
    for requirement in requirements:
        if (
            not isinstance(requirement, str)
            or any(ord(c) < 32 for c in requirement)
            or len(requirement) > 512
        ):
            raise ValueError("Invalid dependency declaration")
        metadata += f"Requires-Dist: {requirement}\n"
    prefix = f"{distribution}-{version}.dist-info/"
    files[prefix + "METADATA"] = metadata.encode()
    files[prefix + "WHEEL"] = (
        b"Wheel-Version: 1.0\nGenerator: airalogy-source-builder-v1\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    files[prefix + "entry_points.txt"] = (
        f"[airalogy.instrument_adapters]\n{entry_name} = {factory}\n".encode()
    )
    records = io.StringIO(newline="")
    writer = csv.writer(records, lineterminator="\n")
    for name, value in sorted(files.items()):
        digest = (
            base64.urlsafe_b64encode(bytes.fromhex(sha256(value))).decode().rstrip("=")
        )
        writer.writerow([name, "sha256=" + digest, str(len(value))])
    writer.writerow([prefix + "RECORD", "", ""])
    files[prefix + "RECORD"] = records.getvalue().encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, value in sorted(files.items()):
            archive.writestr(
                zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), value
            )
    return f"{distribution}-{version}-py3-none-any.whl", buffer.getvalue()


def build_package(manifest, *, factory, payloads, requirements=()):
    """Build from explicit bytes; never follow paths or execute Python source."""
    manifest = json.loads(canonical(manifest))
    sources = {
        name.removeprefix("source/"): value
        for name, value in payloads.items()
        if name.startswith("source/")
    }
    wheel_name, wheel = source_wheel(
        distribution=re.sub(r"[.-]", "_", manifest["id"]),
        version=manifest["version"],
        entry_name=manifest["entry_point"],
        factory=factory,
        sources=sources,
        requirements=requirements,
    )
    wheel_path = "wheels/" + wheel_name
    payloads = {**payloads, wheel_path: wheel}
    roles = {
        "source": "source",
        "tests": "test",
        "licenses": "license",
        "wheels": "dependency_wheel",
    }
    manifest["files"] = [
        {
            "path": name,
            "sha256": sha256(value),
            "size_bytes": len(value),
            "role": "adapter_wheel"
            if name == wheel_path
            else roles[name.split("/")[0]],
        }
        for name, value in sorted(payloads.items())
    ]
    raw = pack(manifest, payloads)
    return raw, inspect_package(raw)
