# Airalogy Instrument Gateway

The Instrument Gateway is the pull-only process that runs beside laboratory equipment. It verifies Platform-signed jobs, applies a second local command allowlist, asks the installed adapter for device-local confirmation and a fresh hardware-safety preflight, maintains the short lease, and reports a schema-validated result or an acknowledged safe stop.

It intentionally has no remote shell, script evaluation, or Platform-delivered adapter code. A real adapter is a separately installed, locally trusted Python package registered under the `airalogy.instrument_adapters` entry-point group. Hardware interlocks and the adapter's idempotent `safe_stop` implementation remain authoritative.

## Install

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

An adapter subclasses `InstrumentAdapter` and implements exact-version `supports`, device-local `confirm`, blocking `execute`, and idempotent `safe_stop`. It should override `preflight` for commands whose Platform safety contract requires interlocks, local operator presence, or emergency-stop availability. Export a factory accepting an optional configuration `Path`:

```toml
[project.entry-points."airalogy.instrument_adapters"]
microscope = "my_lab_adapter:create_adapter"
```

Immediately before every start, the Gateway calls `preflight(job)`. It must read current hardware state rather than reuse a cached value and return `interlocks` as boolean values plus `operator_present`, `emergency_stop_available`, and a local `reference`. The Gateway rejects the job before device start if any pinned requirement is false or missing, then Platform repeats the same validation and retains the attestation. Commands with no safety requirements remain compatible with existing adapters whose default `preflight` returns an empty object.

The adapter must reject every command it does not explicitly know, return only JSON-object results, react to the supplied stop event, and return from `safe_stop` only after the device has reached its hardware-specific safe state. If safe stop cannot be confirmed, it must raise; the Gateway then halts rather than accepting another job.
