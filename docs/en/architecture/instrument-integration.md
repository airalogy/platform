# Equipment software integration

This delivers the **GUI draft/rehearsal slice** of [RFC #5](https://github.com/airalogy/platform/issues/5), not the complete equipment-integration product.

## Goal and authority

An integration assistant should understand an authorized instrument application, observe demonstrations and propose a reusable adapter for validation before deployment. Prefer supported API/SDK, accessibility controls and browser DOM; visual Computer Use needs an independently qualified backend. Launching software may initialize equipment and is not assumed read-only.

Observation, navigation/launch, physical changes, installation and qualification are separate permissions. Screen content and manuals are untrusted data, not instructions. Replay never grants physical control. Protocol continues to describe research methods; an integration draft is not a Protocol or Instrument Command.

## Available workflow

In **Lab → resource library → Instrument Gateways**, select a Gateway and use **Equipment software integration**. The API requires both Lab Owner/Manager access and `equipment.service` on the active equipment. Drafts and history are not public, including when a Project is public.

1. Select equipment and enter the goal. A unique equipment option is inherited.
2. Load the synthetic example or import JSON (256 KiB maximum): exact application/version/OS/language, literal steps, source declarations, limitations and independently supplied observations/expected outputs.
3. Optionally ask Aira to edit from those observations and authorized notes. Processing consent is mandatory; the deployment model may be external. One call is limited to 60 seconds, with no model-selected tools, browsing, code execution or iterative retries. Permissions are checked before and after generation. This is not autonomous desktop exploration. Imported source labels are user declarations, not cryptographic attestations.
4. Rehearse and preview. The API interprets data only: exact window/target, interactive session, control ownership, blocking dialogs, unique controls, state continuity, parameter readback and expected outputs. Every command needs a passing scenario for an overall pass. Failures can be saved for diagnosis without being labelled successful.
5. Confirm the preview. Its digest binds equipment/Gateway revisions, actor, draft revision and content. Stale/concurrent writes fail instead of overwriting. Save adds the private draft, report and audit snapshot, not commands or execution authority.
6. Reload, edit or export. Old revision exports do not change current or installed versions. Draft/history lists currently show the most recent 100 entries.

AI-disabled deployments retain steps 1–2 and 4–6. No real documents/screenshots are automatically collected or sent to a model. Treat exports as private laboratory material until separately reviewed for sharing.

## Local tools

From a source checkout with Python 3.11+:

```bash
pnpm gateway:rehearse --example
pnpm gateway:rehearse /absolute/path/to/rehearsal.json
```

The CLI needs no additional Python dependencies or credentials. It rejects a final symlink and oversized files, never scans adjacent directories, follows package paths or executes content. Exit codes: 0 matched, 1 mismatched observations, 2 invalid input. No results are uploaded automatically.

With repository Node dependencies and Playwright Chromium installed:

```bash
pnpm gateway:gui-demo
```

This operates only the bundled synthetic reader through real browser controls: fill sample count, click simulation, read result. Network requests are denied. The expected result is fixed independently of observations. It prints a bundle for import. It is not a generic browser controller or native Windows backend.

## Contract and remaining delivery

`airalogy.gui-rehearsal.v1` supports `observe`, `read`, `invoke`, `set_value` as **step descriptions compared with observations**, literal scalars, up to 10 commands, 40 steps per command and 20 scenarios. No shell, code, URL fetching, coordinates, implicit retries or physical stop claims. One authored Python contract in Gateway generates the API copy; CI checks equality.

| Capability | Status |
| --- | --- |
| Private draft/history, import/export, preview confirmation | Implemented |
| Offline replay and synthetic browser demonstration | Implemented; not hardware evidence |
| Optional Aira editing within supplied target/controls/states | Implemented; provider success needs deployment configuration |
| Autonomous instrument software discovery/launch/exploration | Not implemented |
| Native accessibility and visual control backends | Not implemented; target software/OS required |
| Sandboxed driver generation and trusted package distribution | Not implemented |
| One-time pairing, installation receipts, binding qualification | Not implemented |
| Instrument raw-file ingestion and draft DataAsset mapping | Not implemented by this slice |
| Real equipment, OS installation and safety acceptance | Awaiting authorized pilot and operator |

Existing Gateway signing, allowlists, bookings, approvals, heartbeat and safe-stop contracts are unchanged. No pilot model/software/OS is specified. Do not close RFC #5 or mark P0-A/P0-B acceptance complete based on this slice.

Migration `0048_instrument_integration_drafts` adds the draft table. Upgrade through the normal backed-up deployment workflow before using the UI. Test migrations on disposable data; downgrade deletes drafts but does not reverse physical actions or uninstall adapters.
