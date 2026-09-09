# Airalogy Instrument Gateway

The Instrument Gateway is the pull-only process that runs beside laboratory equipment. It verifies Platform-signed jobs, applies a second local command allowlist, asks the installed adapter for device-local confirmation and a fresh hardware-safety preflight, maintains the short lease, and reports a schema-validated result or an acknowledged safe stop.

It intentionally has no remote shell, script evaluation, or Platform-delivered adapter code. A real adapter is a separately installed, locally trusted Python package registered under the `airalogy.instrument_adapters` entry-point group. Hardware interlocks and the adapter's idempotent `safe_stop` implementation remain authoritative.

## Install

### Integration rehearsal (no hardware)

The equipment workbench stores versioned `airalogy.gui-rehearsal.v1` bundles: observations and bounded literal steps, **not executable Adapter Packages**. They never enter Instrument Jobs or grant device authority. From the repository root:

```bash
pnpm gateway:rehearse --example
pnpm gateway:rehearse /absolute/path/to/rehearsal.json
pnpm gateway:gui-demo
```

The last command operates the bundled synthetic reader in an isolated browser with all network requests denied, checks an independently fixed expected output, and prints an importable bundle. It needs Playwright Chromium; `--headed` shows the software. The Python CLI needs no model, credentials, browser or network.

The contract is authored in `src/airalogy_instrument_gateway/integration_contract.py`. After editing it, run `node scripts/sync-instrument-contract.mjs` from the repository root to generate the API copy for its independent Docker build context. CI checks equality. See the [support matrix](../../docs/en/architecture/instrument-integration.md).

## Gateway runtime installation

Executable adapters now have a separate source-included package format and a no-network Docker test path. See [Adapter Packages](../../docs/en/architecture/instrument-adapter-packages.md). Inspection never imports driver code; the test command never installs it on the host. Distribution, approved workstation installation and equipment qualification are separate from package tests.

### Local pairing

Instead of copying a long-lived token through the browser, a Lab administrator can create a ten-minute code for a **disabled** Gateway. The local assistant generates its credential in an exclusive private file, claims the code and displays an identity fingerprint. Only after comparing that fingerprint does the administrator approve replacement of the old credential. The Gateway remains disabled; pairing does not load adapters, poll jobs or qualify hardware.

```bash
pnpm gateway:pair --credential-file /private/service-directory/gateway.json --platform-url https://lab.example.edu/api --lab-id <Lab-UUID> --gateway-id <Gateway-UUID> --client-name "Local station"
```

Replace all placeholders; create the service-account-owned parent directory with mode `0700` first. Enter the code at the hidden interactive prompt, never in command arguments. Installed packages can use `python -m airalogy_instrument_gateway.pairing_cli` with the same arguments. Runtime configuration accepts `AIRALOGY_GATEWAY_CREDENTIAL_FILE` **instead of** `AIRALOGY_GATEWAY_TOKEN` and inherits the paired Platform URL. Credential files are POSIX-only for now; unsupported ACL storage fails closed. See [pairing, recovery and support boundaries](../../docs/en/architecture/instrument-integration.md#local-installation-pairing).

### Supervised runtime

Use a dedicated operating-system account on the equipment network:

```bash
python3 -m venv .venv
.venv/bin/pip install .
```

Register a Gateway and its exact command versions in Platform, then place the one-time credential in the local service manager's secret store. Configure:

```text
AIRALOGY_PLATFORM_URL=https://lab.example.edu/api
AIRALOGY_GATEWAY_TOKEN=<one-time Gateway credential>
AIRALOGY_GATEWAY_ADAPTER=<locally installed adapter name>
AIRALOGY_GATEWAY_ADAPTER_CONFIG=/etc/airalogy/instrument-adapter.json
AIRALOGY_GATEWAY_STATE_FILE=/var/lib/airalogy-instrument-gateway/state.json
```

Start `airalogy-instrument-gateway` under systemd, launchd, or another supervised service. The state path contains a short-lived job lease and is atomically written with owner-only permissions; keep its parent directory private and persistent across restarts.

`deploy/airalogy-instrument-gateway.service` and `deploy/instrument-gateway.env.example` provide a hardened systemd starting point. Copy the environment file to `/etc/airalogy/instrument-gateway.env`, restrict it to the service account, replace every placeholder, and install only the device permissions required by the selected adapter. The template deliberately does not grant generic device access.

The built-in `mock` adapter is only for development:

```text
AIRALOGY_PLATFORM_URL=http://127.0.0.1:4000
AIRALOGY_GATEWAY_ADAPTER=mock
AIRALOGY_GATEWAY_ADAPTER_CONFIG=examples/mock-adapter.json
```

HTTP is accepted automatically only for loopback. `AIRALOGY_GATEWAY_ALLOW_INSECURE_HTTP=true` is an explicit test-network override and must not be used for normal deployments.

## Adapter contract

For source-reviewed pure Python packages, `airalogy-instrument-installation` prepares an installation-only request and applies its independent Platform grant without reading the Gateway runtime credential or executing drivers. See [the shared installation guide](../../docs/en/architecture/instrument-adapter-packages.md#platform-authorized-installation-and-receipt-synchronization). The installer must use the same service directory and journal as this runtime. An installed receipt is not equipment qualification or activation.

An adapter subclasses `InstrumentAdapter` and implements exact-version `supports`, device-local `confirm`, blocking `execute`, and idempotent `safe_stop`. It should override `preflight` for commands whose Platform safety contract requires interlocks, local operator presence, or emergency-stop availability. Export a factory accepting an optional configuration `Path`:

```toml
[project.entry-points."airalogy.instrument_adapters"]
microscope = "my_lab_adapter:create_adapter"
```

Immediately before every start, the Gateway calls `preflight(job)`. It must read current hardware state rather than reuse a cached value and return `interlocks` as boolean values plus `operator_present`, `emergency_stop_available`, and a local `reference`. The Gateway rejects the job before device start if any pinned requirement is false or missing, then Platform repeats the same validation and retains the attestation. Commands with no safety requirements remain compatible with existing adapters whose default `preflight` returns an empty object.

The adapter must reject every command it does not explicitly know, return only JSON-object results, react to the supplied stop event, and return from `safe_stop` only after the device has reached its hardware-specific safe state. If safe stop cannot be confirmed, it must raise; the Gateway then halts rather than accepting another job.

The supervised entry point holds an exclusive lock for its configured state journal, including adapter loading. Installation managers must take the same lock and require an empty journal before switching software. Do not delete the lock file or start another journal to bypass a busy installation. A failed safe stop persists as `stop_unconfirmed`; restart retries only the adapter's idempotent stop, never the physical command. Execution exceptions also require a confirmed stop before reporting failure. Legacy failure receipts without a safety marker are conservatively rechecked. A live, unresponsive worker prevents in-process reconciliation; recover under the supervisor with the same adapter and journal.
