# Local adapter source authoring

The local assistant can request actual Python source from the configured Aira model, assemble a source-included Adapter Package, run its **fixed** tests in the existing isolated Docker sandbox, and send bounded failure diagnostics back for another source proposal. It does not execute model code in Platform or on the host. It does not open instrument software, discover a workstation, install a driver, approve source, qualify equipment or activate commands.

This is one implementation slice of RFC #5, not completion of autonomous instrument onboarding. Separately authorized [bounded browser exploration](./instrument-interface-exploration.md), [scoped macOS discovery/observation and owned-simulator actions](./instrument-native-interface.md), and [documented HTTP reads](./instrument-http-interface.md) are available. Vendor-native/visual control, cross-platform operations and a real pilot remain pending. Source development supports fixed read-only and low/medium/high-risk command contracts; non-read-only source requires separate explicit development consent. Only pure Python and the trusted SDK/standard library are available: no dependency download, native build, arbitrary tools or physical experiment. Human-reviewed material, command contracts and independent tests are still required.

## Local browser development guide

The installed SDK provides a loopback guide for preparation, approval handoff, bounded execution, cooperative pause and draft download:

```bash
airalogy-instrument-authoring serve --workspace /absolute/private/development
```

From a source checkout use `pnpm gateway:author serve --workspace /absolute/private/development`. Select an existing owner-only `0700` POSIX directory **separate from the Gateway service directory**. A directory containing `gateway.json` or the runtime `state.json` is refused. This does not isolate malicious programs running under the same OS account; use dedicated least-privilege accounts and a maintained isolated test host. The guide reuses the [authenticated local setup server](./instrument-integration.md#local-browser-setup), its one-hour private address, Host/Origin checks and no-remote-assets policy. Nothing opens or runs automatically. Windows installation and native dependencies remain unsupported.

1. Select the reviewed specification described below and independently trusted SDK wheel. Input copies remain local, private and bounded (spec 128 KiB, SDK 64 MiB, retained copies 64 files / 256 MiB). Enter the exact Platform/Gateway/equipment, preinstalled digest-pinned Docker image and call/time limits. Preview displays the fixed material/contracts/tests and destination without a network/model call or credential creation. Five-minute single-use confirmation rechecks the selected bytes before saving a separate authoring credential and request.
2. Download the **PRIVATE authorization** and import it in Platform → Instrument Gateways → Prepare adapter → Develop source. This file includes private selected material, not a bearer credential. Compare the full fingerprint and independently approve material processing and limits. Never upload `request.json`; model processing may be external. The browser guide cannot approve its own grant.
3. Return to **Check approval and preview run**. Review the exact current request and confirm. The existing authoring coordinator performs source generation, fixed tests and receipt recovery in a background local thread, under the same exclusive development lock as the CLI. Polling reads only local state; it cannot call a model or start another run. Reload restores saved sessions without executing anything. Existing sessions default to the resume area rather than a full new-input form.
4. **Pause local development** requests a stop between bounded steps; the current model/test step and its receipt may finish first. It does not revoke Platform authorization or stop an instrument. Closing a browser tab is not a pause. Ctrl-C closes the guide and requests pause, but process termination can leave an interrupted test or uncertain network receipt. On restart, run tickets are history, not evidence a process stopped. Resume the same request; the shared lock blocks an existing CLI/guide runner. Do not remove its journal to bypass it.
5. Interrupted disposable tests require a separate reconciliation choice, preview and confirmation listing their exact container identities. Only those previewed tests may be reconciled; a newly uncertain test requires a fresh preview. Reconciliation records interruption as failure, never as a passing test. Existing physical jobs are not affected.
6. Inspect retained inputs, local run outcomes and candidate reports. Only locally passing, digest-checked draft ZIPs are offered for download; failed candidates retain inspectable reports. Downloads recheck candidate/report/archive identity and cannot select arbitrary files or private credential files. These are client-reported results, not hardware qualification or trusted execution attestations. Review source, dependencies, confidentiality and licenses before importing the draft in Platform and handing it to the separate installation guide.

Saved sessions and run outcomes remain ordinary private files, not chat or browser storage. Session enumeration is bounded to 100 sessions and 1,000 directory entries; artifacts/history are bounded to 1,000 entries per session. Copies and reports are not deleted automatically. Preserve referenced files until review and retention requirements are satisfied. Unknown/failed operation details are redacted in the browser; inspect the original CLI workflow for advanced diagnosis. The guide does not invent device semantics, independent expected results, manuals or operating permissions, and does not replace the real pilot.

Browser/API/database acceptance uses an owned synthetic specification with injected external model and sandbox outcomes; separate actual container tests exercise incorrect/corrected source against fixed tests. Neither is evidence of a successful paid model or real-device deployment.

## Prepare selected inputs locally

Use a maintained POSIX test workstation and an existing physical, owner-only (`0700`) directory without symlink ancestors. Obtain and independently verify a Gateway SDK wheel and a preinstalled digest-pinned Python Docker image as described in [Adapter Packages](./instrument-adapter-packages.md). Keep this development workspace separate from Gateway runtime credentials and its journal. Windows credential/ACL setup is not yet supported.

For a **synthetic demonstration only**, generate a specification from a repository reference fixture, choosing a new absolute filename:

```bash
node scripts/instrument-authoring-example.mjs /absolute/private/synthetic-spec.json
```

Add `--http-reader` to select the documented HTTP reference with its independently fixed sample/schema tests. The model prompt describes the reusable SDK transport; it does not grant network authority. Choose the exact SDK wheel containing `HttpReadClient`. Neither reference generator contacts equipment or a model.

Alternatively add `--export-reader` for the [completed-file collector](./instrument-export-interface.md), its public completion contract and independent synthetic file tests. Use the exact SDK wheel containing `ExportReadClient`. This does not authorize access to real export folders or create a vendor completion bridge; the hand-written source-included package is also available without AI.

### Controlled-command source drafts

The same source-only workflow can draft low/medium/high-risk command implementations without authorizing their execution. The package's fixed risk, local confirmation, interlocks, completion and stopping requirements still pass the shared package validator. Medium/high risk cannot omit local confirmation, and high risk cannot omit operator presence or emergency-stop requirements. Aira cannot lower those requirements or rewrite the independent tests. These are declared requirements, not an AI safety classification or proof that a generated implementation satisfies them.

Before authorization, Platform displays the exact command/version, declared risk, effects, completion, stopping and local safety contract. For any non-read-only command, both preview and confirmation require the strict boolean `controlled_source_consent: true`, independently of model-processing consent. Changing inputs clears UI confirmations and invalidates the preview; the server enforces this independently. Authorization audit records the consent and command review. Existing read-only requests do not require the new consent or receive broader command authority; their immutable specifications remain fixed. History and the local preparation/run previews retain the same source-only distinction. No migration or execution credential is introduced.

To exercise the owned stateful reference with fixed independent fake-transport tests:

```bash
node scripts/instrument-authoring-example.mjs /absolute/private/controlled-spec.json --controlled-reader
```

Use a newly verified SDK build containing this support and the corresponding API/web deployment. The reference package lives in `examples/controlled-reader`, with `controlled_reader:create_adapter` as its factory. It is also available for manual package building without AI. It configures an in-memory controller, reads parameters back, starts once, observes completion and checks result units/count. Its tests vary the result independently, simulate ownership changes, cancellation, lost start responses and failed stop confirmation. The controller has no production configuration or transport; a fresh controller represents one simulation acquisition and no physical reset/restart command is provided. Its immutable output contract always says `simulation_only: true`, so it cannot qualify for real-equipment activation.

Actual Docker acceptance first rejects a deliberately duplicated start, then accepts corrected source against unchanged tests and resumes the same receipt without rerunning the candidate. API/local-browser tests separately use injected model/test outcomes to verify consent, audit, bounded repair, cancellation and credentials that cannot access runtime commands. These are software tests, not a paid-model benchmark or vendor safety acceptance.

Real controlled implementations require independently documented parameter readback, completion, takeover and device-specific stopping, plus independent test cases. Missing semantics must produce `missing_information`, not invented endpoints, no-op stopping or a simulation relabelled as hardware. A tested draft still needs independent source approval, exact installation, non-simulation qualification covering the controlled commands, activation, bookings and local startup/operation requirements. This change does not authorize a model or development process to contact live equipment.

A real specification is a JSON object with exactly `goal`, `manifest`, `factory`, `materials`, `tests`, `licenses`, and `initial_sources`. The manifest is an unbuilt Adapter Package template (`files: []`, `provenance.kind: "aira"`, no claimed tested hardware). `factory` is a fixed Python `module:function`. Materials are 1–16 explicitly selected `{name, text}` items, named without local directory paths; tests/licenses/initial sources are maps from portable `tests/*.py`, `licenses/*`, `source/*.py` paths to text. Initial sources may be empty. The context is limited to 128 KiB. PDF/OCR, directory collection and software discovery are not performed here; provide an explicitly reviewed text extract when permitted.

No secret detector is comprehensive. Review confidential information, personal data and redistribution/model-processing rights before preparing a request. Known Platform credential patterns are rejected, but this is not a guarantee that all secrets have been removed.

Selected text observations from the separately confirmed [browser interface backend](./instrument-browser-interface.md) can be reviewed locally and added to `materials`. This is a manual, explicit transfer; the source author does not gain browser control and no UI capture is automatically sent to the model.

```bash
pnpm gateway:author prepare \
  --workspace /absolute/private/development \
  --platform-url https://lab.example.edu/api \
  --gateway-id <Gateway-UUID> --resource-id <equipment-Resource-UUID> \
  --spec /absolute/private/selected-spec.json \
  --sdk-wheel /absolute/path/to/airalogy_instrument_gateway-0.1.0-py3-none-any.whl \
  --trusted-sdk-digest <independently-verified-SDK-SHA256> \
  --image <trusted-image-repository>@sha256:<image-SHA256> \
  --max-iterations 3 --duration-seconds 900 --timeout-seconds 60
```

The command performs no network request. It snapshots selected text, generates a separate `aiauthor_` credential, and creates a new session directory with private `0600` files. `request.json` contains the local credential and SDK path: **never paste it into Platform, chat or an issue**. `authorization.json` contains no bearer credential, but includes private selected Lab material. It is **not a public document**. The command prints filenames and the fingerprint, not the secret or selected text. The installed SDK exposes `airalogy-instrument-authoring` and `python -m airalogy_instrument_gateway.authoring_cli`.

## Authorize, then run

In **Lab → resource library → Instrument Gateways → select Gateway → Prepare adapter → Develop source**, an Owner/Manager with current `equipment.service` access imports `authorization.json`. Compare the full fingerprint with the local operator. Review the exact equipment, selected materials/source/tests/license, model-processing consent, sandbox SDK/image identities and limits; supply a reason, preview and confirm. The API rechecks current membership, Restricted equipment access and scope. Authorized equipment managers can read the private development history. No Gateway execution or installation token is accepted in place of the development token.

Authorizations allow 1–5 model calls, expire within 30 minutes, and fix the configured model and Gateway/equipment revision. Each response is limited to 60 seconds and 64 KiB; a local test is limited to 1–120 seconds. Existing model usage context records the operation identity. These are call/time/output bounds, **not a guaranteed monetary ceiling**. Configured model processing may be external. Aira disabled/unavailable leaves manual package creation, tests, import and governance available.

```bash
airalogy-instrument-authoring run /absolute/private/development/<session-UUID>/request.json
airalogy-instrument-authoring status /absolute/private/development/<session-UUID>/request.json
```

The assistant holds an exclusive development lock. Before each generation the API durably reserves a unique attempt, so a lost response does not create another paid call. Proposals contain only a complete `source/*.py` map, summary, assumptions and missing-information questions. Fixed tests, manifest, factory, licenses, command schemas and safety effects cannot be changed by a proposal. A changed specification requires a new request and authorization. Untrusted manual text or test output cannot authorize tools or change the execution boundary. Code is not made trustworthy by this structural validation.

The local builder never imports source. It makes an actual immutable ZIP/wheel and runs only the selected fixed tests in the existing non-root, no-network, no-host/device-mount, resource-bounded sandbox. Failed tests can produce another proposal within the original grant; incomplete device semantics stop with questions instead of a fabricated driver success. The SDK/image must match the pinned identities. Local API traffic requires HTTPS outside loopback, rejects redirects and bounds responses.

## Results and recovery

Each attempt retains private proposal JSON, ZIP if buildable, and test receipt. Platform stores private source proposals, model operation IDs and matching client-reported diagnostics; the UI shows history and cancellation in English/Chinese. A successful fixed test returns `draft_tested`, the ZIP/report paths and the next review step. It is **not source approval, trusted execution attestation or hardware qualification**: a local client can falsify a report, and generated source can be dishonest or inadequately tested. Independent review and the existing [import/install/qualification/activation workflow](./instrument-adapter-packages.md) are still required. The final package is an ordinary editable/versioned draft, not a state hidden in chat.

Resume the **same** request after a lost network response. Saved artifacts are checked rather than overwritten; completed tests are not repeated simply to resend a receipt. If local testing was interrupted without a durable report, the assistant stops with the exact journaled container identity. After reviewing that interruption, `run ... --reconcile-test` stops only that session's named disposable test and verifies its absence. An unconfirmed termination stops the workflow. Confirmed interruption is recorded as a failure, never a pass, before another iteration. This is not a physical instrument stop operation.

Cancellation blocks new calls and late model output. It does not delete retained material, terminate an already running local sandbox or stop an instrument. Existing saved test receipts may reconcile after expiry/cancellation, subject to current scope and exact credentials. An expired/stale grant cannot start a new model attempt. Review local retained files according to Lab policy; there is no automatic deletion/retention policy in this slice.

Migration `0055_instrument_authoring` adds separate development sessions/attempts. Apply through normal backed-up deployment; acceptance uses disposable data only. Downgrade drops development records, not local files, installed software or physical actions. Synthetic API/provider-stream fixtures validate transactions and failure recovery; the actual Docker acceptance validates a deliberately incorrect source followed by a corrected source against unchanged tests. No paid model or real equipment has been qualified by those tests.
