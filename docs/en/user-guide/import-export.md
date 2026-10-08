# Import and export

Import and export move research data across a system boundary. Confirm the destination, authorization, schema, and retention requirements before starting.

## Import Records from CSV

Where bulk upload is available, each CSV row creates a new Record under the selected Protocol. It does not overwrite existing Records.

1. Open the Records page for the target Protocol.
2. Choose **Bulk upload**, then **Download CSV template**. The template contains only canonical headers from the current Protocol version, not fabricated observations.
3. Expand the field reference, follow the types, required fields, ranges and enumerations, and save as UTF-8 CSV (BOM is supported).
4. Select the file and choose **Validate file**. Correct the reported fields and lines, then validate again. Preview does not create Records.
5. Check the destination Protocol, version and count, acknowledge the operation, and choose **Confirm import**. Inspect representative saved Records afterward.

Templates use explicit paths such as `var.sample_id`. **Variable IDs must match the Protocol exactly, including case; display titles are not aliases.** There is no guessed or legacy-table mapping. Column order may vary and optional columns may be omitted. Unknown columns (even entirely empty ones), duplicate columns and duplicate paths to the same field are rejected. Direct IDs such as `sample_id` and `data.var.sample_id` remain valid existing API syntax.

Supported paths can also address quizzes, step/check status and annotations, metadata, and an optional `record_id`. Values are converted and validated against the current Protocol field types, including explicitly declared defaults. Complex fields such as arrays or objects must follow their JSON structure; file references also require current access permission.

```csv
var.sample_id,var.amount
S1,12
S2,18
```

This example only applies to a Protocol defining `sample_id` and `amount`. Do not import explanatory rows or examples as research observations.

- Numeric `0` is an observation, not a blank. Do not replace missing observations with zero, `false`, or inferred values.
- Resolve spreadsheet errors such as `#REF!` against the original source. Platform does not repair scores, discard columns, or invent observations.
- Errors are grouped by field. CSV line numbers include the header and identify the starting file line for multiline records. An invalid row prevents the entire batch from being written.
- CSV/TSV limits are 10,000 records and 512 columns; ordinary import files are limited to 20 MiB. Split larger datasets into batches.
- A preview confirmation expires after 20 minutes and is bound to the file, Protocol version and user. Changes require a fresh preview; confirmation still rechecks current permissions, data and resource conditions.
- `.aira` archives retain their separate validated archive-import flow without CSV preview. Existing API clients may still submit imports directly, subject to data validation and permission checks.

## Download a Protocol

Choose **Download → Airalogy archive (.aira, recommended)** to share a published Protocol with its resources and a validated manifest. Choose **Source package (.zip)** for ordinary source editing. Both formats represent the requested Protocol version; neither exports database Records or grants recipients access to Platform. `.aira` is a standard archive with file hashes, not a renamed ZIP. Environment secrets, interpreter caches and generated runtime files are excluded. An invalid source package blocks `.aira` export; the ZIP option remains available for inspection and repair. Existing integrations using the legacy ZIP download URL continue to work.

## Export Records

Authorized Lab and Project roles can request scoped Record exports where the feature is enabled. Available packages may include `.aira`, JSONL, single-schema CSV, attachments, and optional revision history. The export represents the selected scope and snapshot; it does not grant new access to recipients.

Export files can contain unpublished or sensitive research data. Store them only in approved locations, transmit them through approved channels, and delete temporary copies according to policy. Download links may expire; regenerate from Platform rather than redistributing an old link.

## Verify every transfer

- Record the source scope, Protocol versions, filters, export time, and requester.
- Compare counts and key identifiers before and after transfer.
- Inspect files and non-scalar fields that CSV cannot represent faithfully.
- Keep a checksum or immutable archive when the transfer supports audit or recovery.
