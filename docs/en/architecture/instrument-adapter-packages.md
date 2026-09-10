# Instrument Adapter Packages

An `airalogy.adapter-package.v1` ZIP contains an actual driver wheel, its source, tests, licenses and all declared dependency wheels. It is separate from a GUI rehearsal bundle and never travels inside an Instrument Job. Build and inspection require Python 3.11+, not AI or Platform credentials.

## Build and inspect the synthetic example

From the repository root, choose a new output directory:

```bash
adapter_output_dir=$(mktemp -d)
pnpm gateway:package build \
  --manifest apps/instrument-gateway/examples/adapter-package/manifest.json \
  --factory synthetic_reader:create_adapter \
  --file source/synthetic_reader.py=apps/instrument-gateway/examples/adapter-package/source/synthetic_reader.py \
  --file tests/test_reader.py=apps/instrument-gateway/examples/adapter-package/tests/test_reader.py \
  --file licenses/LICENSE.txt=apps/instrument-gateway/examples/adapter-package/licenses/LICENSE.txt \
  --output "$adapter_output_dir/synthetic-reader.zip"
pnpm gateway:package inspect "$adapter_output_dir/synthetic-reader.zip"
```

Only explicitly selected files are read; no workstation discovery or recursive collection takes place. The reference builder assembles a pure-Python wheel without running a build backend. It refuses output overwrite. For unchanged inputs, the archive and digests are deterministic. An installed SDK also exposes `python -m airalogy_instrument_gateway.package_cli`.

The example computes synthetic numbers only. It neither connects to equipment nor qualifies a real reader. Its expected output and failure cases are explicit tests, not values inferred from a model response.

## Immutable contract

The manifest records package ID/SemVer, entry-point name, declared author and source references, license, exact Gateway/Python compatibility, declared equipment/software combinations, limitations and file hashes. Each exact command version declares input/output schemas, risk, units, effects, timeout, completion, stop behavior, safety requirements and bounded output files. Physical-command retry is always `never`.

Inspection checks archive size/count limits, portable paths, case collisions, regular files, exact declared contents and SHA-256. It independently checks wheel metadata, entry points and every `RECORD` digest. Links, traversal, encrypted ZIP members, `.pth`, startup hooks and relocated wheel scripts/data are rejected. Missing/undeclared files and attempts to replace the Gateway SDK fail closed. A manifest contains no installation or hardware-authority flag.

Hashes establish content identity, **not author trust or physical safety**. Source labels, claimed compatibility and package-supplied test results remain declarations. Dependencies are shipped as exact wheel bytes; compatibility and dependency satisfaction are tested offline, not resolved from the network. Native/OS installers are outside the reference builder and require a separately reviewed installation path.

## Run isolated tests

Use a maintained Docker daemon on an authorized test workstation. Independently obtain and verify the Gateway SDK wheel and a Python image; preinstall the image and pin its digest. Do not accept these trust inputs from the adapter itself. Replace the placeholders:

```bash
pnpm gateway:package test /absolute/path/to/adapter.zip \
  --sdk-wheel /absolute/path/to/airalogy_instrument_gateway-0.1.0-py3-none-any.whl \
  --trusted-sdk-sha256 <independently-verified-SDK-SHA256> \
  --image <trusted-image-repository>@sha256:<image-SHA256> \
  --timeout 60
```

The CLI never pulls images or falls back to host execution. The container has no network, host mounts, devices, Docker socket or Gateway credentials; it runs as a non-root user with a read-only root, dropped capabilities, no new privileges, process/memory/CPU limits and bounded temporary storage. Wheels install offline inside the disposable container; dependency checks and a nonempty test suite must pass. Container isolation is not a defense against an unpatched kernel/runtime vulnerability: use an isolated, maintained test host for untrusted packages.

The host enforces a 1–300 second deadline and verifies container cleanup. If termination cannot be established, it reports an error rather than a successful stop; resolve that container before retrying. Diagnostics are bounded, explicitly untrusted and never interpreted as instructions. Exit codes are 0 for passing tests/inspection/build, 1 for failed tests and 2 for invalid input or sandbox errors.

Reports bind archive, manifest, SDK and image digests and always mark `simulation_only: true`, `hardware_authorized: false`. A test pass is **not independent qualification**: package-authored tests can be incomplete or dishonest. No upload, install, Gateway enablement, command registration or device action follows automatically.

## Inactive offline installation

After independent source/dependency review, a local operator can prepare an **inactive** installation snapshot. This creates an isolated Python environment from already inspected wheel bytes without pip, network resolution, build scripts, driver imports or device actions. A virtual environment separates dependencies; it is **not** a security sandbox. Platform installation authorization, equipment binding and qualification are not implied by this local operation.

The first installer accepts POSIX owner-only directories and pure Python `py3-none-any` wheels with unconditional exact dependency pins. Unsupported tags, dependency expressions, Python versions or missing dependencies are rejected, not fetched. Native vendor installers and Windows ACL/service setup need separate support.

Choose an existing, physical absolute directory with mode `0700` (no symlink ancestors), the independently verified SDK wheel, and an explicitly selected local JSON configuration file. Configuration contents stay local; previews/receipts contain only its digest. For the synthetic example, the configuration file contains `{}`. Replace the placeholders:

```bash
pnpm gateway:install preview /absolute/path/to/adapter.zip \
  --root /absolute/private/gateway \
  --sdk-wheel /absolute/path/to/airalogy_instrument_gateway-0.1.0-py3-none-any.whl \
  --trusted-sdk-sha256 <independently-verified-SDK-SHA256> \
  --config /absolute/private/adapter.json
```

Review the destination, configuration/SDK/package digests, Python version and file count/size. Repeat the command with `install` instead of `preview`, adding `--source-reviewed --confirm-digest <preview-digest>`. This acknowledgement records the **local operator's** review; it does not impersonate Platform's Lab source approval or grant installation authority on behalf of another administrator.

The installer and the existing Gateway must use the **same** `<root>/state.json` journal. The installer takes its exclusive process lock and refuses any unreconciled job, including unconfirmed stops or pending receipts. Another independently configured journal cannot protect an already running Gateway. Use the configured service directory; do not point installation at a new directory to bypass a live process.

Each package/SDK/configuration/Python identity produces a separate snapshot. Complete wheel bytes and their receipt are verified before publishing it; a matching retry checks against the independently supplied original wheel bytes, including when receipt hashes have been altered. Existing snapshots are never overwritten and **no active pointer, service, command allowlist or Gateway state is changed**. A crash can leave a private `.pending-install-*` directory; it is not an installed/active version, and a retry uses a new staging directory. Do not manually launch unqualified vendor code from the prepared environment.

Receipts explicitly carry `platform_authorized: false`, `hardware_authorized: false` and `activation_performed: false`. Receipt-only verification detects differences relative to local metadata, not author trust or a signed remote attestation. The software tests explicitly load the repository's synthetic adapter from a prepared environment on macOS and inside a network-disabled Linux container; these tests do not qualify real instrument software or hardware.

## Remaining lifecycle

### Private import and source review

In **Lab → resource library → Instrument Gateways → select Gateway → Prepare adapter → Find or import a package**, an Owner/Manager can select the locally tested ZIP, preview its commands/provenance/file hashes and confirm the exact content and Lab destination. Lab packages are also accessible before selecting a Gateway. The API performs no imports, builds or driver execution. Files are Lab-visible to members, not public; never package credentials, workstation configuration secrets or unapproved customer material.

The preview binds the authenticated actor, Lab, import identity and archive/manifest hashes. Confirmation repeats inspection and permissions. Concurrent imports of the same Lab/package/version reuse one immutable release and logical ResearchFile; different content requires a new version. A lost-response retry does not duplicate quota or revive a revoked version. Package lists are paginated.

Download the exact archive for independent code, origin, license and dependency review. Downloads reuse short-lived ResearchFile tokens, fresh authorization and access audit. Approval requires an explicit acknowledgement, reason, preview and confirmation; concurrent/stale reviews fail. An append-only review history retains each decision. Source approval is an organizational assertion, not a cryptographic signature or proof of honest package-authored tests. Revocation is terminal for that version, but does not uninstall local software or stop a running instrument; coordinate those actions separately. There is no public catalog or runtime credential access to this management API.

Migration `0050_instrument_adapter_packages` adds release and review records. Use normal backed-up deployment procedures; software acceptance uses only disposable databases. Downgrade removes catalog/history, not the stored ResearchFile archive and not any locally installed software.

### Find and compare an existing Lab package

Before authoring another adapter, select **Find reusable adapters** in the Lab package panel. Enter the exact manufacturer and model; optional firmware, control software/version, OS, architecture and Gateway/Python versions refine the comparison. Unknown optional values stay empty. Names are case-sensitive literals after trimming outer spaces; no fuzzy matching, aliases or version ranges are interpreted. This reads the private Lab catalogue, not equipment, installed applications or a public global catalogue. No model is called.

The Lab-authorized `POST /instrument-adapter-packages/match?lab_id=...` accepts `profile` and a strict `include_revoked` boolean. Gateway versions are exact SemVer; Python uses exact `major.minor`. Manufacturer/model are filtered within the same declaration row **before pagination** (default 10, maximum 20 packages per page). The response includes `has_more` and `next_offset`; every matching combination is compared independently, never mixing firmware from one row with software from another.

- **Declarations match**: all nine supplied fields match one combination and its declared runtimes, not equipment qualification.
- **More information or review needed**: target details are missing, or declarations use broad/unknown values such as `any`, `all`, `unknown`, `unspecified` or `*`. These are not executable wildcards.
- **Compatibility conflicts**: at least one supplied detail differs from the literal declaration.

Results include archive identity, source-review snapshots, field differences and package-supplied test references. Even a non-simulation test claim is not independently verified here: `qualification_checked`, `hardware_authorized` and `installation_authorized` remain false. Revoked releases are excluded unless explicitly requested for inspection. Editing the target or reopening search clears old results.

**Inspect and review** reloads the exact release through the scope-protected `GET /instrument-adapter-packages/{release_id}`. Search never selects a package, creates an installation grant or bypasses later revocation. Continue through the existing protected download, source review, device-specific qualification and installation workflow. No match means no corresponding declaration in this Lab, not proof that an adapter cannot exist; import a separately prepared package or use bounded source authoring. AI-disabled lookup is complete and no new migration is required.

### Platform-authorized installation and receipt synchronization

Migration `0051_instrument_device_bindings` adds exact equipment/Gateway/release/configuration bindings, short-lived installation grants and revisioned audit records. Upgrade through normal backed-up deployment procedures. Downgrading removes these authorization records, not local software or physical actions.

After pairing and source approval, prepare a new **installation-only** identity locally. Use the real Gateway service directory and its `<root>/state.json` journal, never a second journal to bypass a running service. The private request's parent must be owner-only (`0700`). Replace the placeholders:

```bash
pnpm gateway:installation prepare \
  --platform-url https://lab.example.edu/api \
  --lab-id <Lab-UUID> --gateway-id <Gateway-UUID> \
  --package /absolute/path/to/adapter.zip \
  --sdk-wheel /absolute/path/to/airalogy_instrument_gateway-0.1.0-py3-none-any.whl \
  --trusted-sdk-digest <independently-verified-SDK-SHA256> \
  --config /absolute/private/adapter.json --root /absolute/private/gateway \
  --destination /absolute/private/install-request.json
```

The manager stores a new `aiinstall_` secret exclusively in the `0600` private file **before** outputting public JSON. It never reads the Gateway execution credential. Only the public JSON, not that private file, belongs in **Instrument Gateways → select Gateway → Device bindings and installations → Authorize an installation**. An Owner/Manager also needs `equipment.service` and access to the package ResearchFile. Compare the full fingerprint with the local operator, select the exact equipment and matching approved release, review digests/versions, then confirm. A private request or extra fields are rejected. This fingerprint identifies the reviewed request; it does not attest to physical device identity or prove that the local machine is trustworthy.

Authorization lasts ten minutes until claimed; claim opens a fifteen-minute package download window. The installer uses only its installation credential to fetch that exact package. It cannot call Gateway job APIs. The API rechecks current membership, equipment permission/revision, source review, file access and paired identity, including after storage I/O. Pending grants block Gateway enablement, credential rotation and re-pairing. Expired **unclaimed** grants release that guard; claimed grants require a receipt or explicit revocation even after the download window expires.

```bash
pnpm gateway:installation apply /absolute/private/install-request.json --source-reviewed
pnpm gateway:installation status /absolute/private/install-request.json
```

The installed SDK exposes the same interface as `airalogy-instrument-installation` or `python -m airalogy_instrument_gateway.installation_manager_cli`. HTTPS is mandatory outside loopback; redirects are rejected and responses bounded. Configuration, SDK/package/interpreter changes require a new request. The manager holds the runtime journal lock throughout claim, download, inactive installation and receipt delivery. It never imports the driver or starts a service.

The immutable local snapshot and receipt are durable before delivery. On a lost response, rerun the same `apply` command: it verifies the original bytes and resends the matching receipt, without re-downloading or re-executing a physical command. Matching receipts can reconcile after the download window expires, but source/target revocation still fails closed. A missing or altered installed snapshot is not silently repaired. The server retains only descriptor hashes, file count/size and the full local receipt's digest—not paths, configuration or the file inventory. Local receipts remain installation facts, not authorization certificates; Platform retains the separate grant.

Refresh the UI to see **Installed; execution status is separate** and its audit history. Installation receipt fields describe that installation operation, not current runtime state. Explicit revocation is preview/revision guarded and remains available after source withdrawal. It removes future installation access, not already downloaded files; it does not uninstall, stop equipment or certify a safe stop. Review such local copies separately. No active version, command registration, booking, Executor Binding or hardware permission is created by installation alone.

### Execution boundary after installation

A pending installation blocks manual execution for both its Gateway and equipment. **Claiming** the grant opts those targets into managed qualification: an installed receipt, grant revocation, credential rotation or a different Gateway must not restore the old manual-command path. The API enforces this at manual Gateway/command enablement, available-command lookup, task creation, control-step queueing, lease delivery and start. Disabled command definitions may still be prepared. Stop, failure and result receipts remain accessible for safe reconciliation; blocking new execution is not proof of a safe physical stop.

Cancelling or expiring a grant **before claim** leaves no permanent execution restriction, provided no other pending/claimed installation covers the targets. Already claimed history is retained; do not delete bindings or downgrade away the enforcement to bypass it. Existing unmanaged equipment keeps its manual path.

The managed active-version workflow below provides a separate execution path. Installation alone still prepares inactive software; source review, independent qualification, Platform activation and explicit local startup are separate gates. Software acceptance uses synthetic fixtures, not a certified real instrument pilot.

### Independent acceptance records

Migration `0052_instrument_qualifications` adds human assessment records. In an installation's **Inspect and review → Equipment qualification**, record the verified target identity, firmware/application/driver/OS versions, assessment time and expiry (at most one year). Select exact commands from the installed package. For each command, supply an independent method, expected result and observed result for identity, output/units and completion; state-changing controlled commands also require parameter readback, safe-stop, takeover and interlock checks. Explicitly mark each check passed or failed. Failed observations remain valid records, not successful qualification.

Simulation is the default. Package self-tests and commands declaring `simulation_only: true` cannot qualify physical equipment. Real-equipment reports require separately authorized, already performed tests and explicit independent human review. These are accountable organizational assertions—not automated verification, professional certification, or permission to start new tests. This API never contacts equipment. The managed runtime compares fresh adapter observations with the assessor's target; this is not a cryptographic hardware attestation and depends on the reviewed driver's honest implementation.

API paths under `/instrument-installations/{binding_id}` are `GET /qualification-context`, `GET /qualifications`, `POST /qualifications/preview`, `POST /qualifications`, and `POST /qualifications/{id}/revoke/preview` / `/revoke`. Scope is `simulation`, `read_only` or `controlled`; evidence origin is `manual_observation`, `independent_test` or `package_self_test`. The independent `equipment.qualify` capability is required in addition to current Owner/Manager and equipment-management access; custody/booking alone does not confer qualification authority. No AI is required.

Confirmation binds the actor, report, equipment revision, approved release, exact package/SDK/configuration/interpreter descriptor, installed receipt, selected contracts and optional Lab ResearchFile evidence digests. It rechecks permissions and source state. Evidence references never grant access; inaccessible details are redacted on read while retaining a revocable history entry. The form records observations directly; attaching existing private ResearchFiles is also supported through the API, not by inventing a Paper or Protocol.

Reports cannot be edited or silently overwritten. An identical confirmation retry returns the same record; corrections require a new report. Revocation preserves the original observations and actor/time/reason, is terminal and supports identical receipt retries. Expiry, revoked installation, changed Resource/Gateway/source, changed installation metadata or missing evidence invalidate current status. Installation, qualification, active-version authorization and physical running state are distinct. A valid report does not itself register commands or start a driver.

### Active versions, local startup and rollback

Migration `0053_instrument_activations` adds immutable activation grants and job-to-grant pins. Apply it only through normal backed-up deployment. Downgrade removes execution audit/pins, not local files, services or physical actions; never downgrade a station with running/unreconciled work or to bypass managed restrictions.

In **Inspect and review → Active version authorization**, select a current real-equipment qualification for this binding, exact covered commands, an expiry no later than the qualification and a reason. Review equipment/software identity, source/config/SDK hashes, affected command revisions and previous authorization before confirming. Current Owner/Manager access plus `equipment.service`, `equipment.qualify` and `equipment.activate` are required. Restricted source/evidence access and approver account/access are rechecked. There is at most one unrevoked grant per Gateway and equipment. Simulation-only assessments cannot activate equipment.

Confirmation enables only the approved command contracts and Gateway. Each selection increments command revisions, including rollback to identical bytes. Leased/running/stop-unconfirmed work prevents switching. Old queued jobs fail closed; they never inherit a new grant. Idempotent confirmation retries return the original outcome without re-enabling a revoked/superseded version. To roll back, select the previous binding in installation history and repeat this fresh preview-confirm flow while its qualification and source remain valid; there is no permission-restoring shortcut.

The local operator independently previews startup. Use the exact original package, SDK, config and private installation request, plus the paired runtime credential. Replace the placeholders, and run from an independently trusted SDK:

```bash
pnpm gateway:activation preview \
  --request /absolute/private/install-request.json \
  --credentials /absolute/private/gateway.json --activation <Activation-UUID>
pnpm gateway:activation run \
  --request /absolute/private/install-request.json \
  --credentials /absolute/private/gateway.json --activation <Activation-UUID> \
  --confirm-digest <local-startup-preview-digest> --startup-authorized
```

An installed SDK exposes `airalogy-instrument-activation`. Preview reads only explicitly selected files and the signed current grant; it never imports a driver. **Startup may initialize equipment**, so the on-site acknowledgement is required even before the first job. The launcher revalidates exact original wheel bytes, interpreter, config, destination, Platform/Lab/Gateway identity and receipt under the journal lock. It launches a clean `-I -S -B` interpreter loading only verified installed wheels in addition to the trusted standard library. This prevents accidental host-plugin/site-hook loading; it is **not an untrusted-code sandbox**. Reviewed driver code can access its process account, device permissions, network and configured secrets. Use a least-privilege service account and separately reviewed OS permissions; no system service is installed or started by Platform.

Managed adapters must implement `identity()` with fresh `identity_reference`, `firmware`, `application`, `application_version`, `driver_version` and `os_version` observations. Values must exactly match the qualification target. Reads are bounded to five seconds; timeout halts rather than retrying unknown controller state. Identity is checked during confirmation, preflight and immediately before execution, alongside the existing safety checks. Stop/recovery must remain usable even after identity or authorization drift. No generic vendor identity discovery is implied.

Every new managed job—including manual, Aira-approved and control-session steps—carries an immutable activation pin, exact command/Resource revisions and signed envelope. Lease and start require the locally selected pin; a running process never follows a new active pointer or hot-reloads a driver. Authorization expiry, source/evidence withdrawal, qualification revocation or approver access changes block new execution and cause stop requests on running-job heartbeats. This is not an emergency stop or real-time safety interlock: offline equipment still depends on local heartbeat-loss handling and hardware-specific safety.

Keep the original signed `activation-<UUID>.json` snapshot, verified installation and private journal for recovery. With an unresolved job, run the same preview/run commands with `--recover` and its original activation ID. This mode does not fetch new authorization or lease new work; it only performs the existing idempotent safe-stop/result reconciliation. Revocation does not block those authenticated receipts. A rotated/unavailable Gateway credential or missing original files requires explicit operator reconciliation, not deleting the journal. Do not uninstall or switch hardware while the original process is stopping.

Management APIs are `GET/POST /instrument-installations/{binding_id}/activations`, `POST .../activations/preview` and `POST .../activations/{id}/revoke/preview` / `/revoke`. Runtime reads `GET /instrument-gateway/v1/activation`; lease/start carry its exact `activation` pin. The shared pin contract is `activation_contract.py`, generated into API by the existing contract synchronization command.

### Not yet delivered

Bounded autonomous driver generation, authorized native/visual Computer Use and supported OS service installation still need their governed workflows. Real software exploration, device safety acceptance and second-installation reuse require an authorized pilot. Current managed execution is POSIX/pure-Python software acceptance only, not general vendor-driver or hardware certification. See the [integration support matrix](./instrument-integration.md#support-matrix).

The standard-library contract is authored in `apps/instrument-gateway/src/airalogy_instrument_gateway/package_contract.py` and generated into the API. Run `pnpm gateway:contract:check` to check parity. CI builds the SDK and runs the synthetic, adversarial isolation and timeout tests with an exact container image; this does not certify equipment.

### Local raw-file capture foundation

The SDK provides `output_contract.py` and `CaptureStore` in `output_capture.py`. The capture library itself performs no adapter discovery, instrument method, network request, Record submission or DataAsset creation. The runtime now connects its private snapshots to the receiving contract below. Existing structured-result-only commands retain their workflow; stop/result reconciliation is not removed.

The caller supplies a canonical job UUID, the digest of its approved context and the exact declared output names, media types, size limits and required flags. It explicitly selects an absolute local source directory and relative files. Each selection carries a timezone-aware acquisition timestamp, reported original units, descriptive conversion rules and a separately reviewed file-writing completion reference. Conversion descriptions are provenance only and are never executed. Filenames are portable, case-insensitive collisions are rejected, and required files cannot be silently omitted. Local paths stay in the private journal, not the transferable capture manifest.

`prepare` pins source identities, sizes and content hashes; `capture` checks a quiet interval, copies bounded bytes, hashes both the copy stream and a second source read, then compares the original content digest and source/path identities again. It does not rely on filesystem timestamp precision. It durably records each hash before publishing the snapshot. `inspect` and `open_output` rehash stored bytes. Retrying after a partial copy, lost rename or lost final manifest resumes the same job without rerunning an instrument. A published snapshot remains usable after the producer removes or reuses its original filename. A changed source that was not durably captured is an explicit reconciliation error, not permission to select newer bytes or repeat the experiment.

The outbox uses owner-only directories/files, a cross-process lock, byte/job quotas and atomic, synced journals. There is one incomplete capture at a time, with multiple completed jobs retained for later delivery. No automatic eviction or deletion is implemented. Symlinks, hard links, special files, group/other writers, path traversal, overlapping source/outbox roots and nested filesystem crossings are refused. Recovery of an already completed capture does not need free space or source access. Select the actual canonical local directory; symlink aliases such as `/tmp` on macOS are intentionally not followed.

Defaults are 16 declared files, at most 2,147,483,647 bytes per file, a 4 GiB/100-job outbox, a one-second quiet interval and a 300-second checked capture deadline. Metadata is bounded separately. These checks target supported POSIX **local storage**, not Windows ACLs or remote/mounted vendor filesystems. A blocking OS disk operation cannot be preempted by the checked deadline. The service account and reviewed adapter remain trusted: this library cannot defend against malicious code running as that same account or prove that stable bytes represent a successful experiment.

### Scoped Platform receiving contract

Migration `0054_instrument_outputs` adds pinned intake batches, output receipts and append-only associations. Apply it through normal backed-up deployment, never by changing a development database during acceptance. Downgrade removes these intake/association records, not already stored ResearchFiles, DataAssets or local snapshots; do not downgrade with unfinished deliveries.

Manual/control previews include the exact Project destination, declared filenames, limits, Project-member visibility, draft asset state and pending Record association. Aira proposals require confirmation. Creation pins the approved command, installation, configuration and target provenance into the intake plan; no caller can redirect an upload to another Lab/Project. The receiving authority is the equipment booking's user and must retain both research execution and Knowledge creation access.

Only a file-delivery-capable Gateway may request `file_delivery_version: airalogy.instrument-output-plan.v1` at lease time. The signed job then includes `file_outputs.plan` and `file_outputs.destination`. Missing capability fails before leasing or starting physical work; do not add this flag to an old client as a workaround. The updated runtime advertises it only when an explicit output directory is configured.

After physical completion, `/complete` returns `files_pending: true`. The Instrument Job is completed, but its Action remains waiting and the control session/dependent graph does not advance. Under `/instrument-gateway/v1/jobs/{job_id}/outputs`:

1. `POST /capture` fixes the exact shared capture manifest. A changed retry conflicts.
2. `PUT /{output_id}` streams only that declared file with its exact `Content-Length`, declared `Content-Type` and `X-Airalogy-Content-SHA256`. API permissions are rechecked after streaming and object-storage latency. Unmatched bytes, excess size, unavailable authority or logical-file quotas fail without registering an asset.
3. Successful uploads create a private Project ResearchFile and draft DataAsset version, retaining original reported units/time/offset, server receipt time and installed-version lineage. Retries return the same IDs. Shared blob deduplication does not create scope permissions or bypass quotas. These raw attachments download as non-inline, non-sniffable binary content even if another file gave the shared blob an active media type.
4. `POST /finalize` requires the same capture and all captured files registered. Only then does normal Action progression resume. A cancelled Task is never restarted by a late delivery. Retries do not create assets or repeat instrument commands.

These endpoints require both the authenticated Gateway and original job lease token; they are not general file or Project access. Recovery receipts remain possible after activation expiry/revocation, but not after Gateway credential or receiving-user authority is withdrawn. Receiving does not verify scientific validity, infer samples from filenames/timestamps, submit a Record or overwrite research evidence.

`GET /research-instrument-jobs/{job_id}/outputs` returns current delivery/association state to authorized users. For each output, `POST /{output_id}/associations/preview` and its confirmation endpoint `/associations` bind the preview digest to an exact same-Project Record version/hash, sample reference and prior association ID. Concurrent stale writes conflict; retrying a confirmation does not restore an older association. Reads recheck Record permission and redact restricted associations. Record data remains unchanged.

### Review files and associate an exact Record

In a Research Task's execution ledger, open **Instrument files** on a file-producing Instrument Action. Review the actual delivery state and saved Lab/Project. A completed acquisition may still be awaiting files; resume the original Gateway delivery journal, not acquisition. Files stay private Project draft DataAssets. **Download original** uses current file authorization and audit; originals are attachments, not executable inline previews.

Expand **Original file and provenance** for acquisition time with its reported timezone, server receipt time, reported units/conversions/completion reference, SHA-256 and the immutable DataAsset version ID. These declarations and byte checks are not scientific validation. Do not infer sample identity from filenames or timestamps.

Choose **Associate Record**, select a Protocol in the same Project, then search by Record number or UUID and choose its exact version. Unique accessible options are inherited; larger lists have explicit pagination. Optional sample references are literal operator observations. Preview shows the Record ID/version/content hash and original DataAsset version/checksum. Confirmation appends a new association without editing/submitting the Record, promoting the DataAsset, or deleting the previous association. **Association history** distinguishes current and previous entries; opening a Record goes to that exact report version.

API permissions, not UI visibility, govern read/write access. `GET /research-instrument-jobs/{job_id}/outputs/record-options` takes `protocol_id`, optional `q`, `offset` and `limit` (1–100); permissions including own-only Record access are applied before pagination. `GET .../outputs/{output_id}/associations` paginates immutable revisions and redacts inaccessible Record/sample details. Associating requires current research execution and Knowledge creation authority; authorized read-only users retain file inspection/download without gaining write access.

After a lost confirmation response, retry the **same confirmation**, or use **Check saved state** before editing again. Concurrent changes invalidate stale previews; reconciliation reloads current state and requires a new selection/preview when needed. Refresh failure clears previously displayed file details. AI is not required anywhere in this workflow. Synthetic installed-driver, actual API/storage and browser tests validate software behavior, not real equipment or workstation safety; authorized pilot acceptance remains necessary.

### Automatic delivery and recovery

For an independently reviewed file-producing adapter, add `--output-root /absolute/owned/instrument-exports` to **both** managed startup preview and run commands. The exact canonical directory and its local identity enter the confirmation digest. Its root must not overlap the private `instrument-output-outbox` next to `state.json`. The installed command's declarations must exactly match the signed receiving plan. The generic runtime accepts `AIRALOGY_GATEWAY_OUTPUT_ROOT`, but this never bypasses managed installation authority.

`execute` returns `InstrumentResult(result=<ordinary JSON object>, files=[...])` for a file-producing command. Each file uses the selected-source fields above plus a lowercase `sha256` computed by the reviewed driver from the closed original **during acquisition, before returning**. The runtime does not infer files by scanning a directory. Optional omissions are explicit; required files cannot be omitted. The driver remains responsible for genuine completion and original units. A hash is byte identity, not scientific validation. A command without file declarations can continue returning an ordinary dictionary.

The runtime saves the result, original hashes and selection in its private journal, captures the originals while maintaining the lease, and then reports physical completion. Only durable, rehashed snapshots go to the fixed authenticated upload endpoints; server-provided URLs are never followed. It checks the signed destination, declarations, deterministic output IDs, content/provenance and stable ResearchFile/DataAsset IDs before accepting a receipt. Files remain draft research assets and no Record is automatically edited or submitted.

Lost completion/upload/finalization responses resume the same receipts with `--recover`, the original activation, request, credentials and `--output-root`. After a complete snapshot exists, the source may be absent or reused. This receipt-only process does **not import or initialize the driver**, fetch a new activation or lease new work. It does still verify the original installed package/SDK/configuration. A pending upload whose permissions are withdrawn remains local until authority is legitimately restored. Invalid adapter completion, changed uncaptured originals, expired pre-completion authority or a stop request during capture require explicit reconciliation; deleting the journal or rerunning acquisition is not a recovery method.

The runtime clears its active journal only after the Platform acknowledges all files and finalization. Retained local snapshots are not automatically evicted, even after successful delivery. Review storage retention separately. These behaviors are tested with temporary local files, actual binary HTTP, installed independent processes and the real scoped API/database/object store; no vendor application, instrument or private laboratory files are used.
