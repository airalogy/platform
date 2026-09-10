# Install the local Instrument SDK

The standalone `apps/instrument-gateway/bootstrap.py` installs the dependency-free official SDK into a **new private directory**, without pip, installation hooks, administrator access, global PATH changes or service registration. Installation never imports SDK/adapter code, pairs a Gateway, launches instrument software or starts jobs. This is an operator-assisted POSIX bootstrap, not a Windows installer or unattended service manager.

## Establish trust first

Use maintained Python 3.11+ and an independently trusted GitHub CLI with the required attestation flags. Obtain the bootstrap itself from a reviewed trusted checkout, or have the operator verify the released `airalogy-instrument-bootstrap.py` **before executing it**. A script cannot establish trust in itself. Official public releases attach the SDK wheel, bootstrap and `airalogy-instrument-attestations.jsonl`; do not treat examples or an unsigned local build as an available signed release.

Independently choose the exact stable release tag, its 40-character source commit and the wheel SHA-256. Do not use `latest`, a branch, a mutable download URL or the selected file's own checksum as proof of origin. The bootstrap supports only `airalogy/platform` and its `.github/workflows/release.yml`, not arbitrary mirrors/fork signers or prereleases. Existing reviewed source/manual installation remains separate.

For example, after replacing the illustrative version, paths and commit:

```bash
gh attestation verify /absolute/downloads/airalogy-instrument-bootstrap.py \
  --hostname github.com --repo airalogy/platform \
  --signer-workflow airalogy/platform/.github/workflows/release.yml \
  --source-ref refs/tags/v0.1.0 --source-digest <40-character-release-commit> \
  --signer-digest <40-character-release-commit> \
  --cert-identity https://github.com/airalogy/platform/.github/workflows/release.yml@refs/tags/v0.1.0 \
  --deny-self-hosted-runners
```

The installer delegates signature verification to the [official GitHub CLI](https://cli.github.com/manual/gh_attestation_verify), enforcing repository, workflow, certificate identity/issuer, exact source ref/commit, signer commit, hosted runner and SLSA provenance. A hash identifies bytes; a verified signature establishes the specified build origin, not software quality, ongoing release approval or physical safety. Review release withdrawal/security notices independently; this tool has no automatic revocation feed.

## Preview and install

Choose an existing service-account-owned `0700` parent without symlink ancestors and a **new** child directory. Keep SDK versions, development workspaces, runtime credentials/journals and original data in separate directories. A parent containing `gateway.json` or `state.json` is refused; this is a guard, not proof that another service account/path is safe to modify.

```bash
python3 -I -S -B /absolute/downloads/airalogy-instrument-bootstrap.py preview \
  --wheel /absolute/downloads/airalogy_instrument_gateway-0.1.0-py3-none-any.whl \
  --wheel-sha256 <independently-verified-wheel-SHA256> \
  --release-tag v0.1.0 --commit <40-character-release-commit> \
  --destination /absolute/private/sdk-installs/sdk-0.1.0 \
  --online-verification
```

Preview reads selected files and executable identities only. It does not create files, contact GitHub or claim verified provenance. Review destination, version/commit, hashes, Python/verifier identities and network choice. Repeat the **same inputs** with `install` instead of `preview`, adding `--install-authorized --confirm-digest <preview-confirm-digest>`. Installation rechecks inputs, verifies the exact copied wheel, then exclusively creates the destination. No dependency download, package-provided hooks, `.pth`, native wheel or dependency-bearing SDK is accepted.

Online verification contacts GitHub/Sigstore through the trusted CLI; it does not upload Lab materials or contact Platform/equipment. For offline installation, omit `--online-verification` and supply all three: `--bundle <selected-attestations.jsonl> --trusted-root <trusted-root.jsonl> --trusted-root-sha256 <independently-approved-root-SHA256>`. An administrator can obtain roots using `gh attestation trusted-root` on a trusted connected host; transport and independently approve them before use. Never accept a trust root merely because it accompanies a package. Mixed online/offline options are refused. Missing/invalid proof, unexpected verified subject, verifier timeout or unsupported flags stop installation; there is no unsigned fallback.

Limits: 64 MiB wheel, 128 MiB expanded SDK, 2,048 wheel files, 4 MiB proof/root/output, 90-second verifier deadline. The installer retains the original wheel, verification output, exact extracted files, bootstrap and a final timestamped `receipt.json`. File and directory writes are flushed before reporting success. It does not copy local credentials, install a vendor adapter or select an active version.

## Launch, inspect and maintain

An explicit launch rechecks retained file hashes, rejects missing/unexpected files and requires the pinned Python interpreter. It starts only a named SDK entry point with an isolated standard-library + SDK import path, without site hooks or bytecode writes:

```bash
python3 -I -S -B /absolute/private/sdk-installs/sdk-0.1.0/airalogy-instrument-bootstrap.py \
  launch --destination /absolute/private/sdk-installs/sdk-0.1.0 \
  -- setup --root /absolute/private/gateway-service

python3 -I -S -B /absolute/private/sdk-installs/sdk-0.1.0/airalogy-instrument-bootstrap.py \
  launch --destination /absolute/private/sdk-installs/sdk-0.1.0 \
  -- author serve --workspace /absolute/private/adapter-development
```

Those existing private service/development directories must be separate. Continue [setup/pairing](./instrument-integration.md#local-browser-setup) or [source development](./instrument-source-authoring.md#local-browser-development-guide). Other named entries are `pair`, `package`, `installation`, `activation` and `gateway`; their existing authorization and safety requirements still apply. Launching an execution entry is a separate operational action, never a consequence of installing or opening a guide.

Use `inspect --destination <installed-directory>` to rehash the installation. It reads local receipts and does **not** re-establish cryptographic provenance or current process liveness. A completed retry with the original installation inputs checks retained bytes and returns the same installation without another network call. Missing final receipts or altered files remain incomplete/invalid: preserve them for inspection; do not overwrite or silently repair them. A crash may leave a private incomplete destination. The tool never automatically deletes it or any original data.

Upgrades use a separate version directory and fresh verification, never an active pointer or in-place replacement. Interpreter changes also require a new reviewed installation. Do not remove an SDK used by a running process; establish the actual process/job/physical stop state and retention requirements first. Service supervision, automatic updates/uninstall, OS ACL installers and recovery from hostile same-account programs remain outside this bootstrap. Hashes and owner-only files cannot defend against a malicious administrator or a program that can rewrite both the installed code and its receipts.

## Verification evidence

Ordinary SDK CI tests malformed/tampered inputs, fixed verification flags, output bounds, interruption, idempotency and actual isolated launch/HTTP behavior against a built SDK. Positive local tests inject the verifier response; a real GitHub CLI negative test rejects an unsigned offline fixture. Official public release CI additionally verifies the newly attested wheel with the actual certificate/source policy and launches both empty local guides before attaching artifacts. That release gate must actually pass for a released version; it is not evidence of a release that has not run, real workstation acceptance or instrument safety.
