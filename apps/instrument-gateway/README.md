# Airalogy Instrument Gateway

The Instrument Gateway is the pull-only process that runs beside laboratory equipment. It verifies Platform-signed jobs, applies a second local command allowlist, asks the installed adapter for device-local confirmation and a fresh hardware-safety preflight, maintains the short lease, and reports a schema-validated result or an acknowledged safe stop.

It intentionally has no remote shell, script evaluation, or Platform-delivered adapter code. A real adapter is a separately installed, locally trusted Python package registered under the `airalogy.instrument_adapters` entry-point group. Hardware interlocks and the adapter's idempotent `safe_stop` implementation remain authoritative.

## Install

### Installed browser workflow bridge

`airalogy_instrument_gateway.interface_process.InterfaceProcessClient` runs a separately prepared, byte-pinned local Node/headless-Chromium worker through fixed stdin/stdout requests. Review the [runtime preparation and source-included reference](../../docs/en/architecture/instrument-interface-worker.md) before using its private configuration in the existing installation/qualification/activation flow. Node, dependencies, browser, workflow and module resolution are reverified before each invocation; no remote shell, listener, model credential or job-delivered code is added.

Actual software acceptance covers installed Instrument Job execution and receipt-only recovery without reopening the browser. The included reference is owned simulation only; physical stop is deliberately unqualified and failures retain the Gateway reconciliation lock. Native/visual production control and OS installation are not supplied by this bridge.

### Integration rehearsal (no hardware)

The equipment workbench stores versioned `airalogy.gui-rehearsal.v1` bundles: observations and bounded literal steps, **not executable Adapter Packages**. They never enter Instrument Jobs or grant device authority. From the repository root:

```bash
pnpm gateway:rehearse --example
pnpm gateway:rehearse /absolute/path/to/rehearsal.json
pnpm gateway:gui-demo
```

The last command operates the bundled synthetic reader in an isolated browser with all network requests denied, checks an independently fixed expected output, and prints an importable bundle. It needs Playwright Chromium; `--headed` shows the software. The Python CLI needs no model, credentials, browser or network.

The contract is authored in `src/airalogy_instrument_gateway/integration_contract.py`. After editing it, run `node scripts/sync-instrument-contract.mjs` from the repository root to generate the API copy for its independent Docker build context. CI checks equality. See the [support matrix](../../docs/en/architecture/instrument-integration.md).

`output_contract.py` and `output_capture.CaptureStore` provide the [local raw-file capture foundation](../../docs/en/architecture/instrument-adapter-packages.md#local-raw-file-capture-foundation): pinned selections, private bounded snapshots and provenance. The runtime now supports [automatic scoped delivery and receipt-only restart recovery](../../docs/en/architecture/instrument-adapter-packages.md#automatic-delivery-and-recovery) when an explicit output directory is configured. Reviewed file-producing adapters return `InstrumentResult` with acquisition-time file hashes; ordinary no-file commands retain dictionary results. This does not grant file access, verify scientific success or automatically delete retained data.

## Gateway runtime installation

Executable adapters now have a separate source-included package format and a no-network Docker test path. See [Adapter Packages](../../docs/en/architecture/instrument-adapter-packages.md). Inspection never imports driver code; the test command never installs it on the host. Distribution, approved workstation installation and equipment qualification are separate from package tests.

### Local source authoring

For the [private local browser guide](../../docs/en/architecture/instrument-source-authoring.md#local-browser-development-guide), run `airalogy-instrument-authoring serve --workspace /absolute/private/development` (source checkout: `pnpm gateway:author serve --workspace ...`). Use an existing `0700` POSIX development directory separate from runtime credentials/journals. The guide previews selected material, downloads a private bearer-free authorization, starts only explicitly confirmed bounded work and offers verified retained draft packages. It supports cooperative pause and same-request recovery; it never self-approves, installs or starts equipment. Closing the browser is not a pause; interrupted tests require separate confirmation to reconcile.

The separate [source authoring assistant](../../docs/en/architecture/instrument-source-authoring.md) can use explicitly selected material and fixed tests to produce actual Python Adapter Packages through bounded Aira calls and offline sandbox repair. Run `airalogy-instrument-authoring --help` after installation. Its short-lived credential and private development journal are separate from this runtime; a tested draft does not authorize installation, software exploration or hardware control.

Non-read-only source drafts require additional explicit Platform consent and visible command effects/completion/stop review. The owned `examples/controlled-reader` reference exercises parameter readback, single start, takeover and uncertain stopping with independent fake transports; it has no production configuration and remains simulation-only. This expands source development, not device access or execution authority.

### Documented HTTP interfaces

For independently documented parameter/start/stop APIs, the separate [reviewed HTTP control backend](../../docs/en/architecture/instrument-http-control.md) fixes methods/paths/body fields in approved code and selects enabled operation names in a separate private configuration. It shares pinned TLS and non-retrying bounded I/O with the read client. The owned `examples/http-controlled-reader` package demonstrates correlated completion, single start, stopping and installed receipt recovery; it is simulation-only and grants no real device authority.

The SDK's [bounded HTTP read backend](../../docs/en/architecture/instrument-http-interface.md) provides fixed GET/JSON operations, private explicit origin/IP/authentication configuration, verified TLS, response/deadline limits and cancellation without redirects or retries. The source-included `examples/http-reader` reference and its loopback simulator exercise reuse, independent package tests and installed result recovery. It is not a generic network tool, real-device adapter or physical safe-stop implementation. Manual development remains available without AI.

### Completed file exports

For file-only workflows, the [read-only export inbox backend](../../docs/en/architecture/instrument-export-interface.md) reads a selected export UUID only after an independently reviewed producer publishes its completion manifest. The source-included `examples/export-reader` collects original CSV/receipt bytes, preserves sample/units/timezone evidence, and uses existing scoped draft asset delivery with receipt-only recovery. It neither scans arbitrary folders nor claims experiment success or live hardware identity. See the guide for producer prerequisites, POSIX configuration, manual packaging and optional Aira inputs.

### Local browser setup

First install a reviewed SDK using the [provenance-checked isolated bootstrap](../../docs/en/architecture/instrument-sdk-installation.md), or the existing trusted manual package workflow. The standalone bootstrap is attached to official releases and does not need an already installed Gateway. Trust the bootstrap itself independently before execution; it does not install Python/GitHub CLI, configure services or qualify equipment.

After installing the reviewed Gateway SDK on an authorized POSIX workstation, run:

```bash
airalogy-instrument-setup --root /absolute/private/service-directory
```

From this source checkout, use `pnpm gateway:setup --root /absolute/private/service-directory`. Replace the example with an existing service-account-owned `0700` directory shared with the Gateway journal. The command prints a private, one-hour loopback address; open it manually in the local browser and do not share the address. It does not open applications automatically.

The bilingual guide confirms the Platform destination, creates/reuses private identity, claims pairing codes, copies selected files locally, previews installation inputs, downloads only the public authorization request and applies independently approved **inactive** installations. Ordinary private files restore saved work after a refresh/restart; Gateway/installer secrets and configuration content are not returned to the browser or uploaded as part of the public request. The independent SDK checksum is still required, not inferred from the selected file.

Read [the local setup workflow, recovery and security boundaries](../../docs/en/architecture/instrument-integration.md#local-browser-setup). This is not a signed bootstrap installer, automatic adapter generator, Windows/vendor installer or unattended service. Source development, qualification and activation remain separate. Existing command-line workflows below remain supported.

### Local pairing

Instead of copying a long-lived token through the browser, a Lab administrator can create a ten-minute code for a **disabled** Gateway. The local assistant generates its credential in an exclusive private file, claims the code and displays an identity fingerprint. Only after comparing that fingerprint does the administrator approve replacement of the old credential. The Gateway remains disabled; pairing does not load adapters, poll jobs or qualify hardware.

```bash
pnpm gateway:pair --credential-file /private/service-directory/gateway.json --platform-url https://lab.example.edu/api --lab-id <Lab-UUID> --gateway-id <Gateway-UUID> --client-name "Local station"
```

Replace all placeholders; create the service-account-owned parent directory with mode `0700` first. Enter the code at the hidden interactive prompt, never in command arguments. Installed packages can use `python -m airalogy_instrument_gateway.pairing_cli` with the same arguments. Runtime configuration accepts `AIRALOGY_GATEWAY_CREDENTIAL_FILE` **instead of** `AIRALOGY_GATEWAY_TOKEN` and inherits the paired Platform URL. Credential files are POSIX-only for now; unsupported ACL storage fails closed. See [pairing, recovery and support boundaries](../../docs/en/architecture/instrument-integration.md#local-installation-pairing).

### Supervised runtime

The following is the existing **unmanaged** adapter path. An installation claimed through the managed lifecycle cannot use manual enablement or this generic entry point to bypass qualification. For managed packages, use the separate [active-version authorization and explicit local launcher](../../docs/en/architecture/instrument-adapter-packages.md#active-versions-local-startup-and-rollback). It pins the reviewed installed SDK/driver/config, checks fresh `identity()` observations, and retains old-version safe-stop/result recovery; Platform does not remotely launch the process. Current managed installation support is POSIX/pure-Python, not Windows/native vendor installation or physical certification.

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

The adapter must reject every command it does not explicitly know, return a JSON-object result (wrapped in `InstrumentResult` for file-producing commands), react to the supplied stop event, and return from `safe_stop` only after the device has reached its hardware-specific safe state. If safe stop cannot be confirmed, it must raise; the Gateway then halts rather than accepting another job.

The supervised entry point holds an exclusive lock for its configured state journal, including adapter loading. Installation managers must take the same lock and require an empty journal before switching software. Do not delete the lock file or start another journal to bypass a busy installation. A failed safe stop persists as `stop_unconfirmed`; restart retries only the adapter's idempotent stop, never the physical command. Execution exceptions also require a confirmed stop before reporting failure. Legacy failure receipts without a safety marker are conservatively rechecked. A live, unresponsive worker prevents in-process reconciliation; recover under the supervisor with the same adapter and journal.
