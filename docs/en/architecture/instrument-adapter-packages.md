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

In **Lab → resource library → Instrument Gateways → Lab adapter packages**, an Owner/Manager can select the locally tested ZIP, preview its commands/provenance/file hashes and confirm the exact content and Lab destination. The API performs no imports, builds or driver execution. Files are Lab-visible to members, not public; never package credentials, workstation configuration secrets or unapproved customer material.

The preview binds the authenticated actor, Lab, import identity and archive/manifest hashes. Confirmation repeats inspection and permissions. Concurrent imports of the same Lab/package/version reuse one immutable release and logical ResearchFile; different content requires a new version. A lost-response retry does not duplicate quota or revive a revoked version. Package lists are paginated.

Download the exact archive for independent code, origin, license and dependency review. Downloads reuse short-lived ResearchFile tokens, fresh authorization and access audit. Approval requires an explicit acknowledgement, reason, preview and confirmation; concurrent/stale reviews fail. An append-only review history retains each decision. Source approval is an organizational assertion, not a cryptographic signature or proof of honest package-authored tests. Revocation is terminal for that version, but does not uninstall local software or stop a running instrument; coordinate those actions separately. There is no public catalog or runtime credential access to this management API.

Migration `0050_instrument_adapter_packages` adds release and review records. Use normal backed-up deployment procedures; software acceptance uses only disposable databases. Downgrade removes catalog/history, not the stored ResearchFile archive and not any locally installed software.

### Not yet delivered

Platform-authorized installation plans and receipt synchronization, exact equipment/Gateway/package/configuration binding, independent qualification, active-version switching/rollback/revocation and instrument-file return still need their governed workflows. The inactive local receipt is not a replacement for those gates. Real software exploration and real hardware acceptance need an authorized pilot. See the [integration support matrix](./instrument-integration.md#support-matrix).

The standard-library contract is authored in `apps/instrument-gateway/src/airalogy_instrument_gateway/package_contract.py` and generated into the API. Run `pnpm gateway:contract:check` to check parity. CI builds the SDK and runs the synthetic, adversarial isolation and timeout tests with an exact container image; this does not certify equipment.
