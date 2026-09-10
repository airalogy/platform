# Native macOS interface observation

This is a **development backend**, not a production instrument controller. Surveys and assembled read definitions remain read-only for explicitly selected, already-running applications. A separate action definition permits bounded fill/press operations on **this build's owned simulator only**, not vendor software. It does not discover applications, launch vendor software, steal focus, use coordinates, execute scripts, capture screenshots or change system permissions. Windows/Linux native and visual backends remain separate work.

## Prepare, review, capture

On macOS 13 or newer, use Node 22+, the installed workspace dependencies and Apple's Swift command-line toolchain. Build the bundled trusted helper into a new owner-only workspace:

```bash
pnpm gateway:native build --workspace /absolute/private/native-builds
pnpm gateway:native doctor --build /absolute/private/native-builds/interface-ID/native-build.json
```

Use the actual `build_file` returned by the build. It also builds an owned, ad-hoc-signed AppKit **simulation-only** reader; nothing is opened. The build manifest pins source/helper bytes and architecture. This is integrity under the trusted local operator account, not signed distribution, vendor trust, notarization, sandboxing against a malicious host or equipment qualification.

`doctor` reports existing Accessibility authorization without prompting or changing it. If authorization is absent, the operator must decide separately whether to grant it through normal system settings. There is no alternate bypass. The implementation uses Apple's [Accessibility authorization](https://developer.apple.com/documentation/applicationservices/1459186-axisprocesstrustedwithoptions) and [bounded AX messaging](https://developer.apple.com/documentation/applicationservices/1459345-axuielementsetmessagingtimeout) interfaces; the timeout affects this helper process, not global permissions.

Select the **POSIX-canonical absolute** `.app` path, its current same-user PID and exact window title. Opening any vendor application may initialize equipment; this tool neither opens it nor authorizes that initialization. Obtain local authorization first. Prepare a private JSON array of exact AX identifiers for regions to omit, if applicable:

```bash
pnpm gateway:native prepare --build /absolute/private/native-builds/interface-ID/native-build.json --bundle /Applications/SelectedInstrument.app --pid 12345 --title 'Exact selected window' --redact /absolute/private/masks.json --workspace /absolute/private/surveys
pnpm gateway:survey run /absolute/private/surveys/interface-ID/request.json --confirm REVIEWED_LOCAL_DIGEST
```

Preparation reads application metadata, not UI content. Review the private preview before `run`. The capture pins bundle identifier/version, code-directory integrity, executable/Info.plist hashes and process UID/start time, preventing PID reuse or app replacement from silently retargeting it. The public report includes only the declared application identity and observed control hints, not local paths/PIDs/build manifests.

Capture requires exactly one non-minimized AX window with the selected title and role. Extra windows, dialogs, missing/ambiguous private masks, invalid geometry, target drift or unreadable attributes stop the run. A survey request retains `run.started` before observation and cannot be replayed. Refusal events retain a fixed reason code, not OS error bodies. Inspect the selected application's state and reconcile with the operator before preparing a new request; never delete the marker as recovery. Transient or inconsistent OS accessibility trees are refusals too, not a reason to accept another window or change permissions.

## Privacy and bounded semantics

- At most 200 AX nodes, depth 16 and 64 candidate controls; unsupported or oversized trees are refused.
- Inputs are not read by default. `--capture-values` is a separate whole-window capture consent; the preview retains that choice. Secure text fields and explicitly masked regions remain omitted.
- Private descendants and ancestor metadata are suppressed. Missing private identifiers stop capture instead of silently removing protection. Application-provided labels/static text can still contain sensitive data: review `survey.json` before processing it with any model.
- Only supported roles with an exactly unique AX identifier become addressable. Ambiguous/identifier-less controls are advisory only. No role/name guessing or index/coordinate fallback.
- Input titles/descriptions are not read because applications can mirror values in them. Only static text and explicitly consented text-field/text-area values have readbacks in this version.
- Each AX call has a two-second IPC timeout; the parent bounds the complete helper capture to 30 seconds and 128 KiB. Failure terminates only the helper, never the selected application or physical operation.
- Geometry, labels and readbacks are application-reported, not pixel visibility, atomic snapshots, physical readiness or scientific success evidence.

## Review and reuse

The report uses the same [survey/Aira review](./instrument-interface-survey.md) API and bilingual Platform panel as the browser backend. Import **only `survey.json`**, never `request.json`, native paths or build files. Aira may interpret the snapshot and suggest `native_accessibility`, but cannot grant native actions. Manual review/assembly works with AI disabled.

```bash
pnpm gateway:survey assemble /absolute/private/surveys/interface-ID/request.json --analysis /absolute/private/reviewed-analysis.json --workspace /absolute/private/drafts
pnpm gateway:native preview --definition /absolute/private/drafts/interface-ID/definition.json
pnpm gateway:native read --definition /absolute/private/drafts/interface-ID/definition.json --confirm REVIEWED_READ_DIGEST --evidence /absolute/private/reads --ack-new-read
```

Assembly verifies the retained capture/analysis digests and creates a fresh editable `airalogy.native-read-definition.v1`, copied evidence and empty plan. It does **not** require the original application to remain open. Execution does require its pinned process and identity anchor to match, and selects only the reviewed readbacks. After restarting/upgrading software, explicitly prepare a new selection and review its identity before reusing mappings; old process pins never silently attach to a replacement. Definitions cannot add click/fill or input-value consent.

## Separately reviewed owned-simulator actions

After explicitly opening the returned `simulator_app` in an authorized graphical session, select its actual PID. The following preparation reads metadata only and writes editable definition, plan and policy files; it does not open or operate the app:

```bash
pnpm gateway:native simulation-template --build /absolute/private/native-builds/interface-ID/native-build.json --pid 12345 --workspace /absolute/private/native-actions
pnpm gateway:native preview --definition /absolute/private/native-actions/interface-ID/definition.json --plan /absolute/private/native-actions/interface-ID/plan.json
pnpm gateway:native run --definition /absolute/private/native-actions/interface-ID/definition.json --plan /absolute/private/native-actions/interface-ID/plan.json --confirm REVIEWED_ACTION_DIGEST --evidence /absolute/private/runs --ack-new-run
```

Use the returned file paths, review the exact preview, and leave the simulator's selected window focused. `airalogy.native-interface.v1` is distinct from the survey's read-only definition: it declares controls, literal operations, states and limits. The template fills two synthetic samples, presses the simulation button and checks both `Complete` and the independently specified result `0.84`. It never learns the expected result from its own output.

The trusted builder seals the owned simulator's executable/Info.plist hashes into the helper. The helper also requires that exact sibling bundle path and the pinned process; a `simulation` label or same bundle ID cannot authorize another app. Rebuild older v1 manifests; builds now include sealed source and simulator identity. This is still an operator-owned development tool, not a boundary against malicious code running as that operator.

Every action durably records intent, rechecks the fresh snapshot in the helper, retains the exact AX control reference, checks focus/enabled state, uses only fixed AXValue/AXPress operations, and checks the post-state/readback. No focus stealing, arbitrary AX actions, script or coordinate fallback. An attempted action with missing/invalid results is uncertain and cannot be retried within that session. A new run is a new explicitly acknowledged operation, **not recovery**; preserve the evidence and reconcile first. Closing a session leaves the operator's app running and makes no physical safe-stop claim.

The owned fixture has synthetic labels, a secure field and an opt-in sample count. Tests open only this bundled fixture and close their own process, verifying private omissions, malformed selections, stale identities/observations, offline assembly, independent CLI reads and actual fill/press/result checks. Run actual GUI acceptance only in an operator-authorized graphical session:

```bash
pnpm --filter @airalogy/instrument-interface test:native
```

Hosted macOS CI compiles and checks the helper/signature/permission diagnostic without opening apps or granting TCC. Actual GUI tests fail, rather than silently skip, if explicitly requested on a host without authorization. Native production writes still need qualified vendor adapters, independent safety checks, Gateway booking/lease/stop integration and a real pilot. The owned-simulator action path does not complete automated equipment onboarding or qualify vendor control.
