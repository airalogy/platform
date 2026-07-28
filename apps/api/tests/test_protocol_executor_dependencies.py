import re
import tomllib
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]


def _exact_version(requirements: list[str], package: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(package)}(?:\[[^\]]+\])?\s*==\s*([^\s;]+)$",
        re.IGNORECASE,
    )
    for requirement in requirements:
        if match := pattern.fullmatch(requirement.strip()):
            return match.group(1)
    raise AssertionError(f"{package} must use an exact version pin")


def test_protocol_executor_airalogy_version_matches_backend():
    pyproject = tomllib.loads(
        (API_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    backend_requirements = pyproject["project"]["dependencies"]
    executor_requirements = [
        line
        for line in (
            API_ROOT / "protocol_requirements.txt"
        ).read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]

    assert _exact_version(
        executor_requirements, "airalogy"
    ) == _exact_version(backend_requirements, "airalogy")
