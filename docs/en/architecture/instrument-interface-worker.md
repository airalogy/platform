# Installed adapter to local interface worker

The Gateway SDK's `InterfaceProcessClient` connects an **independently reviewed and installed Python adapter** to the existing fixed browser workflow backend. It uses one bounded, local stdin/stdout process invocation, not an HTTP listener, remote desktop, shell endpoint or second Platform control system. Jobs do not deliver code, URLs, selectors or new parameter values. Platform permissions, booking, exact activation, local checks, leases and the durable Gateway journal remain the execution authority.

This closes a software integration gap: an installed adapter can execute a selected [fixed workflow](./instrument-interface-workflow.md), return its actual readback as an Instrument Job result, and recover a lost completion receipt **without importing the driver or launching Node/Chromium again**. The reference and actual acceptance use owned simulation HTML; they do not qualify a vendor application or physical instrument. Native/visual managed execution remains open.

## Prepare the independent runtime

Install the workspace's exact Node/dependency versions and Playwright Chromium through your independently reviewed deployment procedure. Preparation does not install or download anything. It selects that release's dedicated **headless shell**, never an existing personal browser/profile. The pinned Playwright registry layout must be supported; missing/incompatible runtimes fail instead of falling back. Use a saved workflow and an existing owner-only evidence directory:

```bash
pnpm gateway:interface-runtime preview \
  --workflow /absolute/private/workflow.json \
  --evidence /absolute/private/worker-evidence
pnpm gateway:interface-runtime prepare \
  --workflow /absolute/private/workflow.json \
  --evidence /absolute/private/worker-evidence \
  --workspace /absolute/private/runtime-descriptors \
  --confirm <reviewed-preview-sha256>
```

The installed CLI is `airalogy-interface-runtime`. Review the full private inventory before confirmation: Node executable, interface sources/package metadata, complete declared Node dependency trees and resolution targets, Chromium tree/internal links, exact workflow bytes/digest and evidence location. It hashes the selected software only, not workstation documents. Each tree is bounded to 20,000 entries/2 GiB, individual files to 512 MiB, and the descriptor to 2 MiB. Missing/extra/changed files, external links, group/world-writable runtime files, changed package resolution or changed workflow invalidate execution. Internal browser links remain within their selected tree. Runtime roots cannot exclude newly inserted `node_modules` code.

Preparation writes a private `runtime.json` and a small `config.json` containing its exact digest. Use **that config** as the existing installation binding's configuration. Changes to the workflow, source, dependencies, executable or browser need a fresh descriptor and normal binding/qualification/activation review; do not edit an active descriptor. Nothing is installed, enabled, registered or launched by preparation. These local source/runtime paths are private and nonportable. Reuse the adapter package on another host, but prepare and qualify that host's own runtime/configuration.

Before **each** child invocation, the installed SDK independently rehashes the descriptor, complete selected runtime trees, dependency resolutions and workflow. Hashing also observes cancellation/deadlines. This adds I/O overhead; a slow host can fail the bounded identity-probe deadline rather than skip checks. The worker rechecks selected workflow bytes and the existing backend rechecks application identity, initial conditions, states, parameter readback and final success. Node receives a fixed entry path and only fixed `probe`/`execute` requests; execute carries the exact Job UUID. No inherited Gateway/model credentials, `NODE_OPTIONS`, loader injection settings or shared browser profile are passed. System libraries, the kernel and programs running as the same service-account owner remain trusted: **this is integrity pinning, not a sandbox or authorization against hostile same-user code**.

## Source-included owned reference

The reference exposes only `interface.workflow.run@1.0.0` with empty arguments and a selected, literal workflow. It uses actual observed identity/initial values, not an invented operator-presence flag. It returns the Job UUID, workflow digest, numeric readback and explicit synthetic units/marker. It does not submit Records or promote scientific evidence.

```bash
adapter_output_dir=$(mktemp -d)
pnpm gateway:package build \
  --manifest apps/instrument-gateway/examples/interface-workflow/manifest.json \
  --factory interface_workflow:create_adapter \
  --file source/interface_workflow.py=apps/instrument-gateway/examples/interface-workflow/source/interface_workflow.py \
  --file tests/test_interface_workflow.py=apps/instrument-gateway/examples/interface-workflow/tests/test_interface_workflow.py \
  --file licenses/LICENSE.txt=LICENSE \
  --output "$adapter_output_dir/interface-workflow.zip"
```

Continue through [package testing, source review, inactive installation and qualified activation](./instrument-adapter-packages.md) using the independently prepared config. The published reference is **simulation-only and ineligible for real hardware activation**. Do not relabel it to bypass qualification. Tests exercise the production API policy using separate explicitly synthetic qualification fixtures in disposable databases; those rows are not deployable acceptance records.

For an owned local software check only, `node scripts/instrument-interface-worker-example.mjs` creates and exercises the bundled HTML and prepares a matching private runtime. It accepts no target/executable overrides and never calls a model or uses the foreground desktop. This automatic fixture confirmation must not be copied into a vendor deployment workflow.

## Failure, recovery and verification

The transport bounds requests to 8 KiB and stdout/stderr to 64 KiB each, drains pipes without blocking, refuses concurrency and repeated attempted Job IDs in one client, and has a 0.1–300 second caller deadline. The reference uses at most 20 seconds for execution; the managed identity probe retains its existing outer limit. Cancellation, timeout, malformed/cross-job responses or worker failure never trigger a retry. Local process-group termination is bounded, including a worker that exits while its child still holds pipes.

Killing Node/Chromium is **not a physical safe stop**. The reference deliberately raises from `safe_stop`: failed or uncertain operations must retain the Gateway stop/reconciliation lock. No receipt, process exit or closed window is converted into proof that a real instrument is safe. A production vendor adapter needs independently qualified stop/takeover behavior.

Tests cover source/dependency/browser drift, inserted modules (including previously absent earlier lookup paths and optional dependencies), resolution changes, non-inheritance of explicitly seeded test credentials/loader settings, malformed responses, cancellation, output limits, timeouts/child cleanup, independent installed-copy reuse, fixed tests inside a real network-disabled container, and actual API/database/installed-Python/Node/headless-browser execution. Lost-completion acceptance verifies one acquisition and no additional worker invocation during receipt recovery. These are software tests, not physical validation, paid-model quality evaluation, a cross-platform installer, vendor-native control or an operating-system sandbox.
