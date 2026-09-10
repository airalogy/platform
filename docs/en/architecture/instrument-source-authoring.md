# Local adapter source authoring

The local assistant can request actual Python source from the configured Aira model, assemble a source-included Adapter Package, run its **fixed** tests in the existing isolated Docker sandbox, and send bounded failure diagnostics back for another source proposal. It does not execute model code in Platform or on the host. It does not open instrument software, discover a workstation, install a driver, approve source, qualify equipment or activate commands.

This is one implementation slice of RFC #5, not completion of autonomous instrument onboarding. Separately authorized [bounded browser exploration](./instrument-interface-exploration.md), [scoped macOS discovery/observation and owned-simulator actions](./instrument-native-interface.md), and [documented HTTP reads](./instrument-http-interface.md) are available. Vendor-native/visual control, cross-platform operations and a real pilot remain pending. The first source author accepts read-only command drafts, pure Python and the trusted SDK/standard library only; no dependency download, native build, arbitrary tools or physical experiment is available to the model. Human-reviewed material, command contracts and independent tests are still required.

## Prepare selected inputs locally

Use a maintained POSIX test workstation and an existing physical, owner-only (`0700`) directory without symlink ancestors. Obtain and independently verify a Gateway SDK wheel and a preinstalled digest-pinned Python Docker image as described in [Adapter Packages](./instrument-adapter-packages.md). Keep this development workspace separate from Gateway runtime credentials and its journal. Windows credential/ACL setup is not yet supported.

For a **synthetic demonstration only**, generate a specification from a repository reference fixture, choosing a new absolute filename:

```bash
node scripts/instrument-authoring-example.mjs /absolute/private/synthetic-spec.json
```

Add `--http-reader` to select the documented HTTP reference with its independently fixed sample/schema tests. The model prompt describes the reusable SDK transport; it does not grant network authority. Choose the exact SDK wheel containing `HttpReadClient`. Neither reference generator contacts equipment or a model.

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

In **Lab → resource library → Instrument Gateways → select Gateway → Local adapter development**, an Owner/Manager with current `equipment.service` access imports `authorization.json`. Compare the full fingerprint with the local operator. Review the exact equipment, selected materials/source/tests/license, model-processing consent, sandbox SDK/image identities and limits; supply a reason, preview and confirm. The API rechecks current membership, Restricted equipment access and scope. Authorized equipment managers can read the private development history. No Gateway execution or installation token is accepted in place of the development token.

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
