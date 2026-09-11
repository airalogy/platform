# Reuse a reviewed interface workflow

A successful [bounded exploration](./instrument-interface-exploration.md) can now become a **private, fixed local workflow**. It retains the steps actually executed, exact initial control values/enabled state, the success checks selected **before** exploration, and source evidence digests. Subsequent runs use the same deterministic browser/native backend without calling Aira. This is an intermediate development artifact, **not an Adapter Package, Platform Workflow, Instrument Job or hardware qualification**.

## Record a person's browser demonstration {#browser-demonstration}

`gateway:demonstrate` (installed: `airalogy-interface-demonstration`) records actual browser input events in an explicitly selected, offline **owned simulation HTML** application. It does not execute an action menu on the person's behalf. Select the same reviewed definition and finite literal action/success policy used for exploration; `gateway:interface-example` can prepare an owned example without opening it. Unknown controls, parameter generalization, native applications, live URLs and visual desktop recording are not part of this recorder.

```bash
pnpm gateway:demonstrate preview --definition /absolute/private/definition.json --policy /absolute/private/policy.json
pnpm gateway:demonstrate record \
  --definition /absolute/private/definition.json --policy /absolute/private/policy.json \
  --confirm <reviewed-demonstration-preview-sha256> \
  --evidence /absolute/private/demonstrations --ack-visible-owned-simulation
```

Preview does not open software. It binds the exact source bytes, selected controls, allowed literal actions, privacy/success policy and **visible-window** choice. `record` additionally requires an interactive terminal and explicit acknowledgement, then opens a new isolated visible Chromium window, never an existing authenticated profile or the desktop. The normal network/download/dialog/frame gates remain; do not supply vendor-control HTML or rely on this development recorder as a physical safety boundary.

In that window, demonstrate only the reviewed operations. After editing a field, press **Tab** to commit it and wait for the terminal's recorded-step acknowledgement before the next operation. While the receipt is pending, further input is ignored, not queued for execution; an immediately following click may need to be made again after the acknowledgement. After the original success checks are satisfied, type **`finish`** in the terminal. Other input, EOF, Ctrl-C, a closed window or the session deadline ends the recording without promoting it. An unfinished field, ambiguous target, out-of-policy value, unrecorded state change, malformed event or changed final result prevents successful export. No automatic action, reset or relaunch follows a failure.

The recorder retains selected control readbacks and semantic click/fill steps, not raw keystrokes, pointer coordinates, clipboard contents or a desktop video. Existing explicit scope/masks and optional scoped observation screenshots still apply. Events are bounded to 256 KiB and the definition's step/time limits. It verifies the prior observation and independently rechecks current target/privacy/unique controls and the post-action state. This first recorder requires observable synchronous transitions and field commits; it does not infer asynchronous vendor completion or arbitrary keyboard/menu interactions. Application-provided text/events remain untrusted, and even a trusted browser input event is not proof of a person's identity.

Human actions are recorded **after observation**, with distinct `demonstration_action`/`demonstration_readback` events, not falsely presented as durable pre-execution agent intents. Successful export retains `source.kind: human_browser_events`; mismatched/mixed event origins are rejected. These owner-controlled files are not signed attestations, prior physical authorization or a guarantee that all application side effects were observed. Keep the evidence private under the same retention policy as other interface observations.

Use the returned `evidence` with the export commands below. No model, Platform development credential or paid service is required. Headless acceptance generates real browser input events, checks export and independent fixed replay, then verifies two separately installed copies and actual Instrument Job receipt-only recovery with the same adapter. It is automated synthetic evidence, **not actual human usability, a visible-terminal acceptance or a vendor-device test**; those still require separately authorized sessions/targets.

## Review and save

Use the `evidence` directory returned by a successful `gateway:explore run` or `gateway:demonstrate record`, not its parent containing `request.json`. Preparation reads historical evidence only; it does not open software, contact Platform or call a model, and works even if the original software is no longer present.

```bash
pnpm gateway:workflow prepare --evidence /absolute/private/completed-interface
pnpm gateway:workflow export \
  --evidence /absolute/private/completed-interface \
  --workspace /absolute/private/saved-workflows \
  --confirm <reviewed-export-preview-sha256>
```

Review the full private preview: target identity/paths, controls, literal steps, initial conditions, success checks, and lineage. Export rechecks evidence and rejects a stale digest before creating a fresh owner-only directory. It writes `preview.json` and `workflow.json` without modifying the source evidence. The installed command is `airalogy-interface-workflow` with identical arguments.

Only complete, closed, successful traces are accepted. Checks include consecutive event hashes, matching session/preview identity, action membership in the approved policy, observed preconditions, exactly matched intent/result pairs (or separate human action/readback pairs), parameter readback, and the predeclared success checks. Missing results, stopped/budget-exhausted sessions, unsupported events, or unrecorded state/value changes are not converted into reusable steps. A model or person saying “finished” is insufficient. The exporter neither invents missing actions nor turns literal values into unreviewed parameters or branches.

The artifact contains local paths, approved literal values and selected initial readbacks: **keep it private**. It does not copy credentials, model turns, screenshots, accessibility trees or source HTML. The exporter reads only the preview and numbered events; at most 1,024 directory entries, 256 events, 512 KiB per selected file and 16 MiB total. POSIX directories/files must be owner-only; selected links and multiply linked files are refused. Hashes detect inconsistencies, not malicious replacement by the owning user, and are not signed hardware attestations.

## Preview a new fixed run

```bash
pnpm gateway:workflow preview --workflow /absolute/private/saved/workflow.json
pnpm gateway:workflow run \
  --workflow /absolute/private/saved/workflow.json \
  --confirm <reviewed-run-preview-sha256> \
  --evidence /absolute/private/new-run-evidence \
  --ack-new-run
```

Run preview revalidates the current runtime and selected target bytes/build through the existing backend; it has a **different digest** from export approval. Review it before acknowledging a **new operation**, never use it as recovery for an uncertain earlier operation. Each run records its workflow/lineage and before/after observations separately. No model or Platform credential is needed for fixed development replay; AI off or a disconnected model does not prevent it.

After opening/observing the selected target, all initial values, enabled flags and state must match. Each step still checks fresh observations, unique controls, state transition and parameter readback. A fresh final observation must satisfy the saved success checks. Failure stops the flow; no automatic retry, reset, relaunch or physical safe-stop claim is made. Closing a browser is not stopping equipment. Existing application-startup risks remain: even loading a page can initialize hardware, so review independently before any new run.

Browser actions remain limited to selected hash-pinned simulation HTML; live URLs remain observation-only. Native exports retain exact bundle/process/build pins. Replay still requires the original build-sealed owned simulator and initial state; it never opens, resets or retargets a native application. A restarted app has a different process identity and needs a new selection/review. Export does not promote native surveys to action authority, remove the owned-simulator restriction, or provide Windows/visual control.

## Verification and next integration boundary

The [pinned local process bridge](./instrument-interface-worker.md) now connects a reviewed installed Python adapter to this browser workflow backend through existing Instrument Job execution and receipt recovery. It does not promote this workflow artifact to hardware authority; the included reference remains simulation-only, and native/visual production execution still requires its own qualified backend.

Tests cover offline export, chain/semantic failures, private-file limits, stale approval, native pin preservation, real headless replay, changed initial values, and a wrong final result despite a matching state label. Real API/disposable-database acceptance completes authorization → exploration → saved workflow → independent CLI replay, with a synthetic provider and owned HTML. The replay consumes **no additional model calls**. Native historical export is tested without foreground access; real vendor/hardware execution is not established.

This does not install or activate anything, submit a Record, publish Knowledge, or make a workflow publicly visible. Editing the definition, steps, initial conditions or checks creates a different digest requiring new review; digest recomputation alone is not qualification. Production reuse still needs a reviewed versioned adapter, installation and target qualification, and an Instrument Job governed by permissions, booking, local confirmation, leases, stop/reconciliation and data-delivery rules. Native demonstration recording, automatic parameter generalization, qualified vendor GUI execution, supported-OS acceptance and a named real pilot remain open.
