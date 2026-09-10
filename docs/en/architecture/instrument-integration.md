# Equipment software integration

This delivers **GUI drafts/rehearsal, a bounded browser development backend, local installation pairing and sandboxed Adapter Packages** from [RFC #5](https://github.com/airalogy/platform/issues/5), not the complete equipment-integration product.

## Goal and authority

An integration assistant should understand an authorized instrument application, observe demonstrations and propose a reusable adapter for validation before deployment. Prefer supported API/SDK, accessibility controls and browser DOM; visual Computer Use needs an independently qualified backend. Launching software may initialize equipment and is not assumed read-only.

Observation, navigation/launch, physical changes, installation and qualification are separate permissions. Screen content and manuals are untrusted data, not instructions. Replay never grants physical control. Protocol continues to describe research methods; an integration draft is not a Protocol or Instrument Command.

## Available workflow

In **Lab → resource library → Instrument Gateways**, select a Gateway and use **Equipment software integration**. The API requires both Lab Owner/Manager access and `equipment.service` on the active equipment. Drafts and history are not public, including when a Project is public.

1. Select equipment and enter the goal. A unique equipment option is inherited.
2. Load the synthetic example or import JSON (256 KiB maximum): exact application/version/OS/language, literal steps, source declarations, limitations and independently supplied observations/expected outputs.
3. Optionally ask Aira to edit from those observations and authorized notes. Processing consent is mandatory; the deployment model may be external. One call is limited to 60 seconds, with no model-selected tools, browsing, code execution or iterative retries. Permissions are checked before and after generation. This is not autonomous desktop exploration. Imported source labels are user declarations, not cryptographic attestations.
4. Rehearse and preview. The API interprets data only: exact window/target, interactive session, control ownership, blocking dialogs, unique controls, state continuity, parameter readback and expected outputs. Every command needs a passing scenario for an overall pass. Failures can be saved for diagnosis without being labelled successful.
5. Confirm the preview. Its digest binds equipment/Gateway revisions, actor, draft revision and content. Stale/concurrent writes fail instead of overwriting. Save adds the private draft, report and audit snapshot, not commands or execution authority.
6. Reload, edit or export. Old revision exports do not change current or installed versions. Draft/history lists currently show the most recent 100 entries.

AI-disabled deployments retain steps 1–2 and 4–6. No real documents/screenshots are automatically collected or sent to a model. Treat exports as private laboratory material until separately reviewed for sharing.

## Stop uncertainty and equipment ownership

An execution error is not a physical-stop confirmation. After a job has started, a failure callback without the strict boolean `safe_stop_confirmed: true` keeps it in `stop_requested`, pauses the research run and retains its lease identity for recovery. The Gateway sends confirmation only after bounded safe-stop reconciliation. Lost responses are replayed without repeating the physical command; local recovery state is retained until the Platform acknowledges a terminal failure.

Equipment is serialized across all Gateways, not just within one controller or booking. A leased, running or stop-requested job prevents another Gateway from taking the same Resource, even after the original booking expires. Credential rotation/pairing also remains blocked by the original unresolved job. This is a software guard, not an emergency-stop circuit or independent evidence that vendor hardware is safe. Upgrade both API and Gateway together; older clients without the explicit confirmation fail closed after started-job errors and require reconciliation with an updated Gateway. Historical terminal failures from before this guard are not retroactively certified safe: inspect and reconcile any previously uncertain equipment before enabling it.

## Local tools

From a source checkout with Python 3.11+:

```bash
pnpm gateway:rehearse --example
pnpm gateway:rehearse /absolute/path/to/rehearsal.json
```

The CLI needs no additional Python dependencies or credentials. It rejects a final symlink and oversized files, never scans adjacent directories, follows package paths or executes content. Exit codes: 0 matched, 1 mismatched observations, 2 invalid input. No results are uploaded automatically.

With repository Node dependencies and Playwright Chromium installed:

```bash
pnpm gateway:gui-demo
```

This operates only the bundled synthetic reader through the shared [browser interface backend](./instrument-browser-interface.md): fill sample count, click simulation, read result. Network requests are denied. The expected result is fixed independently of observations. It prints a bundle for import and saves private local evidence. The separate `gateway:interface` CLI supports selected, digest-confirmed simulation HTML and observation-only URL targets; it is not a native Windows backend or production instrument controller.

## Contract and remaining delivery

### Local installation pairing

In the Gateway panel, a Lab Owner/Manager first disables the Gateway and finishes or safely stops active jobs, then previews and creates a pairing code. It expires after ten minutes, is shown once and cancels earlier pending pairings. The current credential is not changed yet.

On the authorized workstation, create a service-account-owned private directory (`0700`) and run:

```bash
pnpm gateway:pair --credential-file /private/service-directory/gateway.json --platform-url https://lab.example.edu/api --lab-id <Lab-UUID> --gateway-id <Gateway-UUID> --client-name "Local station"
```

Replace every placeholder. An installed Gateway package can instead use `python -m airalogy_instrument_gateway.pairing_cli`. Verify the Platform URL and scope before entering the code at the hidden prompt; never put the code in shell arguments, chat or an issue.

The assistant creates an exclusive `0600` credential file before contacting the selected Platform. It does not load adapters or poll jobs. Refresh Platform's pairing list, compare the full fingerprint on both sides, preview and confirm. Confirmation invalidates the old credential, records an audit event and **leaves the Gateway disabled**. A client label is a declaration, not hardware attestation. Existing allowlists and approvals are neither expanded nor bypassed.

After a lost network response, use `--credential-file <same-file> --resume` to retry the same claim, or `--credential-file <same-file> --status <pairing-UUID>` to recover confirmation status. An expired/cancelled attempt needs a fresh pairing code; never overwrite an existing identity file. Configure the runtime with `AIRALOGY_GATEWAY_CREDENTIAL_FILE` instead of `AIRALOGY_GATEWAY_TOKEN`. It inherits the paired destination and rejects conflicting URL overrides. Non-loopback addresses require HTTPS and redirects are rejected.

Private directory/file permissions, symbolic/hard links, exclusive creation and destination binding are checked. This is POSIX software acceptance only: Windows ACL storage/service installation is not implemented and unsupported credential storage is refused. Legacy service-manager secret configuration remains usable. Pairing neither installs an Adapter Package nor establishes equipment qualification.

### Support matrix

Actual Python drivers can now be built, inspected without execution, tested in an isolated container and prepared as inactive POSIX installation snapshots. See [Adapter Packages](./instrument-adapter-packages.md) for the selected-file workflow, immutable artifacts and security boundaries. Preparation does not activate an instrument driver.

`airalogy.gui-rehearsal.v1` supports `observe`, `read`, `invoke`, `set_value` as **step descriptions compared with observations**, literal scalars, up to 10 commands, 40 steps per command and 20 scenarios. No shell, code, URL fetching, coordinates, implicit retries or physical stop claims. One authored Python contract in Gateway generates the API copy; CI checks equality.

| Capability | Status |
| --- | --- |
| Private draft/history, import/export, preview confirmation | Implemented |
| Offline replay and synthetic browser demonstration | Implemented; not hardware evidence |
| Selected browser application observation and bounded simulation exploration | [Local survey](./instrument-interface-survey.md) discovers visible control hints in the selected scope; the [browser backend](./instrument-browser-interface.md) and independently authorized [Aira action selection](./instrument-interface-exploration.md) use reviewed definitions/policies. No installed-app discovery or live URL writes |
| Optional Aira editing within supplied target/controls/states | Implemented; provider success needs deployment configuration |
| Instrument software discovery/launch/exploration | [Scoped macOS discovery](./instrument-native-interface.md#find-software-in-a-selected-directory) lists metadata after directory/depth confirmation. [Aira candidate comparison](./instrument-native-interface.md#compare-candidates-with-aira-or-select-manually) uses only explicitly selected metadata; a person selects software before independent current identity checks. Selected startup has its own expiring approval and single-use receipt; `windows` supplies bounded metadata. Autonomous software selection, vendor-action qualification and cross-platform backends remain open |
| Native accessibility and visual control backends | [macOS native observation](./instrument-native-interface.md) supports identity-pinned running apps, private surveys, Aira/manual review and read-only definitions. Separately reviewed fill/press is verified on the exact owned AppKit simulator only. Vendor-native writes, Windows/Linux and visual control remain open; real acceptance needs an explicit target |
| Source-included package build, integrity inspection, isolated tests | Implemented; package tests are not hardware evidence |
| Reusable documented HTTP GET/JSON reads | [Fixed-operation SDK backend](./instrument-http-interface.md), owned simulator and source-included reference; actual installed API/result-recovery acceptance is synthetic, not vendor qualification |
| Private package import, source review/revocation, protected download | Implemented; not installation or qualification |
| Find reusable packages in the Lab catalogue | [Exact declaration comparison](./instrument-adapter-packages.md#find-and-compare-an-existing-lab-package), paginated candidates and fresh source review implemented; no automatic selection, public catalogue or qualification |
| Inactive pure-Python offline installation and local receipts | Implemented, POSIX; no activation or remote authorization |
| Exact device/package/config binding, independent installation grants and receipt synchronization | Implemented; inactive POSIX pure-Python copies only |
| Bounded source generation and test repair | Implemented through the [local authoring assistant](./instrument-source-authoring.md); fixed human-selected contracts/tests, synthetic acceptance only |
| Autonomous application exploration and signed distribution | Not implemented |
| Two-sided identity review, one-time pairing, private credential storage | Implemented, POSIX software acceptance |
| Independent scoped acceptance records, expiry and revocation | Implemented; human assertions, simulation kept separate |
| Enforced active-version selection, rollback and local target drift checks | Implemented, POSIX/pure-Python; reviewed driver observations, not hardware attestation |
| Prevent manual execution bypass after installation claim | Implemented; exact managed grant required, stop/result reconciliation preserved |
| Local raw-file snapshot, provenance and crash recovery | Connected to the POSIX runtime with acquisition-time hashes and an explicit source directory |
| Instrument scoped upload and draft DataAsset/Record mapping | Receiving/association APIs, automatic SDK transfer and bilingual file review implemented. Recovery does not repeat acquisition or initialize the driver; older Gateways cannot lease file-producing jobs |
| Real equipment, OS installation and safety acceptance | Awaiting authorized pilot and operator |

Existing Gateway signing, allowlists, bookings, approvals, heartbeat and safe-stop contracts are unchanged. No pilot model/software/OS is specified. Do not close RFC #5 or mark P0-A/P0-B acceptance complete based on this slice.

Migration `0048_instrument_integration_drafts` adds drafts and `0049_instrument_pairings` adds enrollment records. Upgrade through the normal backed-up deployment workflow before using the UI. Test migrations on disposable data; downgrade deletes these records but does not undo confirmed credential rotation, reverse physical actions or uninstall adapters.
