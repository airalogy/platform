"""Pure catalog contracts; every shipped component is parsed by the real executor."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from app.config import config
from app.libs.protocol_agent import protocol_exec
from app.services.scenario_catalog import (
    MODULES,
    availability,
    catalog,
    digest,
    template_files,
)


def test_catalog_is_closed_and_compatible():
    for entry in catalog():
        assert entry["external_services"] == []
        assert not availability(
            entry, enabled_modules=set(MODULES), platform_version="0.3.1"
        )
        assert availability(entry, enabled_modules=set(), platform_version="0.3.1")
        assert availability(
            entry, enabled_modules=set(MODULES), platform_version="development"
        )
        assert entry["digest"] == digest(
            {k: v for k, v in entry.items() if k != "digest"}
        )


@pytest.mark.parametrize(
    "component,version",
    [("sample", "1.0.0"), ("measurement", "1.0.0"), ("measurement", "1.1.0")],
)
def test_bundled_protocol_compiles(component, version):
    async def exercise():
        Path(config.PROTOCOL_DIR).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=config.PROTOCOL_DIR) as directory:
            for name, content in template_files(
                component, "synthetic_kit", version
            ).items():
                (Path(directory) / name).write_text(content)
            result = await protocol_exec(
                "get_protocol_info", Path(directory).name, {"env_vars": {}}
            )
            assert result["success"], result
            schema = result["data"]["json_schema"]["vars"]
            assert schema["additionalProperties"] is False
            if component == "measurement":
                assert {
                    "sample",
                    "value",
                    "method",
                    "metric",
                    "unit",
                    "measured_at",
                } <= set(schema["required"])
                sample = next(
                    field
                    for field in result["data"]["fields"]["vars"]
                    if field["name"] == "sample"
                )
                assert sample["kwargs"]["resource_role"] == "reference"

    asyncio.run(exercise())
