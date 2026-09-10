# Instrument Interface

Local, bounded Chromium observation and supervised **synthetic HTML** replay for instrument-adapter development. This is a development tool, not a remote equipment controller or hardware qualification.

`pnpm gateway:native` (installed: `airalogy-interface-native`) adds **read-only macOS Accessibility surveys** for explicitly selected, already-running applications. Build/doctor/prepare never open vendor software; capture pins bundle integrity, process lifetime and one exact window, omits passwords/private regions and defaults to no input values. Reuse `gateway:survey run/assemble` and the Platform Aira review panel, then separately preview/confirm a native read definition. An independent `simulation-template` → `preview` → `run --ack-new-run` path supports reviewed fill/press only on the exact owned simulator sealed into that build; survey definitions cannot acquire action authority. No vendor UI writes, automatic app discovery, screenshot or visual fallback. Windows/Linux native support remains pending.

Selected application startup is separate: `inspect` reads metadata/current matching instances; `prepare-launch` writes a private, expiring preview; `launch --request ... --confirm ... --ack-initialization` uses a single-use durable intent, fixed LaunchServices configuration and verified returned process identity. Launching real software may initialize equipment or network/background activity and is **not sandboxed**; obtain independent local authority and review first. No arbitrary arguments, scripts, app substitution, forced extra instance or automatic retry. `launch-status` reads saved receipts offline without opening or stopping anything; use `inspect` for current metadata. Startup does not authorize UI actions or qualify hardware. See the bilingual **Native macOS interface observation** guide for exact commands, risks and owned-simulator acceptance.

`pnpm gateway:survey` (installed: `airalogy-interface-survey`) adds `prepare`, digest-confirmed single-use `run`, and `assemble` for a selected application with no handwritten control/state map. It discovers bounded, browser-verified semantic control hints, defaults to no input values or screenshots, and produces an editable **read-only** definition after review. Follow the bilingual **Selected-application interface survey** guide. No model is called by this local flow; survey evidence is not hardware attestation or action approval.

- Dedicated nonpersistent browser; never attaches to an existing browser/profile.
- Explicit file-byte/target/plan/engine digest confirmation before launch.
- Exact accessible roles/names or test IDs, unique visible controls, known states and readback.
- Live HTTP(S) targets are **observation-only**. No clicks/fills, authentication profiles, redirects, arbitrary JS/selector commands, uploads, downloads, sockets or embedded frames.
- Local HTML runs from its selected bytes in an `about:blank` document, without file-origin access or authorized network requests. Only reviewed simulation/training HTML belongs here.
- Private, exclusive evidence files with event hashes, before/after observations and opt-in scoped screenshots. The manual CLI makes no model calls or uploads; optional Aira exploration requires separate Platform consent/grant and local policy confirmation.
- No automatic retries or restart replay. Closing Chromium does not establish a physical safe stop.

Source checkout, Node 22+, POSIX owner-only evidence directory, installed workspace dependencies and matching Chromium:

```bash
pnpm exec playwright install chromium
pnpm gateway:interface-example
```

The example command prints absolute `definition`, `plan` and `evidence` paths for a temporary synthetic fixture. Substitute those paths below:

```bash
pnpm gateway:interface preview --definition /absolute/definition.json --plan /absolute/plan.json
pnpm gateway:interface run --definition /absolute/definition.json --plan /absolute/plan.json --confirm <reviewed-sha256> --evidence /private/owner-only-directory --ack-new-run
```

Preview emits **private** JSON and never opens an application. Review the selected code/application, source, version identity, network rules, masks, limits and exact steps. Opening software or even a GET request can initialize equipment: obtain independent local authorization first. Do not point this tool at production hardware to bypass Platform permissions, bookings, leases or approvals.

Omit `--plan` for observation only. Successful run prints its evidence directory and session ID; failed runs exit nonzero. Read `stopped`/`closed` events before deciding what happened. A new run is a new operation, not a recovery mechanism; reconcile uncertainty with the operator first. Evidence is not an attestation: its owning user can replace it.

For manual library use, call `previewInterface`, then `BrowserInterfaceSession.open({ definition, plan, confirmation, evidenceRoot })`, `session.step(digest(session.lastObservation))`, and `session.close()` in `finally`. The manual backend accepts the next **already confirmed** step only. Optional exploration uses a separately confirmed finite policy; a model may choose only an approved action index, never new controls/values/code. Treat the imported module and session object as trusted local code, not an RPC security boundary.

`pnpm gateway:explore` (installed: `airalogy-interface-exploration`) provides `prepare`, `run REQUEST --confirm LOCAL_DIGEST`, and `sync REQUEST`. Follow the bilingual **Bounded Aira interface exploration** guide in `docs`: import only the generated `authorization.json` into Platform, never the credential-bearing `request.json`. The grant fixes target scope, actions, selected model data and at most five calls. Reports are client evidence, not hardware qualification. No auto relaunch: `sync` sends existing reports without opening a browser or calling a model. The Node-authored JSON Schema is shared with API validation and checked by `pnpm gateway:contract:check`.

`pnpm gateway:gui-demo` exercises the same backend with only the bundled synthetic app and independently verifies its exported `airalogy.gui-rehearsal.v1` bundle. It accepts no target arguments. `pnpm gateway:interface-test` runs contract, actual browser, private-evidence and independent-process CLI tests. The package can be packed from its directory; install its pinned Playwright Chromium on the selected host.

For Aira exploration on the owned macOS simulator, use the `definition_file` and `policy_file` returned by `gateway:native simulation-template` with `gateway:explore prepare`. The existing Platform review, local digest confirmation, finite action indexes and report-only recovery apply. Native scope is explicitly `native_macos_simulation`; source/build/process/focus checks remain local, and neither a remote grant nor a read-only survey promotes vendor software into an action target. No app is opened or closed by the native exploration runner.

See the repository's bilingual **Browser interface backend** guide for the precise browser contract and privacy/network limits. Windows private-file ACL, vendor-native writes and visual/production GUI control are not implemented; synthetic CI does not qualify an instrument.
