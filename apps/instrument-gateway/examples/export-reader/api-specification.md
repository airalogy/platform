# Local export inbox — fixed collector specification

This is a read-only local file collector, not vendor software or live equipment control. Fixed tests create synthetic files only. Source/installation/qualification/activation approvals remain separate; no tested hardware combination is claimed.

Implement `ExportInboxReader(client)` and `create_adapter(config_path)` in `source/export_reader.py`. Use the existing SDK `ExportReadClient` and `read_export_config`. The factory validates the explicitly selected private config and pins its export directory without scanning it, connecting to an instrument or reading a result. Do not replace these guards with arbitrary filesystem access.

The sole command is `export.files.collect@1.0.0` with exactly `export_id` (canonical UUID) and `sample_reference` (explicit bounded nonempty string). `supports()` only compares the command/version. `execute()` rejects extra argument keys and unsupported commands, delegates to `client.read(export_id, sample_reference, stop_event=stop_event, timeout_seconds=20)` and returns the resulting `InstrumentResult` unchanged. Never produce a canned measurement, infer scientific success, choose the latest file or create a completion receipt yourself.

The reviewed output declarations are fixed:

- `result.csv`, `text/csv`, required, maximum 1,048,576 bytes.
- `export.json`, `application/json`, required, maximum 131,072 bytes.

The reviewed producer/operator closes the original files and atomically publishes `<root>/<export UUID>/export.json` last. The SDK validates `airalogy.export-completion.v1`, exact export/sample identity, `export_complete: true`, timestamps with timezone, original units and conversion evidence, byte sizes and SHA-256 values. It reads only declared basenames, checks private source identity/permissions, rejects links and changed bytes, and returns file evidence for the existing scoped OutputDelivery path. This receipt confirms exported bytes, not experiment success. See the public export-interface guide for its full schema.

`identity()` calls `client.identity()` afresh and returns exactly: `identity_reference: "local-export-inbox:<device>:<inode>"`, `firmware: "not-observed"`, `application: "airalogy-export-inbox"`, `application_version: "1.0.0"`, `driver_version: "1.0.0"`, `os_version: platform.system() + ":" + platform.release()`. It identifies this local source, not manufacturer hardware; never invent vendor firmware.

`confirm()` and `safe_stop()` return `None` and perform no operation: this collector has no physical process. Cancellation is cooperative through the stop event; the Gateway must still join the active worker before acknowledging a stop. This is not a general hardware safe-stop implementation. Local configuration, paths and production files stay out of model materials and package payloads; no HTTP, vendor SDK, shell, file writes, directory discovery or automatic Record submission is authorized by this reference.
