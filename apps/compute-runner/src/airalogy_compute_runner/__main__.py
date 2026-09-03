"""Command-line entry point for the supervised Compute Runner."""

from __future__ import annotations

import logging

from .client import PlatformClient
from .config import RunnerConfig
from .engine import ContainerEngine
from .runtime import RunnerRuntime
from .state import StateStore


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = RunnerConfig.from_env()
    engine = ContainerEngine(config)
    engine.verify()
    client = PlatformClient(
        config.platform_url,
        config.runner_token,
        timeout_seconds=config.request_timeout_seconds,
        output_upload_timeout_seconds=config.output_upload_timeout_seconds,
    )
    runtime = RunnerRuntime(config, client, engine, StateStore(config.state_file))
    runtime.run_forever()


if __name__ == "__main__":
    main()
