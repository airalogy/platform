"""Instrument Gateway command-line entry point."""

from __future__ import annotations

import logging

from .adapters import load_adapter
from .client import PlatformClient
from .config import GatewayConfig
from .output_delivery import receipt_only
from .runtime import GatewayRuntime
from .state import StateStore


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = GatewayConfig.from_env()
    state_store = StateStore(config.state_file)
    with state_store.exclusive():
        adapter = (
            None
            if receipt_only(state_store.load())
            else load_adapter(config.adapter_name, config.adapter_config)
        )
        client = PlatformClient(
            config.platform_url,
            config.gateway_token,
            timeout_seconds=config.request_timeout_seconds,
            file_delivery_enabled=config.output_root is not None,
        )
        GatewayRuntime(config, client, adapter, state_store).run_forever()


if __name__ == "__main__":
    main()
