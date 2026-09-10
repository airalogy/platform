# Documented instrument HTTP reads

The Gateway SDK provides a reusable `HttpReadClient` for **explicitly selected, independently reviewed GET/JSON endpoints**. It removes repeated transport code from hand-written or Aira-drafted adapters. It is not device discovery, an arbitrary HTTP tool, a network sandbox or permission to contact equipment. An HTTP GET can have physical effects; verify endpoint semantics before approving any access.

## Configuration and authority

The reviewed adapter fixes operation names, paths, query fields and response limits. The local operator separately selects the service origin, numeric IP and instrument-specific credentials. Job arguments cannot select a URL, path or authentication header.

Configuration has exactly these fields (illustrative values only):

```json
{
  "schema": "airalogy.http-read-config.v1",
  "origin": "https://reader.example.test:443",
  "address": "192.0.2.20",
  "allow_plaintext": false,
  "headers": {}
}
```

Store the real configuration in an absolute, service-account-owned `0600` regular file inside a private `0700` POSIX directory without symlink ancestors. Do not put real addresses, tokens or configuration in model materials, package payloads, issues or job arguments. Only explicit `Authorization` and `X-API-Key` headers are accepted; use an instrument-only credential, never a Platform Gateway/development/installation token. Known Platform token patterns are rejected, but secret detection is not comprehensive. Configuration changes require the existing new installation/activation review; installed configuration is digest-bound.

The IP is pinned independently of DNS. The origin determines the Host header, TLS SNI and certificate hostname check; IP-literal origins must match the selected IP. TLS uses Python's default trusted CA configuration with certificate and hostname verification, with no insecure TLS option. An administrator may maintain a private CA trust store on the workstation. Plain HTTP requires explicit `allow_plaintext: true`, including loopback: it provides neither credential confidentiality nor server authentication and needs a separately approved test/network policy. No environment proxy, redirect, cookie jar, credential refresh or automatic retry is used. See Python's [HTTP client](https://docs.python.org/3/library/http.client.html) and [TLS context](https://docs.python.org/3/library/ssl.html#ssl.create_default_context) documentation for the underlying transport.

## Reviewed adapter code

```python
from airalogy_instrument_gateway.http_read import HttpReadClient, HttpReadOperation

client = HttpReadClient.from_file(config_path, {
    "identity": HttpReadOperation("/v1/identity", max_response_bytes=4096),
    "result": HttpReadOperation("/v1/result", ("sample_id",), 4096),
})
# Construction validates private configuration but makes no connection.
# Call only inside a separately authorized identity check or execution:
response = client.get("result", {"sample_id": "sample-A"},
                      timeout_seconds=3, stop_event=stop_event)
```

The paths above belong to the synthetic reference, not a vendor API. Paths are fixed ASCII segments, not templates or encoded traversal. Query keys must match the reviewed set exactly; values are bounded and encoded. Each client allows one call at a time. Deadlines are 0.1–30 seconds; the cancellation watcher interrupts local I/O, including stalled headers and body reads. Operating-system scheduling is not a hardware real-time guarantee.

Only HTTP 200 with uncompressed UTF-8 JSON-object content is accepted. Body limits are 1 byte–1 MiB (default 64 KiB). Duplicate keys, non-finite numbers, excessive nesting, ambiguous framing, truncation and oversized bodies fail. The adapter must still validate its result schema, sample identity, units and scientific completion criteria. `response.raw` preserves the received JSON bytes, `sha256` identifies those bytes and `received_at` is local receipt time, **not acquisition time** or a scientific-success attestation. The helper does not upload raw files or create DataAssets; use the existing [explicit output delivery contract](./instrument-adapter-packages.md#automatic-delivery-and-recovery) when needed.

`HttpReadError.code` is sanitized and does not include credentials, addresses or the response body. `request_may_have_been_sent` is conservative: after a request starts, failure/cancellation cannot prove the server did nothing. Do not retry an acquisition based on this flag. Closing a socket is not a physical safe stop; an actual adapter must implement and independently qualify its hardware-specific stop/interlock behavior. This helper cannot prevent reviewed Python code from using other I/O libraries; it is not an execution sandbox.

## Runnable synthetic reference

From the repository root, start the owned loopback-only service:

```bash
python3 apps/instrument-gateway/examples/http-reader/simulator.py
```

It prints its selected origin. It serves only fixed synthetic identity and two pre-existing results, does not control a device, and stops with Ctrl+C. Use that origin and `127.0.0.1` in a private configuration with `allow_plaintext: true` and empty headers. No real instrument credentials are needed.

Build the source-included reference without AI or a network request, selecting a new output file:

```bash
pnpm gateway:package build \
  --manifest apps/instrument-gateway/examples/http-reader/manifest.json \
  --factory http_reader:create_adapter \
  --file source/http_reader.py=apps/instrument-gateway/examples/http-reader/source/http_reader.py \
  --file tests/test_http_reader.py=apps/instrument-gateway/examples/http-reader/tests/test_http_reader.py \
  --file licenses/LICENSE.txt=LICENSE \
  --output /absolute/private/http-reader.zip
```

Follow the existing [inspection, offline tests and inactive installation guide](./instrument-adapter-packages.md). Test against the exact SDK wheel containing this helper, not merely another wheel with the same development version. The reference factory accepts loopback only and its published manifest always declares simulation output. It is not eligible as real-hardware qualification and must not be relabelled to enable a physical instrument.

To independently exercise Aira source drafting with fixed synthetic API material/tests:

```bash
node scripts/instrument-authoring-example.mjs /absolute/private/http-reader-spec.json --http-reader
```

This creates a private specification only: no model call, driver load, device access or authorization. Continue the separately confirmed [source-authoring workflow](./instrument-source-authoring.md). The model can change source, not endpoint authority, manifest or fixed tests. The checked-in hand-written package remains available with AI disabled.

## Verification and remaining scope

Automated tests cover real loopback HTTP and TLS, rejected certificates/hostname mismatch, pinned addresses, credential isolation, cancellation, invalid responses, source-included offline package tests and reuse in two independent installation directories. A disposable PostgreSQL/API acceptance runs the installed driver against the owned HTTP fixture: Platform saves its result, a simulated lost completion acknowledgement leaves the local journal pending, and receipt-only restart completes without loading the driver, rereading the service or leasing another job. Plain JSON and file-producing completions both use this recovery boundary; invalid completions halt without driver initialization.

The disposable test alone constructs synthetic qualification-policy records to exercise software gates; they are not the published package or hardware evidence. No vendor API, real instrument, physical stop, paid-model performance, second physical device or Windows workstation has been accepted. Documented JSON parameter/start/stop operations can use the [separately configured control backend](./instrument-http-control.md), without broadening this read client. Streaming/binary vendor APIs, vendor SDKs and service discovery need separate reviewed backends/adapters. RFC #5 remains open for the complete onboarding product and an authorized real pilot.
