# Reviewed instrument HTTP control

`HttpControlClient` is a reusable SDK transport for independently documented JSON operations. It supports fixed GET, POST and PUT operations, sharing the [pinned HTTP/TLS transport](./instrument-http-interface.md) with the read client. It is not a device adapter, source approval, equipment permission, discovery service or safety controller. Do not infer physical semantics from an HTTP method.

## Separate local configuration

Read-only configuration cannot enable this client. A local operator must select a separate private configuration and explicit operation names:

```json
{
  "schema": "airalogy.http-control-config.v1",
  "origin": "https://reader.example.test:443",
  "address": "192.0.2.20",
  "allow_plaintext": false,
  "headers": {},
  "enabled_operations": ["state", "configure", "start", "stop"]
}
```

These are illustrative addresses, not an instrument to contact. Apply the same POSIX owner-only file/ancestor checks, pinned IP, hostname-verified TLS, explicit plaintext opt-in and instrument-only authentication rules as the read backend. No environment proxies, cookies, redirects, authentication refresh or automatic retries. Configuration changes require a new reviewed installation/activation; do not place real configuration, credentials or addresses in model materials, packages or public issues.

The reviewed source fixes the operation's method, path, exact body/query field names, byte bounds and accepted status codes. Local configuration may select only a subset of those operations; neither job arguments nor model output can add destinations or methods to an already reviewed package. This is not a sandbox against hostile Python running under the operator account.

```python
from airalogy_instrument_gateway.http_control import HttpControlClient, HttpControlOperation

client = HttpControlClient.from_file(config_path, {
    "state": HttpControlOperation("GET", "/v1/state"),
    "configure": HttpControlOperation("PUT", "/v1/parameters", ("operation_id", "sample_count")),
    "start": HttpControlOperation("POST", "/v1/start", ("operation_id",), statuses=(202,)),
    "stop": HttpControlOperation("POST", "/v1/stop", ("operation_id",)),
})
# Construction does not connect. Invoke only inside an independently authorized
# adapter operation with the exact SDK job.job_id and reviewed parameter bounds.
receipt = client.call("start", {"operation_id": job.job_id}, stop_event=stop_event)
```

These paths describe the owned reference below, not vendor endpoints. Bodies are JSON objects with exact top-level keys, at most 64 KiB, depth 16 and bounded collections. GET accepts no body. Query fields follow the read backend's exact-key encoding rules. The adapter must additionally validate vendor types, ranges, units and operation correlation; the transport does not infer them. The trusted source can select 200, 201 or 202 with a strict JSON-object response, capped at 1 MiB. Empty 204 responses, streaming/binary protocols and dynamic paths are not supported here.

## Acceptance is not completion

`receipt.status`, original `raw` bytes, `sha256`, parsed `data` and local `received_at` describe an HTTP receipt, not acquisition time or scientific completion. A 202 response means only request acceptance. Independently read back the exact operation ID, parameters, completion state and output. Detect ownership changes and conflicting operations before and after critical observations. A vendor's atomic device-side checks remain necessary; separate HTTP observations are not atomic interlocks.

`HttpControlError` contains a fixed code and conservative `request_may_have_been_sent`, never private addresses, credentials or response text. After a write may have been transmitted, timeout, cancellation, lost response or invalid JSON must not cause a new start. Canceling I/O or closing a socket is not stopping equipment. Device-specific stop and state reconciliation belong in the reviewed adapter, using a separately usable stop request rather than the already-cancelled acquisition event. The helper itself stores no physical-operation journal: existing Instrument Job, Gateway journal, lease, local confirmation, preflight and uncertain-stop rules remain mandatory.

## Runnable owned reference

Start only the bundled loopback simulation, which controls no physical device:

```bash
python3 apps/instrument-gateway/examples/http-controlled-reader/simulator.py
```

Use its printed origin and `127.0.0.1`, explicit plaintext opt-in, no credentials, and exactly `identity`, `state`, `configure`, `start`, `result`, `stop` in `enabled_operations`. The service represents one acquisition per fresh instance and has no implicit reset. Its published package and output are permanently simulation-only, not eligible for real-equipment activation.

Build without AI:

```bash
pnpm gateway:package build \
  --manifest apps/instrument-gateway/examples/http-controlled-reader/manifest.json \
  --factory http_controlled_reader:create_adapter \
  --file source/http_controlled_reader.py=apps/instrument-gateway/examples/http-controlled-reader/source/http_controlled_reader.py \
  --file tests/test_http_controlled_reader.py=apps/instrument-gateway/examples/http-controlled-reader/tests/test_http_controlled_reader.py \
  --file licenses/LICENSE.txt=LICENSE \
  --output /absolute/private/http-controlled-reader.zip
```

For separately authorized [source drafting](./instrument-source-authoring.md), generate a fixed independent specification with `node scripts/instrument-authoring-example.mjs /absolute/private/http-controlled-spec.json --http-controlled-reader`. Use an exact verified SDK wheel containing `http_control`; older wheels with the same development version are not interchangeable. Generation makes no model call or equipment connection. Non-read-only source consent, source review, exact installation, controlled qualification and activation remain separate.

Software tests use an independent fake client, actual loopback HTTP, isolated package tests and two independent installations of identical package bytes. Disposable API/PostgreSQL acceptance uses clearly synthetic qualification-policy records and the installed driver: parameter configuration, a single start, correlated result, then lost Platform completion receipt and journal-only recovery without loading the adapter or contacting the service again. No paid-model quality, vendor protocol, physical safe stop, real device or second physical installation has been verified. RFC #5 remains open for those requirements and the GUI/OS paths.
