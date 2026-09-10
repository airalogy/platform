# Selected-application interface survey

For an already-running native macOS application, use the [native observation preparation](./instrument-native-interface.md), then this same single-use `run`, review/Aira and `assemble` flow. Native definitions remain read-only; they are not browser action policies.

Survey the visible controls of an **explicitly selected** browser application without handwriting its control/state map. This is bounded local development evidence, not automatic discovery of installed software or permission to operate equipment. It shares the [browser backend](./instrument-browser-interface.md)'s isolated Chromium, exact network allowlist, privacy masks and stopping rules. Linux/macOS private-file support only; native Windows and visual Computer Use remain unqualified.

## Prepare and review

Install Node 22+, workspace dependencies and the pinned Chromium from the browser guide. For the repository's owned synthetic reader, substitute the checkout's absolute path:

```bash
pnpm gateway:survey prepare \
  --file /absolute/platform/apps/instrument-gateway/examples/simulated-reader.html \
  --application 'Airalogy Simulated Reader' --version 1.0 \
  --title 'Airalogy Simulated Reader — no hardware' \
  --scope-role main --workspace /absolute/private/survey
```

Preparation reads the selected file to pin its bytes, writes a new private directory and prints `request_file` and `local_preview_digest`. It opens no application, contacts no model and makes no network request. Review the adjacent `preview.json`: source, operator-declared version/title, scope, runtime, network, privacy and limits. Local HTML must be independently reviewed simulation/training content; do not use this mode for vendor software or production control.

For a selected web application, use `--url` instead of `--file`. The initial exact GET is included in the preview; additional same-origin GET/HEAD requests require an explicit `--network /absolute/rules.json`. No authentication/profile sharing, arbitrary URLs, redirects, sockets, frames, downloads, clicks or fills are authorized. **Opening software or GET can initialize equipment**: independent operator authorization is required even for observation. Do not test unknown production endpoints.

Default capture excludes input values and screenshots. `--capture-values` and `--screenshot` are distinct opt-ins shown in the preview. `--redact /absolute/locators.json` masks an array of exact semantic locators. Choose a unique scope with `--scope-role`/`--scope-name` or `--scope-test-id`; an advanced `--selection /absolute/selection.json` uses the exact saved selection without overrides. There is no automatic secret detector: static text, labels, test IDs and approved values may contain confidential research data. Review locally before sharing.

## Capture once

```bash
pnpm gateway:survey run /absolute/session/request.json --confirm <reviewed-local-digest>
```

The retained, durably flushed `run.started` marker precedes launch. Repeating this request is refused even after failure or a lost response; never remove the marker to replay an uncertain launch. Inspect private evidence with the operator; a new preparation is a new operation. Closing the browser does not confirm physical safety.

Capture visits at most 200 candidate elements within the selected visible scope and emits at most 64 control hints. Exact test IDs or accessible role/name locators are retained only when Chromium resolves them uniquely to the observed node. Duplicates or unsupported semantics remain advisory with no executable locator. Password/file inputs and private masks are excluded, including composed Shadow DOM and indirect label references. When values are not approved, enclosing text containers cannot bypass the restriction. Optional screenshots remain private and masked; no screenshot, raw HTML or full accessibility tree is uploaded.

The result includes `survey.json`, its digest and a manual-analysis template. Software version is operator-declared; this single client-reported snapshot proves no transition, experiment result, device identity or physical readiness. Client-owned files and exports are not attestations.

## Review and assemble an ordinary draft

Inspect `survey.json` and edit the generated `manual-analysis.json`. Keep its `capture_digest` unchanged. Select `identity_control` from a unique observed **text** control containing the visible application/version identity, and `read_controls` from controls with non-null `locator` and `read`. Use only observed control IDs. `features` distinguishes `observed` from `inferred` interpretations, records `read_only`/`state_change`/`unknown` risk, and grants no authority. `route` can recommend `browser`, `api_or_sdk`, `manual` or `unknown`; do not infer an API exists from a screenshot.

```bash
pnpm gateway:survey assemble /absolute/session/request.json \
  --analysis /absolute/session/manual-analysis.json --workspace /absolute/private/drafts
```

Assembly verifies selection/runtime/source, retained receipt, capture digest and control references, then writes a **new** private draft directory. It never opens software, calls a model or overwrites an existing draft. It creates ordinary editable `definition.json`, an empty `plan.json`, copied analysis/report and provenance. All generated controls permit **read only**. The sole `observed` state is an initial identity anchor, not an experimentally validated success condition. Reopening this definition requires the separate browser preview/confirmation and is a new operation.

No adapter is installed, activated or qualified. Before [Aira action selection](./instrument-interface-exploration.md), independently review any added controls, literal actions, transitions and success checks. Transferring selected report text to [source authoring](./instrument-source-authoring.md) is explicit, not automatic. AI-disabled operation fully supports this local/manual flow.

## Optional Aira interpretation in Platform

In **Lab → resource library → Instrument Gateways → select Gateway → Application survey**, select the equipment and import only the locally reviewed `survey.json`. Enter a goal and reason, review the exact capture and configured-model processing consent, then preview and compare the **capture digest** with the local result. Confirm to save a private, five-minute analysis authorization. Use **Analyze once** to start its one permitted model attempt. Confirmation does not open software or spend a model call by itself.

The user-authenticated `/instrument-surveys` API independently enforces current Lab/equipment service permissions, source-purpose separation and exact preview matching. Only the confirming user can start the paid attempt. Gateway/equipment revisions, user, model and processing-transport configuration are pinned and rechecked after model latency. At most one attempt, 60 seconds and 32 KiB of output; these are bounds, not a guaranteed monetary ceiling. The call is reserved durably before contacting the existing Aira provider. Same-turn retries return saved state, while a second turn is refused. Browser requests allow for that response window and do not automatically retry. After uncertainty, refresh saved history rather than calling again.

The model receives the selected report's text and the user's goal, not local source paths, HTML, screenshots or an authenticated browser. Content is untrusted data. The validator rejects invented control references, extra operations, unapproved readbacks and invalid identity anchors. Interpretations distinguish observed from inferred and read-only/state-changing/unknown risk; these labels remain advisory, not equipment qualification. A label alone cannot establish that an API/SDK exists.

Review the result and choose **Export reviewed analysis**. Save the exported JSON in an owner-only local directory/file and pass it to `assemble` instead of `manual-analysis.json`. Its capture digest must match the retained original receipt. Export provenance records a client-supplied Aira export, not a cryptographic attestation; the original analysis remains in private Platform history. Assembly still produces only the same ordinary read-only draft. No click/fill rights, source approval, installation or activation are inherited.

Cancellation prevents a later proposal from being accepted; it cannot recall already transmitted data or guarantee cancellation of provider charges. History and completed exports remain scope-protected and available when AI is off or the grant expires. In-progress calls lost with a server restart are shown as interrupted after their deadline and cannot be silently resumed.

Migration `0057_instrument_survey` adds the separate `survey` purpose to existing development history. Downgrade deletes survey sessions/turns before restoring the previous source/interface purpose constraint; it preserves source/interface history and does not alter local files or undo processing. Back up before deployment through the normal release process. The real API/DB/Chromium acceptance uses only a synthetic model stream; it is not paid-model quality evaluation or real-device validation.

Installed command: `airalogy-interface-survey`. `gateway:interface-test` exercises actual synthetic Chromium, privacy, duplicate locators, CLI no-replay and reopening the read-only draft. `gateway:contract:check` checks the shared Node/API schema. These tests do not qualify vendor software, native/visual operation or real hardware.
