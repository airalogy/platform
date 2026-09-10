# Owned synthetic HTTP reader — fixed API specification

This is an independently specified software fixture, not vendor documentation or real equipment acceptance. Only use its owned loopback server. It serves pre-existing constants; no measurement, motion, reset or parameter writes exist.

## Interface

- `GET /v1/identity`, without query parameters, returns `{"simulation_only": true, "target": {...}}`. The target has exactly six nonempty string fields: `identity_reference`, `firmware`, `application`, `application_version`, `driver_version`, `os_version`. The adapter must read it, not fabricate identity.
- `GET /v1/result?sample_id=sample-A` returns `{"sample_id":"sample-A","value":1.25,"unit":"synthetic_unit","simulation_only":true}`.
- `GET /v1/result?sample_id=sample-B` returns the same schema with `sample_id: "sample-B"` and `value: 4.75`.
- Only these sample identifiers are accepted. Successful reads return HTTP 200 and UTF-8 `application/json`. Missing routes/samples fail. No redirects, authentication refresh or retries are supported.
- `value` must be a finite number (not boolean) from 0 to 100. The returned sample must match the request. Reject extra fields, different units, missing/false `simulation_only`, bad types and any failure response. Return received data, not a locally computed or canned substitute; the fixed tests vary the supplied value.

## Adapter boundary

Implement `ReferenceHttpReader(client)` and `create_adapter(config_path)` in `source/http_reader.py`; the fixed tests use that constructor seam without network access. The sole command is `reader.result.read@1.0.0` with exactly `{"sample_id": "sample-A" | "sample-B"}`.

Use the current Gateway SDK's `HttpReadClient` and fixed `HttpReadOperation` entries: `identity` maps to `/v1/identity`, `result` to `/v1/result` with the exact `("sample_id",)` query tuple. Bound each response to 4 KiB and each call to three seconds. Pass the execution stop event. Do not request data during construction or `supports`.

The factory reads an explicitly selected private `airalogy.http-read-config.v1` file using `read_http_read_config`, rejects a non-loopback address, then constructs the client. Origin, numeric connection address and any instrument headers belong only in that private local file, not the package, job arguments or model materials. Construction performs no connection.

`identity()` validates the exact target response above. `confirm()` returns `None`. The reference `safe_stop()` starts no request: this fixture has no physical process and only reads existing constants. This implementation is **not** a generic hardware safe stop. GET does not prove that an unknown service is physically read-only, and a server's simulation label is not trusted qualification. Production onboarding still requires the separate review, installation, identity, qualification and activation flow.
