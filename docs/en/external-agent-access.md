# External Agent access

Connect Codex or another MCP client to one authorized Project. Platform remains responsible for access control, strict data validation and Record revision history. These deterministic operations do not require Aira, Masterbrain or an enabled model service.

This V1 implements [Issue #11](https://github.com/airalogy/platform/issues/11). It provides scoped tokens, HTTP/MCP reads, CSV import and corrections to the token owner's Records. It does not grant administrative, file-download or instrument-control access.

## Enable and connect

1. A Lab Owner or Manager opens **Lab settings → External tool access policy**. Access is off by default. Enable it only if the organization's data policy permits the external tool and its model provider to process the returned data.
2. Optionally block top-level Record variable IDs, one per line. These restrictions apply across the Lab, including otherwise public Projects. Changing the policy invalidates outstanding write confirmations.
3. In **Account settings → External AI tools**, select a Project, name the grant, choose actions and an expiration of 1–90 days. The user must currently belong to that Lab and have access to that Project. The grant never expands the user's permissions.
4. Save the token when it is shown once. The server stores only its SHA-256 digest. Do not use a browser session token or legacy API key as a substitute.
5. Configure the client privately. For a same-origin deployment, the MCP endpoint is `https://your-platform.example/api/mcp`. The settings page supplies the exact command for the current instance:

```sh
codex mcp add airalogy --url https://your-platform.example/api/mcp --bearer-token-env-var AIRALOGY_PLATFORM_TOKEN
```

Set `AIRALOGY_PLATFORM_TOKEN` using your client's secure environment configuration. Do not paste the token into chat, source control or shared documents; do not place it literally in the registration command. A desktop application does not necessarily inherit variables from an already-open terminal: restart it with the configured environment. See the [Codex MCP documentation](https://developers.openai.com/codex/mcp/) for client configuration.

Revocation takes effect on subsequent calls and cancels unexecuted requests. Expiry, account credential invalidation, loss of Lab/Project membership and policy changes are checked server-side on each request. An operation already committed before revocation remains a normal Record, with its history.

## Complete an import

Ask the connected tool to:

1. Call `access_context`, then `list_protocols` and `get_protocol` to establish the target and obtain its canonical CSV header.
2. Prepare CSV using those exact `var.<id>` headers. Display titles and approximate names are not mappings. Do not invent values, fill missing scores with zero or relax the Protocol to force an import.
3. Call `preview_import` with the Protocol ID, CSV text and a unique `request_key`. The platform validates every row with the existing importer. Invalid data returns bounded row/field errors and creates **zero Records**.
4. Open the returned confirmation URL yourself. Review the destination, row count, Protocol version and complete CSV in Platform. Approve or reject while logged into the same account that created the token. **The external token cannot approve itself.**
5. Return to the tool and call `execute_operation` with only the approved operation ID. It cannot replace the input at execution time. The result contains saved Record IDs and links.

Confirmations expire 15 minutes after preview; approval does not extend that deadline. They are temporary operation requests, not Record drafts. Changing the input requires a new preview and request key. Retrying the same preview key with identical input returns the same request; different input returns `409`. Retrying a completed operation returns its existing receipt rather than importing again. Always check status after an interrupted response before preparing a new request.

## Correct a Record

`list_records` returns only the latest versions that the user may read. A deleted latest version also hides its retained earlier revisions from this list. Pass `record_id`, `protocol_id`, `expected_version`, changed variable values in `changes`, a meaningful `reason` and a fresh `request_key` to `preview_revision`. Only the original author may revise a Record, matching the existing Platform rule.

The user reviews the before/after values in Platform. After approval, execution creates a correction revision and retains the old version and reason. If another revision was saved meanwhile, execution fails; read the new version and preview again. There is no external delete operation.

## V1 disclosure and operation limits

- Each token is bound to exactly one Project. Required scope: `protocols:read`. Optional scopes: `records:read`, `records:import`, `records:revise`. Revision also requires Record read scope.
- Lab field restrictions and existing Protocol/Record permissions are checked in the API. Public visibility alone does not allow an external token to skip Lab membership or policy.
- Protocol reads expose field IDs, titles, required status, primitive types and supported validation limits. They do not expose AIMD, executable code, environment variables, model prompts or defaults/examples. CSV templates contain headers only.
- Record reads expose primitive variables only, including supported date/time strings. Attachments, signed URLs, reports, objects and arrays are unavailable. Unsafe string values are omitted and named in `withheld_fields`; they are not rewritten as scientific null values. Omitted fields must not be inferred.
- A Protocol containing blocked or unsupported complex variables must be imported/revised through the normal Platform UI. V1 does not partially write such a Protocol. External import does not inject the user's broad legacy API key or Protocol environment secrets into validation; validators requiring those credentials must use the normal UI.
- Each CSV is at most 1 MiB; total request body is at most 2 MiB, including streamed bodies. Existing row limits still apply. Listings use 50 items per page with `next_offset`. At most 10 pending/approved confirmations per grant and 50 active grants per user; authenticated tool activity is limited to 120 logged calls per user per minute.
- Credentials and CSV/Record payloads are excluded from external API request logs. Audit records contain actor, grant, operation identity and result references rather than input values. Validation errors expose bounded field/line locations and categories, not arbitrary custom-validator output.
- Confirmation payloads are cleared on execution, rejection and revocation, and lazily cleared when expired operations are visited. Revision summaries remain private and require current permission to view. They are not a public activity feed.

## API and MCP contract

The public reverse proxy prefixes these application paths with `/api`:

| Endpoint | Authentication | Purpose |
| --- | --- | --- |
| `GET /external-access/dashboard` | Browser `Auth-Token` | Own grants, confirmation metadata and audit |
| `GET/PUT /external-access/labs/{id}/policy` | Browser; Lab Owner/Manager | Current policy and revision-checked update |
| `POST /external-access/grants` | Browser | One-time scoped token issuance |
| `DELETE /external-access/grants/{id}` | Browser; token owner | Revoke and cancel pending writes |
| `GET /external-access/operations/{id}` | Browser; token owner | Authorized complete preview |
| `POST /external-access/operations/{id}/decision` | Browser; token owner | Confirm exact `digest` with `approve: true/false` |
| `POST /external-access/tools/{name}` | Scoped Bearer token | Deterministic tool call with JSON arguments |
| `POST /mcp` | Scoped Bearer token | Stateless Streamable HTTP MCP |

The MCP tools are `access_context`, `list_protocols`, `get_protocol`, `list_records`, `preview_import`, `preview_revision`, `operation_status`, and `execute_operation`. Client discovery supplies each input schema. Extra arguments are rejected; the execution tool accepts only an operation ID. Tool discovery does not grant any scope.

MCP uses JSON responses, accepts `application/json, text/event-stream`, validates Origin against `SITE_URL`, negotiates supported protocol versions and returns `202` for supported notifications. There are no session IDs, legacy SSE transport or unsolicited server requests; GET/DELETE return `405`. Failed tool calls use `isError: true`. Direct HTTP clients receive appropriate `401`, `403`, `404`, `409`, `413`, `422` or `429` errors. Generic executor failures ask the user to inspect the normal Platform UI rather than returning potentially sensitive exception text.

All mutations and their idempotent receipt/audit commit together. The lock order is user call gate → shared Lab policy → grant → operation → Protocol → Record; ordinary Record corrections also acquire the stable Protocol lock and may supply `expected_version`. Calls from different Lab members do not require an exclusive Lab-wide lock. No external tool can send SQL, choose arbitrary server URLs, change members/permissions or execute an instrument.

## Deployment and follow-up

This feature needs migration `0078_external_agent_access` and its matching web/API build. Follow the normal release and backup gates; this guide is not authorization to upgrade a live instance. Existing Labs remain disabled until explicitly configured. The independent `mcp` client is a development/test dependency only; the runtime transport uses the existing FastAPI stack.

The integration suite covers real migration round trips, real CSV validation, atomic rollback, concurrent retries, Record history, permission changes, expiry, disclosure boundaries and an independent MCP SDK client. Browser coverage exercises grant creation, user confirmation and revocation in Chinese/English at phone/desktop widths. No production/customer data is needed.

OAuth/PKCE onboarding, a dedicated CLI/SDK, Webhooks, broader Knowledge/Protocol editing and attachment access are later, separately scoped work. They must reuse this authorization and mutation boundary rather than adding a parallel data path.
