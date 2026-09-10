# Native macOS interface observation

This is a **development backend**, not a production instrument controller. Surveys and assembled read definitions remain read-only for explicitly selected, already-running applications. A separate action definition permits bounded fill/press operations on **this build's owned simulator only**, not vendor software. Application startup requires its own local single-use approval; a survey or Aira grant never authorizes launch. Bounded discovery can list application metadata within a separately confirmed directory, not scan the workstation without a selected scope. No coordinate/script actions, screenshots or system-permission changes. Windows/Linux native and visual backends remain separate work.

## Find software in a selected directory

When the application path is not known, use Node 22+ and macOS's built-in property-list parser. This step requires neither the Swift helper nor Accessibility permission. It does not launch applications, read executable bytes, enumerate running processes or inspect windows.

```bash
pnpm gateway:native prepare-discovery --directory /Applications --depth 0 --workspace /absolute/private/discovery
```

There is **no default scan directory**. Select an absolute, POSIX-canonical physical directory you are authorized to inspect. Preparation reads only its identity and the discovery runtime, then writes a five-minute private preview/request. Keep the owner-only evidence workspace outside the selected directory. The preview records the exact directory/device/inode, depth, bounds and read-only effects; review it before continuing:

```bash
pnpm gateway:native discover --request /absolute/private/discovery/interface-ID/request.json --confirm REVIEWED_DISCOVERY_DIGEST
pnpm gateway:native discovery-result --request /absolute/private/discovery/interface-ID/request.json
```

Use the returned request path and reviewed digest. `discover` prints only a private report path, count and stop reason; `discovery-result` explicitly displays the saved **private** snapshot. The installed package exposes the same commands through `airalogy-interface-native`. No model call, Platform upload, automatic target selection or installation follows discovery.

- Depth `0` examines immediate children only; `1` or `2` explicitly includes that many vendor-directory levels. At most 1,000 entries and 40 application candidates are examined, with a 15-second scan budget and a 20-second parent-worker deadline. Each metadata parser has its own 1.5-second bound. Timeout stops only the owned worker/parser process group, never discovered applications.
- Dot-prefixed names, symbolic links, other-filesystem descendants and known non-application bundle interiors are excluded. It never descends into `.app` internals to discover helper applications. Only the candidate's bounded regular, unlinked `Contents/Info.plist` is read, at most 1 MiB, using a fixed system parser on selected bytes. The selected filesystem itself may be backed by network storage; this is not an offline-storage guarantee.
- Results retain the literal bundle path, declared names/identifier/version/build and metadata hash, **not verified vendor identity or code-signature trust**. Missing, invalid, oversized or linked metadata stays visible as an unavailable candidate. Metadata text is untrusted data, never a command. Manufacturer/model, APIs and equipment capability are not inferred from an app name.
- Stop reasons and exclusion counts describe partial coverage. No result means no discovered candidate within this exact bounded scope, not that the workstation has no compatible software. Select a narrower directory or separately authorize a different scope; there is no automatic expansion.
- Changed directory identity or runtime refuses execution. A started request cannot rescan; `discovery-result` reads historical evidence offline, including after software removal or update. It does not claim current availability. Prepare a new request for a new snapshot. Owner-controlled files are not cryptographic attestations against that owner.

After reviewing a candidate, pass its exact `bundle_path` to **`inspect` below**. That separate check verifies current bundle/code identity and matching processes; it can reject software that discovery merely listed. A subsequent startup still requires independent initialization approval, and UI observation/action permission remains separate. Discovery acceptance uses synthetic binary/XML metadata and the built, signed owned simulator without opening it; this does not qualify vendor software or hardware.

## Compare candidates with Aira or select manually

The existing private, one-shot survey-analysis workflow also accepts a distinct `airalogy.application-candidates.v1` report and exports `airalogy.application-selection-export.v1`. This does not turn directory entries into interface controls or grant a development/runtime bearer credential.

```bash
pnpm gateway:native prepare-selection --request /absolute/private/discovery/interface-ID/request.json --indices 1,3 --workspace /absolute/private/selections
```

Numbers are one-based positions in the saved discovery report: explicitly choose 1–10 distinct entries. `candidates.json` includes only their declared name/display name/identifier/version/build and metadata hash, stable candidate IDs and an opaque source digest. Paths, directory names, process IDs and unselected software are not copied. `selection.json` retains the local mapping: **never upload it, the complete discovery report or request files**. Metadata strings may themselves contain confidential or hostile text; this is field selection, not automatic secret removal.

In **Lab → resource library → Instrument Gateways → select Gateway → Software understanding → Choose software with Aira**, select equipment, import only `candidates.json`, enter the goal, review the exact report and consent to configured-model processing. Existing Owner/Manager plus `equipment.service` checks, preview binding, five-minute authorization, one reserved model attempt, 60-second/32-KiB response bound, private history, cancellation and read-only lost-response recovery apply. No new migration is needed beyond the existing survey tables. The provider may be external; limits do not guarantee a monetary ceiling.

Recommendations reference only supplied IDs and non-null metadata fields. They are **inferences**, not verified functions, vendor identity or compatibility. Insufficient data produces questions rather than an invented match. No paths, action fields or automatic launch are accepted. Review and export the analysis, then explicitly choose a candidate locally:

```bash
pnpm gateway:native inspect-selection --selection /absolute/private/selections/interface-ID/selection.json --candidate candidate_1 --analysis /absolute/private/reviewed-analysis.json --build /absolute/private/native-builds/interface-ID/native-build.json
```

The local tool validates retained discovery/selection digests, checks the chosen ID against the exported recommendations, resolves its path only from local evidence, and independently inspects current signed code and matching processes. Changed metadata is refused. It opens no application and grants no UI/hardware authority; continue through separate startup/observation approvals. With AI disabled, omit `--analysis` for explicit manual selection. Neither route proves scientific capability or real instrument qualification.

Acceptance uses actual local selection tools, API, isolated PostgreSQL and the existing model wrapper with synthetic provider responses; macOS additionally checks the owned signed simulator without opening it. No paid-model quality or vendor acceptance is implied.

## Prepare, review, capture

On macOS 13 or newer, use Node 22+, the installed workspace dependencies and Apple's Swift command-line toolchain. Build the bundled trusted helper into a new owner-only workspace:

```bash
pnpm gateway:native build --workspace /absolute/private/native-builds
pnpm gateway:native doctor --build /absolute/private/native-builds/interface-ID/native-build.json
```

Use the actual `build_file` returned by the build. It also builds an owned, ad-hoc-signed AppKit **simulation-only** reader; nothing is opened. The build manifest pins source/helper bytes and architecture. This is integrity under the trusted local operator account, not signed distribution, vendor trust, notarization, sandboxing against a malicious host or equipment qualification.

`doctor` reports existing Accessibility authorization without prompting or changing it. If authorization is absent, the operator must decide separately whether to grant it through normal system settings. There is no alternate bypass. The implementation uses Apple's [Accessibility authorization](https://developer.apple.com/documentation/applicationservices/1459186-axisprocesstrustedwithoptions) and [bounded AX messaging](https://developer.apple.com/documentation/applicationservices/1459345-axuielementsetmessagingtimeout) interfaces; the timeout affects this helper process, not global permissions.

`doctor.interactive_session` also reports console/login, same-user and active-display indicators plus any OS-reported lock flag, never names or user IDs. Launch and AX operations refuse an inactive/reported-locked session with `interactive_session_required`; metadata inspection and saved receipt recovery remain usable. These signals are not authentication or physical-readiness evidence: the lock flag is an optional OS diagnostic, and exact AX window/role/focus checks still apply. The tool never unlocks or wakes a session. Unlock and keep the graphical test session active yourself before opting into GUI acceptance.

Select the **POSIX-canonical absolute** `.app` path, its current same-user PID and exact window title. Opening any vendor application may initialize equipment; survey preparation neither opens it nor authorizes that initialization. Use the separately approved startup flow below only after obtaining local authority. Prepare a private JSON array of exact AX identifiers for regions to omit, if applicable:

```bash
pnpm gateway:native prepare --build /absolute/private/native-builds/interface-ID/native-build.json --bundle /Applications/SelectedInstrument.app --pid 12345 --title 'Exact selected window' --redact /absolute/private/masks.json --workspace /absolute/private/surveys
pnpm gateway:survey run /absolute/private/surveys/interface-ID/request.json --confirm REVIEWED_LOCAL_DIGEST
```

Preparation reads application metadata, not UI content. Review the private preview before `run`. The capture pins bundle identifier/version, code-directory integrity, executable/Info.plist hashes and process UID/start time, preventing PID reuse or app replacement from silently retargeting it. The public report includes only the declared application identity and observed control hints, not local paths/PIDs/build manifests.

Capture requires exactly one non-minimized AX window with the selected title and role. Extra windows, dialogs, missing/ambiguous private masks, invalid geometry, target drift or unreadable attributes stop the run. A survey request retains `run.started` before observation and cannot be replayed. Refusal events retain a fixed reason code, not OS error bodies. Inspect the selected application's state and reconcile with the operator before preparing a new request; never delete the marker as recovery. Transient or inconsistent OS accessibility trees are refusals too, not a reason to accept another window or change permissions.

## Application inspection and separately approved startup

`inspect` reads only metadata for the explicitly selected `.app` and its matching same-user instances, not window contents. It reports unresolved conflicting/starting instances without attaching to them. Its output is private and can supply a verified PID for a new survey selection:

```bash
pnpm gateway:native inspect --build /absolute/private/native-builds/interface-ID/native-build.json --bundle /Applications/SelectedInstrument.app
pnpm gateway:native prepare-launch --build /absolute/private/native-builds/interface-ID/native-build.json --bundle /Applications/SelectedInstrument.app --reason 'Locally authorized startup; initialization risks reviewed' --workspace /absolute/private/launches
```

After selecting a verified PID, `gateway:native windows --build BUILD_FILE --bundle APP_PATH --pid PID` explicitly reads up to eight window titles, roles, exact focus matches, minimized/geometry indicators and foreground state. It requires existing Accessibility access and an active session, reads no descendants or screenshots, and approves no actions. Titles can contain private project/file names; keep the output private. This helps select an exact window without guessing its title. Startup identity is not UI readiness: a missing or non-window AX object must be reconciled, never treated as a usable window.

Preparation launches nothing. Read the returned private `preview_file`: exact bundle/version/signature and executable/Info.plist hashes, runtime, reason, expiry and effects. Default expiry is five minutes, configurable from 30–900 seconds. Code integrity does **not** prove vendor trust or safe initialization. Confirm only software you are authorized to run, with equipment startup/network/resource effects independently reviewed:

```bash
pnpm gateway:native launch --request /absolute/private/launches/interface-ID/request.json --confirm REVIEWED_LAUNCH_DIGEST --ack-initialization
pnpm gateway:native launch-status --request /absolute/private/launches/interface-ID/request.json
```

The helper uses [Apple's application-opening API](<https://developer.apple.com/documentation/appkit/nsworkspace/openapplication(at:configuration:completionhandler:)>), with no supplied arguments, custom environment, documents, scripts, forced new instance or substitution of another installed copy. It requests no activation or recent-item entry. This is **not a sandbox**: the selected app/system may add environment variables, show its own UI, activate itself, initialize equipment, connect to a network or start background services. Gatekeeper is never bypassed; its UI may still appear and is not automatically dismissed.

The runtime rechecks bundle/build/OS and expiry, durably records `launch.started` plus intent before dispatch, and serializes same-bundle-ID launches across this user's workspaces. Any existing matching bundle ID stops startup, including another installed copy. It checks the returned executable/bundle and process start time, refuses reuse/race ambiguity and leaves the app running. The helper waits at most 20 seconds; the parent bounds the call to 30 seconds. Timeout or lost receipts are uncertain, not permission to relaunch or kill the app. Never delete a marker to retry.

`launch-status` reads saved receipts **offline**, even after helper upgrades or app exit. `reported_identity_verified` means identity was checked at startup, not that the app is currently running, ready or physically safe. `uncertain` means dispatch was recorded without a verified receipt. Use `inspect` with a current trusted build and reconcile with the operator; status never launches, focuses, terminates or retries software. Startup gives no UI-action or production Gateway authority. Survey capture still needs its own target/window/privacy confirmation.

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

For reviewed installed adapters, the separate [native read worker](./instrument-interface-worker.md#installed-native-read-adapters) connects this read-only definition to existing Instrument Jobs and receipt recovery. It does not launch or retarget an application, upgrade the definition to actions or establish vendor qualification. Graphical installed/API acceptance is explicitly opt-in and separate from compile-only checks.

## Separately reviewed owned-simulator actions

After explicitly opening the returned `simulator_app` in an authorized graphical session, select its actual PID. The following preparation reads metadata only and writes editable definition, plan and policy files; it does not open or operate the app:

```bash
pnpm gateway:native simulation-template --build /absolute/private/native-builds/interface-ID/native-build.json --pid 12345 --workspace /absolute/private/native-actions
pnpm gateway:native preview --definition /absolute/private/native-actions/interface-ID/definition.json --plan /absolute/private/native-actions/interface-ID/plan.json
pnpm gateway:native run --definition /absolute/private/native-actions/interface-ID/definition.json --plan /absolute/private/native-actions/interface-ID/plan.json --confirm REVIEWED_ACTION_DIGEST --evidence /absolute/private/runs --ack-new-run
```

Use the returned file paths, review the exact preview, and leave the simulator's selected window focused. `airalogy.native-interface.v1` is distinct from the survey's read-only definition: it declares controls, literal operations, states and limits. The template fills two synthetic samples, presses the simulation button and checks both `Complete` and the independently specified result `0.84`. It never learns the expected result from its own output.

The trusted builder seals the owned simulator's executable/Info.plist hashes into the helper. The helper also requires that exact sibling bundle path and the pinned process; a `simulation` label or same bundle ID cannot authorize another app. Rebuild older v1 manifests and rebuild/review after any native source update, even when the manifest schema has not changed. Builds include sealed source and simulator identity. This is still an operator-owned development tool, not a boundary against malicious code running as that operator.

Every action durably records intent, rechecks the fresh snapshot in the helper, retains the exact AX control reference, checks focus/enabled state, uses only fixed AXValue/AXPress operations, and checks the post-state/readback. No focus stealing, arbitrary AX actions, script or coordinate fallback. An attempted action with missing/invalid results is uncertain and cannot be retried within that session. A new run is a new explicitly acknowledged operation, **not recovery**; preserve the evidence and reconcile first. Closing a session leaves the operator's app running and makes no physical safe-stop claim.

The owned fixture has synthetic labels, a secure field and an opt-in sample count. Tests open only this bundled fixture and close their own process, verifying private omissions, malformed selections, stale identities/observations, offline assembly, independent CLI reads and actual fill/press/result checks. Run actual GUI acceptance only in an operator-authorized graphical session:

```bash
pnpm --filter @airalogy/instrument-interface test:native
```

Hosted macOS CI compiles and checks the helper/signature/permission diagnostic without opening apps or granting TCC. Actual GUI tests fail, rather than silently skip, if explicitly requested on a host without authorization. Their shared, test-only setup verifies and foregrounds the exact already-running owned simulator once; it is excluded from the installed package, accepts no vendor target and never recovers focus after a refused action. Keep that test window in the foreground during acceptance. Native production writes still need qualified vendor adapters, independent safety checks, Gateway booking/lease/stop integration and a real pilot. The owned-simulator action path does not complete automated equipment onboarding or qualify vendor control.
