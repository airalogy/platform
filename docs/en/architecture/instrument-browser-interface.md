# Browser interface backend

This is an executable local development backend for [equipment software integration](./instrument-integration.md), not autonomous instrument onboarding. It replaces the synthetic demo's one-off browser clicks with the same bounded, confirmed session used by the local CLI.

## Supported boundary

| Target | Supported now |
| --- | --- |
| Explicitly selected, hash-pinned standalone simulation HTML | Observe, literal parameter fill, click, state checks and readback |
| Explicit HTTPS application URL (HTTP only on loopback) | Open and observe; plans containing fill/click are rejected |
| Existing authenticated browser, workstation desktop, native vendor software | Not attached or controlled |
| Production instrument commands and remote execution | Must use separately qualified Gateway adapters and Instrument Jobs; not supplied by this tool |

Opening a page or a GET request can initialize equipment. Neither the network method nor a label such as “read” establishes physical safety. Obtain independent local authorization and use an isolated training/simulation environment. No real target was used for software acceptance. Windows private-file ACL support is refused; Linux/macOS synthetic CI is not vendor/OS qualification.

## Run and review

With Node 22+, repository dependencies and the pinned Playwright Chromium installed:

```bash
pnpm exec playwright install chromium
pnpm gateway:interface-example
```

The example command creates owner-only temporary definition/plan files and prints their absolute paths. It does not open the app. Substitute these paths and an owner-only evidence directory:

```bash
pnpm gateway:interface preview --definition /absolute/definition.json --plan /absolute/plan.json
pnpm gateway:interface run --definition /absolute/definition.json --plan /absolute/plan.json --confirm <reviewed-sha256> --evidence /private/owner-only-directory --ack-new-run
```

Review the **private** preview before copying its digest: selected application/HTML code, version identity, exact target, controls, network, masks, limits and each step. The digest includes the tool and browser-library versions. File bytes are checked again immediately before opening. Omitting the plan means observation only. A changed target/plan/file/version requires a new preview. Confirmation is a local user's declaration, not a Platform grant or source approval.

`pnpm gateway:gui-demo` runs only the bundled synthetic reader using this backend, saves local evidence and emits a compatible rehearsal bundle. A separate Python contract checks the expected result `0.84`; it is not inferred from the returned value. Its synthetic Gateway ownership label does not attest real equipment ownership.

## Contract and stopping

`airalogy.browser-interface.v1` contains:

- `target`: application/version/title/locale, scoped exact role/name or test ID, a selected source and visible identity text.
- `controls`: unique IDs and semantic locators, text/value/checked readback and explicit read/fill/click operations.
- `states`: uniquely matching conjunctions of literal control values. Unknown or ambiguous state is refused.
- `network`: exact same-origin GET/HEAD URLs with request-count limits. The initial URL GET must be listed. A bounded local fetch layer refuses redirects before following them, streams at most 2 MiB per response and 16 MiB per session, and passes no browser cookies/authentication. No URL wildcards or navigation after initial load; authenticated applications are not supported in this slice.
- `blocked`, `privacy.redact`, `privacy.screenshot`: stop selectors and explicit local capture choices.
- `limits`: at most 900 seconds, 40 steps, 10 seconds per operation, viewport at most 1920 × 1080. At most `2 × max_steps + 1` saved observations; control values ≤4 KiB, accessibility tree ≤32 KiB, each screenshot ≤2 MiB.

`airalogy.interface-plan.v1` is a continuous sequence of literal steps with before/after state IDs. Fill requires exact parameter readback and cannot declare a state transition. The runner executes only the next confirmed step; it does not accept JS, arbitrary selectors, shell, coordinates or model instructions. It rechecks identity, controls, enabled state and the previous observation digest before the action, holds the selected DOM element for that action, and checks resulting state. This is not an atomic physical interlock; rapidly changing applications need their own qualified adapter. State transitions must already be observable when the action returns; no hidden retries or unbounded polling are performed.

Unexpected dialogs, windows, frames, downloads, sockets, denied requests, stale observations, unknown state, timeout or failed postconditions stop the session. An attempted action with uncertain results is recorded before closing. No action is automatically retried or replayed after restart. Closing a browser is **not** confirmation that equipment stopped safely. Existing Platform safe-stop and lease rules are unchanged.

## Private evidence and model use

Evidence uses a new `0700` directory, exclusive `0600` files and a hash-linked event sequence. Intent is durably written before each action, followed by readback/result or uncertainty. Screenshots are opt-in, restricted to the selected scope and masked using declared page locators plus password inputs. Controls overlapping a mask are refused. When masks/password fields exist, the entire accessibility tree is omitted because its serializer has no redaction contract. Never put passwords into step values. Masks are not automatic secret detection; review dynamic application content before enabling capture. All displayed data may be sensitive even if it is not a password.

The manual CLI uploads no screenshots, evidence or selected files. After local review, explicitly selected text observations may be included as `materials` in the separately authorized [source-authoring workflow](./instrument-source-authoring.md). For adaptive model choices, use the separately authorized [bounded interface exploration](./instrument-interface-exploration.md) workflow: only selected textual readbacks/actions reach Aira, and local actions still require an exact policy confirmation. Visual interpretation, unknown-app/native launch/discovery, managed GUI execution and real-equipment validation remain open RFC work.

Browser isolation and request routing are defense in depth, not an OS security sandbox or a guarantee against every browser-originated transport. Service workers are blocked, browser contexts are fresh, OS permissions are not granted and no existing session is attached. Only run reviewed application code on a patched, appropriately isolated host. Version text and evidence hashes are observations/declarations, not firmware identity or tamper-proof attestations.

## Verification

`pnpm gateway:interface-test` exercises actual Chromium against owned standalone HTML and temporary loopback fixtures, including consent, state drift, duplicate controls, masks, dialogs, extra windows, sockets, redirects, request denial, budgets, CLI processes and private evidence. Pre-push selects these tests for backend/demo/dependency changes. Dedicated CI runs synthetic Linux/macOS checks and packs the local tool; it does not upload UI evidence. The Gateway replay contract and Platform data-only draft APIs remain compatible.
