# Owned fixed browser workflow adapter contract

This public synthetic fixture teaches the Python adapter boundary, not how to discover or control a vendor instrument. Implement `OwnedInterfaceWorkflow(client)` and `create_adapter(config_path)` in `source/interface_workflow.py` using the trusted SDK's `InstrumentAdapter` and `interface_process.InterfaceProcessClient`. The factory must reject `None` and use `InterfaceProcessClient.from_file(config_path)` unchanged. Do not create executable paths, workflows, selectors, credentials or subprocesses.

The independently prepared private worker configuration fixes the reviewed workflow, Node/dependency/browser files and evidence destination. It is NOT included in this development specification and is never opened by the offline tests. Changing any of those identities requires independent review and normal installation/qualification gates. A passing source test is not installation or hardware authority.

## Fixed command and worker methods

- Support exactly `interface.workflow.run` version `1.0.0`, with empty arguments, a canonical Job UUID and a job timeout. Unsupported commands/arguments are rejected.
- `client.call("probe")` returns `data` containing `source_kind: "file"`, a strict boolean `initial_matches` and an actual `target` identity mapping. Reject other source kinds or malformed diagnostics. `identity()` returns that mapping unchanged. `preflight(job)` reports `interface.initial` from that boolean, not a fabricated success; `operator_present` and `emergency_stop_available` are both false.
- `confirm(job)` returns `None`: there is no operator attestation.
- `client.call("execute", job_id=job.job_id, timeout_seconds=min(20, job.timeout_seconds), stop_event=stop_event)` runs the already fixed workflow once. The SDK independently checks the pinned runtime, exact Job/digest correlation, cancellation and bounded I/O; the worker checks initial state, each action and the predeclared success conditions. There are no dynamic command/selector arguments.
- A successful response contains `job_id`, a 64-character lowercase hex `workflow_digest`, and `data: {source_kind: "file", values: {"result.value": TEXT}}`. Require exact Job correlation and exactly that selected text field. Convert only a finite numeric string; reject boolean/numeric/non-text values, NaN and infinity. Do not hard-code the simulator's result: independent tests vary the readback.
- Return exactly `operation_id` (the Job UUID), `workflow_digest` from the response, parsed `value`, `unit: "synthetic_unit"`, and `simulation_only: true`.

Propagate worker failure/uncertainty without retry, reset or another execute. Forward the actual stop event. `safe_stop(job, reason)` raises `RuntimeError`: local process termination is not a qualified physical stop. The outer Gateway owns durable receipt recovery/reconciliation; this adapter must not invent its own replay path.

The fixed tests inject an independent fake worker and require the installed SDK factory boundary. They open no browser or network connection. The manifest remains low-risk with `interface.initial`, never read-only, and always simulation-only with no tested hardware. No native, live URL, visual or arbitrary desktop execution is authorized. Real vendor semantics not supplied here must remain missing information.
