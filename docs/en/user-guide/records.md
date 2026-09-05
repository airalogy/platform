# Records

A Record stores one use of a Protocol: the entered values, completed steps and checks, annotations, files, provenance, and revision history supported by that Protocol.

## Create a Record

1. Open the target Protocol and choose the recording action.
2. Confirm the Protocol version and the Lab and Project context.
3. Complete required fields with the units and formats requested by the form.
4. Attach files through the provided upload control so Platform can retain a stable file reference.
5. Resolve validation messages, then save or submit according to the interface.

Do not put credentials, private keys, or unrelated personal data in a Record. Follow your organization’s approved naming, retention, and sensitive-data procedures.

## Validation and revisions

The form opens on the field panel, with Aira available separately when enabled. **Save draft** stores unfinished work on this device; it is not a submitted Record. Submission asks you to confirm the destination and Protocol version. After successful submission, **View saved Record** opens that exact report; **Add another** starts a fresh Record.

Validation feedback remains beside the fields. Server validation failures also appear in a persistent summary with links to the affected fields. Your entered values remain available. If a connection times out, check the Record list before retrying: the server may have saved the request even when the confirmation did not arrive.

The form is generated from the Protocol’s structured fields. Validation can detect missing values and incompatible types, but it cannot decide whether an observation is scientifically correct. Review unexpected values before submission.

When edits are allowed, Platform retains revision information according to the active feature and policy. Use annotations or the designated reason field to explain material corrections. Do not overwrite a value merely to make results look cleaner; preserve the original observation and document the correction.

## Files

Uploaded files are stored through the configured storage backend while the Record keeps a stable file identity. A Lab may use MinIO, object storage, or another operator-managed backend. Always verify that an upload completed before deleting the source copy, and follow the operator’s backup policy for irreplaceable data.

## Review and reuse

Use Project, Protocol, recorder, and time context when comparing Records. A field name shared by different Protocol versions does not by itself guarantee identical meaning or units.

For moving existing tabular data into Records or producing an authorized archive, see [Import and export](./import-export).
