"""Explicitly selected, verified installed runtime. Not an untrusted-code sandbox."""

import argparse
import logging
import queue
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from .activation_contract import activation_digest, validate_activation_pin
from .adapters import InstrumentAdapter, load_adapter
from .client import PlatformClient
from .config import GatewayConfig
from .credentials import read_credentials, read_private_json, write_credentials
from .installation_contract import descriptor_from_preview, receipt_summary
from .installation_manager import _inputs, read_request
from .package_cli import read_selected
from .package_contract import sha256
from .package_installation import _contents, installation_preview, verify_installation
from .runtime import GatewayHaltError, GatewayRuntime
from .security import verify_job_signature
from .state import StateStore


def local_installation(request_path, credential_path):
    request = read_request(request_path)
    credentials = read_credentials(Path(credential_path))
    if (
        any(
            request["request"][key] != credentials[key]
            for key in ("lab_id", "gateway_id")
        )
        or request["platform_url"] != credentials["platform_url"]
    ):
        raise ValueError("Installed binding and paired runtime destination differ")
    inputs = _inputs(request)
    raw = read_selected(Path(request["package"]))
    plan = installation_preview(raw, **inputs)
    descriptor = descriptor_from_preview(plan)
    if descriptor != request["request"]["descriptor"]:
        raise ValueError("Installed package, SDK, configuration or interpreter changed")
    _, files = _contents(raw, inputs["sdk_wheel"], inputs["trusted_sdk_digest"])
    receipt = verify_installation(
        inputs["root"] / descriptor["installation_id"],
        expected_plan=plan,
        expected_files={name: sha256(value) for name, value in files.items()},
    )
    return request, credentials, inputs, descriptor, receipt


def validate_selection(response, request, credentials, descriptor, receipt):
    value = response.get("activation")
    if not isinstance(value, dict):
        raise ValueError("No currently authorized managed version is available")  # noqa: TRY004 - absent authorization, not caller argument typing
    verify_job_signature(
        value, response.get("signature", ""), credentials["gateway_token"]
    )
    pin = validate_activation_pin(value["pin"])
    target_keys = {
        "identity_reference",
        "firmware",
        "application",
        "application_version",
        "driver_version",
        "os_version",
    }
    target = value.get("target")
    commands = value.get("commands")
    if (
        not isinstance(target, dict)
        or set(target) != target_keys
        or any(not isinstance(v, str) or not v or len(v) > 500 for v in target.values())
    ):
        raise ValueError("Invalid qualified equipment identity")
    expiry = datetime.fromisoformat(value["expires_at"])
    if (
        expiry.tzinfo is None
        or not isinstance(commands, list)
        or not 1 <= len(commands) <= 10
    ):
        raise ValueError("Invalid active-version expiry or command allowlist")
    identities = set()
    for command in commands:
        required = {
            "id",
            "revision",
            "key",
            "version",
            "input_schema",
            "output_schema",
            "risk",
            "device_confirmation_required",
            "safety_contract",
            "timeout_seconds",
            "resource_revision_id",
            "resource_revision",
        }
        if not isinstance(command, dict) or set(command) != required:
            raise ValueError("Invalid active-version command contract")
        identity = (command["key"], command["version"])
        if identity in identities:
            raise ValueError("Duplicate active-version command")
        identities.add(identity)
    if (
        pin["binding_id"] != request["request"]["id"]
        or any(value[key] != credentials[key] for key in ("lab_id", "gateway_id"))
        or value["descriptor"] != descriptor
        or value["receipt"] != receipt_summary(receipt)
        or pin["installation_id"] != descriptor["installation_id"]
        or pin["target_digest"] != activation_digest(value["target"])
    ):
        raise ValueError("Active version does not match the exact local installation")
    return value


class ManagedClient(PlatformClient):
    def __init__(self, credentials, activation):
        super().__init__(credentials["platform_url"], credentials["gateway_token"])
        self.activation = activation

    def lease(self):
        # An old process never follows a new active pointer or reloads a driver.
        current = self._request("GET", "/instrument-gateway/v1/activation")
        value = current.get("activation")
        if not isinstance(value, dict) or value.get("pin") != self.activation["pin"]:
            raise GatewayHaltError(
                "Active version changed or was revoked; stop and review the next version"
            )
        verify_job_signature(value, current.get("signature", ""), self.gateway_token)
        return self._request(
            "POST",
            "/instrument-gateway/v1/jobs/lease",
            payload={"activation": self.activation["pin"]},
        )

    def start(self, job_id, lease_token, **parameters):
        return self._request(
            "POST",
            f"/instrument-gateway/v1/jobs/{job_id}/start",
            lease_token=lease_token,
            payload={**parameters, "activation": self.activation["pin"]},
        )


class ManagedAdapter(InstrumentAdapter):
    def __init__(self, driver, activation, verify_inputs):
        self.driver = driver
        self.activation = activation
        self.verify_inputs = verify_inputs
        self.commands = {
            (item["key"], item["version"]): item for item in activation["commands"]
        }

    def supports(self, job):
        expected = self.commands.get((job.command_key, job.command_version))
        if expected is None or job.raw.get("activation") != self.activation["pin"]:
            return False
        if (
            job.resource_id != self.activation["resource_id"]
            or job.resource_revision_id != expected["resource_revision_id"]
            or job.resource_revision != expected["resource_revision"]
        ):
            return False
        keys = (
            "key",
            "version",
            "revision",
            "input_schema",
            "output_schema",
            "risk",
            "device_confirmation_required",
            "safety_contract",
            "timeout_seconds",
        )
        return all(
            job.raw["command"].get(key) == expected[key] for key in keys
        ) and self.driver.supports(job)

    def check_identity(self):
        observations = queue.Queue(maxsize=1)

        def observe():
            try:
                observations.put((True, self.driver.identity()))
            except Exception as error:  # noqa: BLE001 - contain reviewed driver failures and reject execution
                observations.put((False, error))

        probe = threading.Thread(
            target=observe, daemon=True, name="instrument-identity"
        )
        probe.start()
        probe.join(5)
        if probe.is_alive():
            raise GatewayHaltError(
                "Identity probe timed out; keep the controller locked until process exit"
            )
        valid, result = observations.get_nowait()
        if not valid:
            raise ValueError(
                "The reviewed adapter could not observe the equipment identity"
            ) from result
        if result != self.activation["target"]:
            raise ValueError(
                "Observed equipment/software identity changed; reassessment is required"
            )

    def confirm(self, job):
        self.check_identity()
        return self.driver.confirm(job)

    def preflight(self, job):
        self.verify_inputs()
        self.check_identity()
        return self.driver.preflight(job)

    def execute(self, job, stop_event):
        if not self.supports(job):
            raise ValueError("Job differs from the locally selected command allowlist")
        self.check_identity()
        return self.driver.execute(job, stop_event)

    def safe_stop(self, job, reason):
        # Revocation/drift must not prevent stopping the original selected driver.
        return self.driver.safe_stop(job, reason)


def inspect_start(
    request_path, credential_path, activation_id, *, recover=False, client=None
):
    request, credentials, inputs, descriptor, receipt = local_installation(
        request_path, credential_path
    )
    activation_id = str(UUID(activation_id))
    store = StateStore(inputs["root"] / "state.json")
    saved = inputs["root"] / f"activation-{activation_id}.json"
    if recover:
        state = store.load()
        if (
            state is None
            or state.envelope.get("activation", {}).get("id") != activation_id
        ):
            raise ValueError(
                "Recovery requires an unresolved job on this exact active version"
            )
        response = read_private_json(saved, max_bytes=4 * 1024 * 1024)
    else:
        store.assert_installable()
        client = client or PlatformClient(
            credentials["platform_url"], credentials["gateway_token"]
        )
        response = client._request("GET", "/instrument-gateway/v1/activation")
    activation = validate_selection(response, request, credentials, descriptor, receipt)
    if activation["pin"]["id"] != activation_id:
        raise ValueError("The selected active version is no longer current")
    if not recover and datetime.fromisoformat(activation["expires_at"]) <= datetime.now(
        UTC
    ):
        raise ValueError("The active version has expired")
    preview = {
        "operation": "recover_managed_instrument"
        if recover
        else "start_managed_instrument",
        "activation": activation,
        "local_destination": str(inputs["root"] / descriptor["installation_id"]),
        "journal": str(inputs["root"] / "state.json"),
        "startup_may_initialize_equipment": True,
    }
    return (
        {**preview, "preview_digest": activation_digest(preview)},
        response,
        (request, credentials, inputs, descriptor, receipt),
        saved,
    )


def run_installed(
    request_path,
    credential_path,
    activation_id,
    *,
    confirm_digest,
    once=False,
    recover=False,
):
    # Called only inside the verified installed SDK, under a clean interpreter.
    request = read_request(request_path)
    store = StateStore(Path(request["root"]) / "state.json")
    with store.exclusive():
        preview, response, local, saved = inspect_start(
            request_path, credential_path, activation_id, recover=recover
        )
        if preview["preview_digest"] != confirm_digest:
            raise ValueError("Local startup preview changed; inspect and confirm again")
        request, credentials, inputs, descriptor, receipt = local
        site = inputs["root"] / descriptor["installation_id"] / receipt["site_packages"]
        if Path(__file__).resolve().parent.parent != site or not (
            sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
        ):
            raise ValueError(
                "Use the verified isolated activation launcher, not a host-installed runtime"
            )
        if saved.exists():
            if read_private_json(saved, max_bytes=4 * 1024 * 1024) != response:
                raise ValueError(
                    "Saved active-version identity differs from the signed approval"
                )
        else:
            write_credentials(saved, response)
        activation = response["activation"]
        config = GatewayConfig(
            platform_url=credentials["platform_url"],
            gateway_token=credentials["gateway_token"],
            adapter_name=descriptor["entry_point"],
            adapter_config=Path(request["config"]),
            state_file=store.path,
        )

        def verify_inputs():
            current = local_installation(request_path, credential_path)
            if (
                current[3] != descriptor
                or receipt_summary(current[4]) != activation["receipt"]
            ):
                raise ValueError("Local installed bytes changed")

        driver = load_adapter(config.adapter_name, config.adapter_config)
        adapter = ManagedAdapter(driver, activation, verify_inputs)
        runtime = GatewayRuntime(
            config, ManagedClient(credentials, activation), adapter, store
        )
        if recover:
            runtime.recover_pending()
        elif once:
            runtime.run_once()
        else:
            runtime.run_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--activation", required=True)
    parser.add_argument("--confirm-digest", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        run_installed(
            args.request,
            args.credentials,
            args.activation,
            confirm_digest=args.confirm_digest,
            once=args.once,
            recover=args.recover,
        )
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as error:
        print(f"Managed runtime stopped: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
