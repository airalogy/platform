# Import and export

Import and export move research data across a system boundary. Confirm the destination, authorization, schema, and retention requirements before starting.

## Import Records from CSV

Where bulk upload is available, each CSV row creates a new Record under the selected Protocol. It does not overwrite existing Records.

1. Open the Records page for the target Protocol.
2. Choose **Bulk upload** and select a `.csv` file.
3. Review validation results before confirming the import.
4. Check the created Record count and inspect representative Records.

Column names can use direct variable names such as `sample_id` or explicit paths such as `var.sample_id`. Supported paths can also address quizzes, step/check status and annotations, metadata, and an optional `record_id`. Values are converted and validated against the current Protocol field types.

```csv
sample_id,amount,metadata.source
S1,12,legacy-study
S2,18,legacy-study
```

If a row contains an unknown field, invalid type, or missing required value, correct the source CSV and repeat the validation. Keep the original source and a record of the mapping used for migration.

## Export Records

Authorized Lab and Project roles can request scoped Record exports where the feature is enabled. Available packages may include `.aira`, JSONL, single-schema CSV, attachments, and optional revision history. The export represents the selected scope and snapshot; it does not grant new access to recipients.

Export files can contain unpublished or sensitive research data. Store them only in approved locations, transmit them through approved channels, and delete temporary copies according to policy. Download links may expire; regenerate from Platform rather than redistributing an old link.

## Verify every transfer

- Record the source scope, Protocol versions, filters, export time, and requester.
- Compare counts and key identifiers before and after transfer.
- Inspect files and non-scalar fields that CSV cannot represent faithfully.
- Keep a checksum or immutable archive when the transfer supports audit or recovery.
