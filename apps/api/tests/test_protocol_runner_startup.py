"""Fail closed when Docker cannot start; never expose runner credentials."""

import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.libs import protocol_agent


@pytest.mark.parametrize(
    ("stderr", "error_type"),
    [
        (b"docker: Error response from daemon: No such image: missing:tag", "ProtocolExecutorImageMissing"),
        (b"docker: Cannot connect to the Docker daemon", "ProtocolRunnerUnavailable"),
        (b"docker: invalid mount configuration", "ProtocolRunnerUnavailable"),
    ],
)
def test_docker_startup_failure_is_actionable_and_never_falls_back(monkeypatch, capsys, caplog, stderr, error_type):
    monkeypatch.setattr(protocol_agent.config, "PROTOCOL_RUN_ENV", "docker")
    child = SimpleNamespace(returncode=125, communicate=AsyncMock(return_value=(b"private-output", stderr)))
    spawn = AsyncMock(return_value=child)
    monkeypatch.setattr(protocol_agent.asyncio, "create_subprocess_exec", spawn)
    with caplog.at_level(logging.ERROR, logger="app"):
        result = asyncio.run(protocol_agent.protocol_exec("get_protocol_info", "synthetic", {"env_vars": {"AIRALOGY_API_KEY": "synthetic-secret"}}))
    assert not result["success"]
    assert result["error_type"] == error_type
    assert "Keep your draft" in result["message"]
    assert "output" not in result
    spawn.assert_awaited_once()
    args = spawn.call_args.args
    assert args[:4] == ("docker", "run", "--rm", "--pull=never")
    assert protocol_agent.config.AIRALOGY_PROTOCOL_EXECUTOR_IMAGE in args
    captured = capsys.readouterr()
    for private in ["synthetic-secret", "private-output", stderr.decode()]:
        assert private not in captured.out + captured.err + caplog.text


def test_missing_docker_binary_returns_safe_failure(monkeypatch):
    monkeypatch.setattr(protocol_agent.config, "PROTOCOL_RUN_ENV", "docker")
    spawn = AsyncMock(side_effect=FileNotFoundError("docker"))
    monkeypatch.setattr(protocol_agent.asyncio, "create_subprocess_exec", spawn)
    result = asyncio.run(protocol_agent.protocol_exec("get_protocol_info", "synthetic"))
    assert result["error_type"] == "ProtocolRunnerUnavailable"
    spawn.assert_awaited_once()


def test_successful_runner_output_is_not_logged(monkeypatch, capsys):
    monkeypatch.setattr(protocol_agent.config, "PROTOCOL_RUN_ENV", "local")
    child = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b'{"success":true,"data":"private-result"}', b"")))
    monkeypatch.setattr(protocol_agent.asyncio, "create_subprocess_exec", AsyncMock(return_value=child))
    result = asyncio.run(protocol_agent.protocol_exec("var_validate", "synthetic", {"value": "private-input"}))
    assert result == {"success": True, "data": "private-result"}
    assert capsys.readouterr().out == ""


def test_documented_build_tag_matches_default_executor_image():
    api = Path(__file__).resolve().parents[1]
    image = type(protocol_agent.config).model_fields["AIRALOGY_PROTOCOL_EXECUTOR_IMAGE"].default
    command = f"docker build -t {image} -f protocol_executor.Dockerfile ."
    assert command in (api / "protocol_executor.Dockerfile").read_text()
    assert command in (api / "README.md").read_text()


def test_named_executor_bridge_pins_identity_and_uses_its_gateway(monkeypatch):
    import json
    from unittest.mock import Mock

    network = {"name": "lab-executor", "id": "a" * 64, "driver": "bridge", "scope": "local",
               "pools": [{"Subnet": "10.34.80.0/24", "Gateway": "10.34.80.1"}]}
    inspect = Mock(return_value=SimpleNamespace(stdout=json.dumps(network)))
    monkeypatch.setattr(protocol_agent.subprocess, "run", inspect)
    assert protocol_agent._docker_network_args("") == ["--add-host=airalogy-server-host:host-gateway"]
    inspect.assert_not_called()
    assert protocol_agent._docker_network_args("lab-executor") == [
        "--network=" + network["id"], "--add-host=airalogy-server-host:10.34.80.1",
    ]
    args = inspect.call_args.args[0]
    assert args[:3] == ["docker", "network", "inspect"] and args[-1] == "lab-executor"
    for changes in ({"driver": "host"}, {"name": "other"}, {"pools": []},
                    {"pools": [{"Subnet": "192.0.2.0/24", "Gateway": "192.0.2.1"}]},
                    {"pools": [{"Subnet": "10.34.80.0/24", "Gateway": "10.90.0.1"}]}):
        inspect.return_value = SimpleNamespace(stdout=json.dumps({**network, **changes}))
        with pytest.raises(ValueError):
            protocol_agent._docker_network_args("lab-executor")


def test_invalid_configured_network_never_starts_a_default_runner(monkeypatch):
    monkeypatch.setattr(protocol_agent.config, "PROTOCOL_RUN_ENV", "docker")
    monkeypatch.setattr(protocol_agent.config, "AIRALOGY_PROTOCOL_EXECUTOR_NETWORK", "host")
    spawn = AsyncMock()
    monkeypatch.setattr(protocol_agent.asyncio, "create_subprocess_exec", spawn)
    result = asyncio.run(protocol_agent.protocol_exec("get_protocol_info", "synthetic"))
    assert not result["success"] and result["error_type"] == "ProtocolExecutorNetworkUnavailable"
    spawn.assert_not_called()
