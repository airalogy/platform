from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]


def test_development_minio_host_ports_are_configurable_and_non_conflicting():
    compose = (API_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (API_ROOT / ".env.example").read_text(encoding="utf-8")

    assert '127.0.0.1:${MINIO_API_PORT:-9200}:9200' in compose
    assert '127.0.0.1:${MINIO_CONSOLE_PORT:-9202}:9201' in compose
    assert "MINIO_API_PORT=9200" in env_example
    assert "MINIO_CONSOLE_PORT=9202" in env_example
