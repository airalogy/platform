# Bounded Aira interface exploration

This adds adaptive **selection among previously reviewed actions** to the [browser interface backend](./instrument-browser-interface.md) and [owned macOS simulator backend](./instrument-native-interface.md). The local operator selects the application, semantic controls, observable states, literal actions and success checks first. Aira receives selected textual readbacks and chooses one action index, asks for missing information or proposes completion. The local runner independently checks every choice and the resulting state. It does not discover arbitrary software or invent new controls, parameter values, URLs or code.

This is development evidence, **not production equipment control or qualification**. Fill/press supports isolated reviewed simulation HTML and the exact build-sealed owned AppKit simulator (`native_macos_simulation`). Live URLs remain observation-only; loading a page/GET can still initialize equipment, so independent local authorization is required. No authenticated browser, vendor-native control, screenshot interpretation or real instrument has been qualified. Linux/macOS are the supported private-file runtime environments; Windows ACL support remains pending.

## Prepare the local policy

Install the pinned Node/Chromium runtime described in the browser guide. `pnpm gateway:interface-example` creates private example `definition`, `plan`, `policy` and `evidence` paths without launching a browser. The policy is an explicit finite menu, not a predetermined execution sequence:

```json
{
  "goal": "Read two synthetic samples",
  "actions": [
    {
      "operation": "fill",
      "control_id": "sample.count",
      "value": "2",
      "before": "ready",
      "after": "ready"
    },
    {
      "operation": "click",
      "control_id": "measurement.start",
      "before": "ready",
      "after": "completed"
    }
  ],
  "success": [{ "control_id": "result.value", "equals": "0.84" }]
}
```

Use the generated policy with its matching definition; control/state IDs must agree. Review the selected HTML source and every action, including read operations. Aira can repeat an approved action within the step/call limits; approving a menu is not approving each action exactly once. Do not put credentials or production actions in a policy.

For native simulation, first use `gateway:native build`, explicitly open **only the returned owned simulator**, and run `gateway:native simulation-template` with its actual PID as documented in the native guide. Pass its returned `definition_file` and `policy_file` below. The native runner never launches or focuses software; keep the selected simulator window focused during execution. It independently verifies the sealed build, process lifetime, window and every AX action. Neither changing the grant's target kind nor a same-name application bypasses those local gates. Survey-generated `airalogy.native-read-definition.v1` files cannot be used as exploration action definitions.

```bash
pnpm gateway:explore prepare \
  --definition /absolute/definition.json --policy /absolute/policy.json \
  --workspace /absolute/private/exploration \
  --platform-url https://lab.example.edu/api \
  --gateway-id <Gateway-UUID> --resource-id <equipment-Resource-UUID> \
  --max-iterations 5 --duration-seconds 600
```

Preparation makes no network request and launches no application. It creates a new owner-only directory with:

- `preview.json`: the exact local application/action policy, digest and runtime versions.
- `authorization.json`: the request to import into Platform; no bearer credential or source path/HTML, but it contains **private selected Lab material**, including literal values.
- `request.json`: local credential, selected definition/policy and Platform endpoint. **Never upload this file or paste it into chat/issues.**

The printed fingerprint identifies the authorization request; the separate `local_preview_digest` identifies the exact local launch policy. Review both, rather than copying an unreviewed digest. Relative or credential/query-bearing API URLs are rejected; HTTPS is required outside loopback.

## Authorize and run

In **Lab → resource library → Instrument Gateways → select Gateway → Aira interface exploration**, import `authorization.json`. An Owner/Manager with current `equipment.service` permission must review the fingerprint, all allowed actions and success checks, and consent to configured-model processing. Supply a reason, preview, then confirm. The local operator separately confirms the local preview:

```bash
pnpm gateway:explore run /absolute/private/session/request.json --confirm <local-preview-digest>
pnpm gateway:explore sync /absolute/private/session/request.json
```

The installed package exposes `airalogy-interface-exploration` with the same arguments. The grant allows 1–5 model calls and 30–900 seconds. The selected interface definition has its own duration/step/observation limits; neither can extend the other. Each model response is bounded to 60 seconds and 16 KiB. These are call/time/output bounds, not a guaranteed financial ceiling.

Each call is reserved durably before contacting Aira; duplicate turn IDs must carry identical inputs. The server pins Gateway/equipment revisions, actor, model and model transport configuration. It rechecks authorization after generation; cancelled/expired/stale requests cannot accept late proposals or start another call. Current scope still applies to history and receipt recovery. Source-authoring (`aiauthor_`), interface development (`aiinterface_`) and installation/Gateway credentials are purpose-separated and cannot be substituted.

Only selected control labels/readbacks, approved actions, prior proposals and bounded results reach the configured model, which may be external. Raw screenshots, accessibility trees, HTML and local paths are not automatically sent. Review confidentiality and model-processing rights; this is not an automatic secret detector. Suggestions and displayed software text remain untrusted data, not permission to execute additional tools.

Before executing even a finish proposal, the local runner re-observes the app and rejects changed state. Fill checks the exact value; click checks the resulting state. Success requires the independently configured checks, not just the model saying “done.” All observations/proposals/action receipts stay in private immutable files and private Platform history; client reports are not trusted hardware attestations.

## Stops and recovery

Cancellation prevents subsequent calls/actions after the next authorization check; it does not atomically interrupt an operation or establish a safe physical stop. Unknown state, ambiguous controls, stale observations, out-of-policy proposals, network errors or exhausted bounds stop development. AI unavailable/disabled leaves manual observation/plans, package creation and existing governance usable.

The retained exclusive `run.started` marker deliberately forbids relaunching the same request, even when no result reached Platform. Intent files and the marker flush both file contents and containing-directory entries before proceeding; a flush failure stops execution. This does not establish storage-hardware or power-loss certification. Never remove the marker to retry an uncertain action. `sync` resends only existing immutable action receipts; it opens no browser, calls no model and cannot invent a missing receipt. Review unfinished model calls, local evidence and any uncertain operation with the operator; a new run requires a fresh preparation and authorization. Locally saved reports can synchronize after cancellation/expiry when current scope and credentials still permit access.

The result distinguishes `client_reported_success`, `needs_information` and `budget_exhausted`; the Platform history marks the grant closed/cancelled. None of these imports, approves, installs or activates an adapter. Reviewed observations can be explicitly transferred to the separate [source authoring workflow](./instrument-source-authoring.md); no automatic publication or file sharing occurs.

## Deployment and acceptance

Migration `0056_instrument_exploration` adds a purpose discriminator (existing sessions default to `source`) and immutable turn inputs to the development tables. Deploy API and local runtime together through the normal backed-up release workflow. Downgrade deletes interface-development sessions/turns before removing the discriminator, so an older source-only server cannot reuse their authority; it preserves source sessions and never undoes local actions/files.

`gateway:contract:check` verifies the shared Node-authored JSON Schema copied to the API; golden requests test matching canonical fingerprints. `gateway:interface-test` uses actual Chromium with synthetic model choices. `research:integration` additionally runs the real API, disposable PostgreSQL and independently launched Node/Chromium together; only the model stream is synthetic. UI tests check confirmation, private-file rejection, escaped output, history/cancel and AI-off behavior using explicit UI response fixtures. No paid-model quality, vendor software or physical-device acceptance is implied.

On an already authorized macOS graphical host, `RUN_INTERFACE_NATIVE_TESTS=1 pnpm research:integration -k interface_exploration` also exercises the owned AppKit simulator through actual AX fill/press, three model turns, saved API history, independent CLI result verification and report-only sync. Native tests cover AI-off, cancellation, out-of-policy proposals and lost receipts without replay. UI fixtures cover both transports in English/Chinese at narrow width. No paid-model quality, vendor software or physical-device acceptance is implied.

Open work includes discovery/authorized launch of unknown applications, qualified vendor-native and visual Computer Use, reviewed GUI adapters in managed production execution, supported-OS operations and a named real pilot with a responsible operator. Owned-simulator exploration does not complete these parts of the full instrument-integration objective.
