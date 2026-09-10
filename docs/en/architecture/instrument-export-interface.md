# Collecting completed instrument exports

The reusable `ExportReadClient` supports equipment workflows that deliver local files instead of an API response. It reads an **explicitly selected completed export**, preserves original bytes and provenance, and returns the existing `InstrumentResult` file contract. The governed Gateway runtime then delivers draft DataAssets through the existing scoped intake. This is not device discovery, a folder synchronization service, a CSV parser or permission to operate an instrument.

## Producer and completion contract

An independently reviewed producer bridge or authorized operator must first establish how the vendor software reports export completion. Close the data files, assign an explicit export UUID and sample reference, calculate their original sizes/hashes, and **atomically publish `export.json` last** in that UUID's directory. Use temporary files in the same filesystem and the producer's appropriate durability procedure. Do not infer completion from a quiet folder or merely finding a CSV. A reused UUID must never be overwritten.

```text
<explicit-local-export-root>/
  <export-UUID>/
    result.csv
    export.json
```

The receipt is bounded UTF-8 JSON with exactly these fields. This is a template: replace the UUID, sample, timestamps, byte count, digest, units and completion evidence with actual observations. The digest placeholder is intentionally not valid input.

```json
{
  "schema": "airalogy.export-completion.v1",
  "export_id": "00000000-0000-4000-8000-000000000001",
  "sample_reference": "sample-A",
  "export_complete": true,
  "completed_at": "2026-09-11T12:30:00+08:00",
  "files": [
    {
      "name": "result.csv",
      "byte_size": 26,
      "sha256": "<64 lowercase hexadecimal characters for the original bytes>",
      "captured_at": "2026-09-11T12:29:00+08:00",
      "original_units": ["signal: original instrument unit"],
      "conversion_rules": [],
      "completion_reference": "Reviewed producer export-completion evidence"
    }
  ]
}
```

Each file entry has exactly the fields above. Names must match the package's reviewed portable basenames; no paths, URLs, globs, reserved names or duplicate names are accepted. All required outputs must be present. `export.json` is reserved and added as a raw output by the reader, not listed in its own `files`. Timestamps retain the supplied timezone; units/conversion evidence are retained without conversion. A sample reference is an explicit producer/operator assertion, not automatic resolution to a Platform Sample. Receipt completion means **export bytes are ready**, not that an experiment or scientific hypothesis succeeded.

## Private local configuration

Configuration has exactly `schema`, `root` and `root_identity`:

```python
from airalogy_instrument_gateway.output_capture import source_root_identity

root = "/absolute/private/export-inbox"  # Explicit operator selection
configuration = {
    "schema": "airalogy.export-read-config.v1",
    "root": root,
    "root_identity": source_root_identity(root),
}
```

Store this JSON in a service-account-owned `0600` regular file inside a private `0700` directory. The root must be an absolute non-root POSIX directory, with no symbolic-link ancestors, and retain its pinned device/inode. Source directories/files must belong to the service account and must not be writable by other users; use `0700`/`0600` to keep exports private. Symlinks, hard-linked files, special files and filesystem crossings below the root fail closed. Do not weaken another user's export permissions: use a separately reviewed handoff into the service account's local inbox when needed. Configuration changes require new installation/activation review; never put local paths or production exports into package payloads, issues or model materials.

The helper only inspects the selected root's identity during construction; it does not enumerate its contents. During execution it waits only for `<root>/<export_id>/export.json`. It rejects a present malformed/partial receipt immediately, mismatched export/sample identity, excess sizes, changing bytes or digest mismatch. File identities and the receipt are rechecked before returning. Source files are never modified or deleted.

There are at most 16 outputs including the receipt, which must be required JSON and at most 128 KiB. Each package fixes file quotas; the SDK defaults to a 64 MiB total quota. One read per client is allowed. Wait/read deadlines are 0.01–120 seconds with cooperative cancellation between filesystem operations. **This does not hard-preempt a stalled operating-system filesystem call**; use reviewed local storage, not a network-mounted inbox. Gateway stop acknowledgment still requires its worker to exit. Cancelling collection does not stop an independently running vendor application or physical experiment.

## Source-included collector and Aira drafting

The hand-written `examples/export-reader` package needs no AI. Its sole `export.files.collect@1.0.0` command takes exactly `export_id` and `sample_reference`. It reads required `result.csv` (1 MiB) and `export.json` (128 KiB), with a 20-second reader deadline inside a 30-second command bound. The result reports export/sample identity, receipt digest, file count/size and `scientific_validation: false`, not a fabricated measurement.

Build the package from the repository root into a new private file:

```bash
pnpm gateway:package build \
  --manifest apps/instrument-gateway/examples/export-reader/manifest.json \
  --factory export_reader:create_adapter \
  --file source/export_reader.py=apps/instrument-gateway/examples/export-reader/source/export_reader.py \
  --file tests/test_export_reader.py=apps/instrument-gateway/examples/export-reader/tests/test_export_reader.py \
  --file licenses/LICENSE.txt=LICENSE \
  --output /absolute/private/export-reader.zip
```

Follow the existing [package inspection, isolated tests, installation, qualification and activation workflow](./instrument-adapter-packages.md). Select the exact trusted SDK wheel containing `export_read`, not just the same development version number. The observed target is this local inbox/reader; `firmware: "not-observed"` explicitly does not establish live vendor-hardware identity. Qualify its data-collection scope separately; this package cannot qualify physical instrument commands.

The installed activation launcher needs the same selected inbox as its explicit `--output-root`, separate from its private journal/outbox. A successful command uses the actual signed job's output plan, captures durable original bytes and transfers only to the authorized Project. Keep the producer files available until capture succeeds. The existing [delivery/recovery workflow](./instrument-adapter-packages.md#automatic-delivery-and-recovery) retains originals/outbox and reconciles lost receipts without reinitializing the driver or rereading the inbox. Record association remains previewed and confirmed separately; no automatic Record submission occurs.

Optional Aira source drafting can use the public collector specification and independent fixed tests:

```bash
node scripts/instrument-authoring-example.mjs /absolute/private/export-spec.json --export-reader
```

This only writes a private input file with synthetic test data; it calls no model and reads no real export. Continue the separately authorized [source-authoring workflow](./instrument-source-authoring.md). The model may change source, not the fixed tests, command/file authority or manifest. Manual build and collection remain available with AI disabled.

## Acceptance and remaining scope

Tests cover exact-ID polling without enumeration, late atomic publication, partial/changed files, hashes/quotas, identity/sample mismatch, traversal/links/permissions and cancellation. The source-included package passes independent fixed tests in the no-network/no-host-mount container. Disposable API/PostgreSQL/object-storage acceptance runs the installed package, compares stored/downloaded original bytes and provenance, then removes only the owned source fixture before receipt-only recovery. This tests the software chain, not vendor semantics or hardware.

No automatic vendor completion bridge, arbitrary-folder import, filename guessing, cross-job export-consumption ledger, Windows ACL/backend or real instrument has been accepted. Delivery is idempotent for the same job; separately confirmed jobs may intentionally create separate draft assets from the same export. A real pilot still needs authorized equipment/software details and independent producer-completion verification. RFC #5 remains open.
