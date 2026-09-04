# Research automation

Research automation in Airalogy starts from a bounded `Research Task`, not from an unconstrained chat. A Task keeps its goal, success and stop criteria, Lab and Project, pinned Research Environment, Runs, Actions, Evidence, Claims, and final human review together.

## Start a Research Task

1. Open **Research** and create a Task in the correct Project.
2. State a testable goal, success criteria, and stop conditions. Add a deadline and one-currency budget ceiling when the Task must operate inside hard time or cost boundaries.
3. Select any Protocol versions, digital tools, reviewed Knowledge, Lab resource types, approved external research services, and governed Compute Environments that may guide or constrain the work. A Protocol is optional when the research path only needs governed digital tools or an external result.
4. Preview the destination and captured environment, then confirm creation.
5. Start the Task. If Aira is available, it can advance the plan until it reaches a human, approval, tool, external-result, or final-review boundary. If AI is unavailable, the same Task remains usable through explicit Actions.

Changing a Protocol or Knowledge item later does not silently change the captured Research Environment. Create a new plan or Run when the new version should apply.

## Register a Compute Environment

Lab members with research-compute management access can open **Lab resource library → Compute environments**. Create a stable environment key, then declare an immutable OCI image digest, runtime and allowed language, hard CPU/memory/GPU/timeout/output limits, network policy, input/result JSON Schemas, software manifest, risk, and optional hourly cost. Preview the complete contract before confirmation. A revision creates a new immutable contract; existing Research Tasks remain pinned to the prior revision.

Task creators with compute-use access can select an enabled environment during Task creation. Platform copies the exact revision into the Research Environment. Selection alone does not run code, reserve budget, or imply that an eligible Compute Runner exists.

## Register a Compute Runner

A Lab compute manager can add a Runner under **Lab resource library → Compute environments**, receive its credential once, and configure a hard concurrency limit. Install the reference process from `apps/compute-runner` on a separately supervised host, preferably with a dedicated rootless Podman account. Configure the Platform URL, one-time Runner credential, immutable helper-image digest, private persistent state path, and any independently enforced exact-egress networks; the included README, environment example, and systemd unit define the complete contract. Do not expose the engine socket to Platform or share the Runner identity with unrelated services.

Its status appears as ready only when it reports non-root execution, a read-only root filesystem, network isolation, and no host mounts. Bind each Runner to the exact environment revisions it may execute; newer revisions require a separate review and binding. Disabling a Runner or removing a binding stops future work without deleting the audit history. Registration and binding alone still run no code. The default systemd unit is CPU-only; a GPU host requires a reviewed device-specific override in addition to the Platform resource approval.

## Request a computation

In an active Task, choose **Run computation**, select one of the exact environment revisions pinned to the Task, and choose an allowed language. Enter source code and a JSON input that satisfies the environment's input Schema. Optionally attach ready DataAssets from the same Project by selecting exact versions and safe mount names. Declare each output file before preview: give it a safe filename, DataAsset name, kind, media type, maximum byte count, and whether it is required. Source must write declared files below `/airalogy/output/files/`. Preview the destination, source digest, immutable image, resource and network limits, input versions, outputs, eligible Runner count, and maximum estimated cost, then confirm the request.

When AI is enabled, Aira may propose this same Compute Action at a next-action boundary. It can choose only an environment revision already pinned to the Task and backed by an authorized Runner, and only eligible current DataAsset versions that Platform exposes in its planning context. Aira supplies bounded source, Schema-valid input, and complete output declarations. The Run then stops at the normal approval boundary. Open the approval impact to inspect the full source, digest, exact inputs, limits, cost ceiling, and outputs; editing any part requires a new proposal or a manual request rather than mutating the pending contract.

Confirmation creates an approval request; it does not execute code. After an authorized person approves the exact impact, Platform reserves the maximum cost for a budgeted Task and queues the job. An independently supervised, compatible Runner must be online and explicitly bound to that exact environment revision. It pulls a signed short lease, downloads only the fixed input versions, executes outside the Platform API process, and reports heartbeat, result, declared usage, or failure. Source reads `AIRALOGY_INPUT_JSON` and `AIRALOGY_INPUT_DIR`, then must write one UTF-8 JSON object to `AIRALOGY_RESULT_JSON`. The reference Runner discards untrusted standard output to enforce its storage boundary, so retain bounded diagnostics in the result object. After execution, it measures and uploads only declared files. Platform validates the result Schema, hard usage limits, media types, byte counts, and SHA-256 receipts, then atomically registers valid files as Project-visible draft DataAssets with exact provenance. Review a draft before marking it ready or using it as validated Evidence. Platform settles actual cost from measured wall time and records the complete state trail. Use **Cancel computation** with a reason when needed. A delivered job remains cancellation-pending until the Runner acknowledges it; uploaded files from a failed or incomplete job do not become accessible assets.

Runner-side arbitrary filesystem paths are never accepted as Platform assets. Adding or changing an output requires a new preview and approval because the declaration is part of the signed job contract.

## Register an external research service

Lab members with research-service management access can open **Lab resource library → External research services**. Add a provider through preview-confirm, then add one or more services. Each service revision records its exact version, request and result JSON Schemas, risk, whether a quote is required, optional catalog price and currency, SLA target, sample requirements, logistics policy, and terms. Revising a service creates a new immutable contract; it does not rewrite existing Tasks.

Task creators with service-use access can select an enabled service when creating a Research Task. Platform copies the exact provider and offering revision into the Research Environment. This step authorizes only the capability boundary. It does not place an order, reserve budget, send a sample, or assert that a result exists.

## Request and receive an external service

In an active Task, choose **Request service**, select a pinned offering, and provide a JSON request that satisfies its pinned input Schema. Preview and confirm the request. A quote-required job then waits for a service manager to record the provider quote; a catalog-priced job creates its quote immediately. In both cases, Platform creates a separate order approval for the exact provider, request, contract revision, quote, amount, and validity. Funds are reserved and the job becomes ordered only after approval. An expired quote, changed contract state, stale preview, wrong currency, or insufficient Task budget blocks the order.

During fulfilment, a service manager can record the provider order reference and progress. Use **Record custody** for each sample handoff, selecting an authorized Lab resource and optional container, both parties, time, location, carrier, and tracking reference. Custody events are immutable audit checkpoints; record inventory consumption separately in the authoritative resource ledger.

When the provider returns results, first create or upload the relevant Task DataAssets. Choose **Receive result**, enter the result JSON, select the exact DataAsset versions, and confirm the actual cost. Platform validates the pinned result Schema, rejects costs above the approved quote, converts the reservation to actual expense, completes the Action, and returns the typed result to Aira. A failure releases the reserved quote and returns the Run to Aira or normal manual control. All request, quote, approval, custody, progress, result, cost, and actor history remains on the Task when AI is disabled.

## Turn Knowledge into a Protocol draft

Open **Knowledge**, switch to **Knowledge Notes**, and choose **Generate Protocol draft** on an active item. Review the pinned source revision, choose an eligible target Project, and open the Aira draft. Platform loads the protected Knowledge content into the editable generator without putting it in the URL. Review and revise the generated AIMD, then choose **Save Protocol** and confirm the Project destination.

The Protocol does not exist until that final confirmation. At save time, Platform checks that you can still read the Knowledge, can create Protocols in the Project, and are still using the same revision. A changed, archived, superseded, cross-scope, or inaccessible source is rejected instead of silently producing an untraceable asset. The accepted Protocol version retains immutable Knowledge provenance. When AI is disabled, the entry is hidden while template, reuse, import, and manual Protocol creation remain available.

## Turn validated results into candidate Knowledge

On a Research Task, register a Record or exact DataAsset version as Evidence and have an authorized reviewer validate it. In **Scientific assets**, choose **Propose Knowledge**, write the reusable finding, method, decision, or note, and select one or more validated Evidence items. Preview the Project destination and exact source set, then confirm.

Platform creates editable Project-scoped Suggested Knowledge and preserves immutable Evidence snapshots and version links. It does not declare the candidate true or adopted. Open Project Knowledge to revise it and use the separate **Review and adopt** action when a Knowledge Reviewer has assessed the evidence. Pending, rejected, or non-Record/DataAsset Evidence is intentionally unavailable. This deterministic path works when AI is disabled.

## Draft a scientific Claim from validated Evidence

In **Scientific assets**, choose **Add Claim** and select the Evidence that defines the scientific context. You can always write the statement, confidence, uncertainty, and Evidence relations manually. When AI is enabled and every selected item is validated, optionally describe the comparison or constraint and choose **Draft with Aira**.

Aira must assess every selected Evidence item, including contradictions, and returns only an editable Suggested Claim. Inspect and revise the statement, confidence, uncertainty, and relations before previewing and confirming. Platform rechecks the exact Evidence and source versions after generation and again at confirmation. The signed receipt expires after one hour, cannot be confirmed twice, and is cleared if the Evidence selection changes. The original generated output remains in provenance even when you edit the draft. Aira cannot accept the Claim; an authorized human must review it separately. With AI disabled, the same manual Claim and review flow remains available.

## Improve a Protocol from validated Evidence

In **Scientific assets**, choose **Propose Protocol improvement**. Select a Protocol already pinned to the Task, describe the scientific rationale and concrete proposed changes, and attach validated Record or DataAsset Evidence. Preview the exact Project, base Protocol version, and immutable Evidence snapshots before confirming. This creates a proposal only; it does not edit the Protocol.

An authorized research approver who can update the Protocol must inspect and accept the proposal. Choose **Create version draft** only after that review, then edit the copied package in the normal Protocol Editor. When saving, choose a version higher than the current Protocol and confirm the package. Platform rechecks the reviewed proposal, Evidence lineage, and base version under lock. If another version was published in the meantime, or the proposal changed or was already applied, saving stops and the proposal must be recreated against the latest method. A successful save marks the proposal Applied and links it to the exact new Protocol version. Existing versions and active Runs remain unchanged. This complete path also works with AI disabled.

When AI is enabled, select the target Protocol and Evidence first, optionally give Aira a focus or constraint, then choose **Draft with Aira**. Review and freely edit the returned content before previewing it. The signed generation receipt expires after one hour and cannot be reused after confirmation; if the scientific context changes, regenerate the draft. Aira never performs the expert review or applies the Protocol version. With AI disabled, all manual fields and the remainder of this flow stay available.

## Repeat, replicate, or continue a Run

After the current Run and Task are completed, failed, or cancelled, choose **New Run** on the Task page. A completed scientific result must receive its human review before another Run is opened. Select any terminal source Run, classify the relationship as retry, replication, or continuation, and explain the intended difference. The preview shows the new Run number, source, destination, and exact Research Environment digest before confirmation.

The new Run preserves every earlier execution and scientific asset and inherits the source environment exactly. It does not automatically adopt later Protocol, Knowledge, Tool, executor-policy, or resource-definition changes. The Task returns to Draft so the next execution starts explicitly, while its original deadline and shared budget ledger still apply. The Run lineage panel keeps each result and human-reviewed conclusion available for comparison.

## Choose the correct Action

- **Protocol work** assigns a version-pinned method to a person. In **Executor bindings**, Lab managers can configure the corresponding Protocol version to use the future Task owner, a specific eligible Project member, or a verified skill pool. Use **Human executor profiles** there to record a member's availability window, concurrent-work capacity, skill level, verification, and qualification expiry. Skill matching chooses the lowest normalized active workload from people who satisfy every required skill and current Project permission, then pins that exact person and matching evidence. The person completes the normal Record form; a validated Record returns as Evidence without becoming a generic chat message. Platform locks and checks current membership, permission, skills, availability, and capacity again at dispatch time. Without AI, managers can still configure the same bindings and users can assign Protocol work manually.
- **Attention inbox** collects new Protocol work and approval requests assigned to you. Opening an item marks that reminder as read and takes you to the authoritative Research Task. If the deployment administrator enables SMTP, Platform also sends a retryable email reminder; a pending, disabled, or failed email never removes the in-product item and never blocks execution.
- **Research tool** runs an allowlisted, version-pinned digital capability such as reviewed Knowledge search or an optional literature provider. Inputs and outputs are Schema-validated, time-limited, retryable, and recorded in the execution ledger. When several read-only searches are genuinely independent, Aira may create a bounded parallel frontier of two to four Actions. Each branch keeps its own approval and audit record, and Aira does not replan until every branch has completed, failed, or been rejected.
- **Wait for an external result** pauses the Run at a typed boundary for a person, instrument, or service. Select and confirm the expected result contract. The generated event key is an immutable delivery reference; in the current version, an authorized user records the received result from the workbench.
- **Reserve resource** resolves a concrete resource from a resource type pinned in the Research Environment. For inventory, select a container, exact quantity, UCUM unit, and optional expiry. For equipment, select the booking window. Platform previews current availability and policy, rejects stale or conflicting confirmation, and records the authoritative inventory reservation or equipment booking behind the Action.

Aira can request a pinned resource type, quantity, unit, or equipment window, but it cannot pick an arbitrary hidden resource or reserve it directly. Platform selects an accessible candidate deterministically and presents the exact impact for approval. If inventory, permissions, the resource revision, or a booking window changes before approval, the proposal is rejected and must be replanned.

## Register an Instrument Gateway

Lab Owners and Managers can open **Lab resource library → Instrument gateways** to establish the local device boundary. Create a Gateway, preview the impact, confirm, then copy its one-time credential into the on-premises Gateway process. Platform never shows that credential again. Rotating it invalidates the old value immediately, so update the local process before resuming device work.

Install and supervise the reference process from `apps/instrument-gateway`, store the credential in the local service manager rather than source control, and keep its persistent state directory private. Configure the Platform `/api` URL, credential, a locally installed adapter name, adapter configuration, and state path. Production connections require HTTPS. The built-in `mock` adapter is for integration testing only; a hardware adapter must independently allow exact command versions and implement an idempotent safe-stop that returns only after the device reaches its safe state.

Select the Gateway and add only the commands it may perform. Every command selects a concrete active equipment Resource, captures its current revision, and defines a versioned key, input and result JSON Schemas, risk, timeout, and device-confirmation requirement. Medium- and high-risk commands always require physical-device confirmation. Schema changes create a new audited allowlist revision; existing jobs retain their original contract. Disable a command or Gateway to block future leasing.

## Run an instrument

First pin the relevant equipment Resource type when creating the Research Task, and create or obtain an approved booking assigned to you in the Lab resource library. In an active Task, choose **Add Action → Run an instrument**. Select the allowlisted command and your approved booking, enter the command input as a JSON object, then preview the exact command revision, equipment, booking window, risk, and device-confirmation requirement before confirming.

The job stays queued until its booking window opens. The local Gateway pulls a signed short lease, confirms the device locally when required, heartbeats while working, and returns a result that Platform validates against the pinned output Schema. The workbench shows delivery attempts, last heartbeat, result, and failures. Use **Request stop** with a reason when necessary. A delivered job is not considered stopped until the Gateway acknowledges it. Pausing or cancelling a Task also requests a stop for delivered physical work. Platform never retries a physical operation automatically; inspect the equipment before resuming a paused Run.

## Control time and budget

The Task page shows the pinned deadline and the budget's reserved, actual, committed, and remaining amounts. Users with research approval capability can record a reservation, release, expense, or credit. Each entry must be previewed and confirmed against the current Task revision and cannot be edited afterward. Release only an existing reservation; credit only an existing actual expense. Record the offset and the replacement as separate entries when correcting a mistake.

Use **Amend limits** when the approved deadline or budget ceiling must change. Enter the complete replacement boundary and a reason, preview the old and new values, then confirm against the current Task revision. Each amendment is an immutable Task event. A budget that already has ledger entries may change its ceiling only: its currency cannot change and the budget cannot be removed. A lower ceiling must remain above the committed total. If the old boundary paused the Run, a valid amendment only makes it eligible to continue; inspect the Run and choose **Resume** separately so a governance change never restarts work by itself.

Platform checks these limits in the API before any new manual or Aira-created Protocol, Tool, Wait, Resource, Instrument, External Service, or Compute Action. It rejects stale or over-limit writes, pauses immediately when a confirmed budget entry exhausts the ceiling, and otherwise pauses at the next runtime boundary after a deadline or budget limit is detected. Approved External Service Jobs reserve their exact quote; approved Compute Jobs reserve their maximum runtime estimate. Each converts the reservation to validated actual cost at completion. Model and other non-integrated costs must still be recorded explicitly.

Search candidates remain Action output. Platform does not silently approve them as Knowledge, Evidence, or Claims.

At each next-action boundary, Aira first chooses between a pinned Protocol, an available Tool, a pinned Resource requirement, an eligible Instrument command, a pinned External Service, a typed external Wait, or finishing the path. Instrument choices appear only after you have an approved, unexpired equipment booking. The model chooses only a listed command ID and input arguments; Platform selects the booking deterministically and shows the exact command, equipment, window, risk, and local-confirmation requirement as a normal approval. No Instrument Job can be leased before that approval, and a stale command, permission, booking, or competing use makes approval fail closed.

For an External Service, Aira can choose only an exact offering already pinned to the Research Environment and draft a request that passes its pinned input Schema. This does not place an order. Platform creates the same governed Service Job used by the manual path: a service manager records a provider quote when required, every exact quote receives a digest-bound order approval, and budget reservation, sample custody, fulfilment, and result receipt remain deterministic controls. This Action Planner never executes arbitrary model output: Platform validates the chosen type, allowlist entry, pinned version, arguments, resource need, and result contract before creating an Action. Physical Actions and service orders always require approval; other Aira-proposed Actions remain governed by their exact risk policy.

Completed Tool, Instrument, Resource, External Service, and external Wait Actions return their typed results to later Aira planning and conclusions. Platform keeps only a bounded recent result window and presents it as untrusted evidence; those results remain Action output until a user deliberately registers and validates the corresponding Record, DataAsset, Evidence, or Knowledge asset.

## Supply an external result

Open the waiting Action and choose **Provide result**. Fill the fields defined by the pinned event contract, preview the exact payload, and confirm it. Platform checks your permission, the event type, the payload Schema, and the event revision before completing the Action. A stale, duplicate, or incompatible signal is rejected.

The Run then resumes Aira when AI is available. With AI disabled, it returns to ordinary manual control without blocking Protocol, Record, Knowledge, or result-review work.

## Review the scientific result

Execution success is not scientific truth. Before completing a Task:

- inspect the execution ledger and failed attempts;
- validate or reject pending Evidence;
- review Claims against their linked Evidence and uncertainty;
- resolve or cancel unfinished Actions and approvals;
- record the goal assessment, scientific outcome, and reviewed conclusion.

When AI is available, choose **Run independent review** to ask the separate Reviewer Agent to critique the exact current result context. Inspect its recommendation, supporting and contradicting Evidence counts, uncertainties, missing checks, and risk flags. Choose **Use as review draft** only when you want to copy its suggested outcome and summary into the editable human form; revise it as needed, then confirm it yourself. A generated recommendation cannot complete the Task, becomes stale when the scientific context changes, and remains an immutable advisory record. When AI is disabled, complete the same human review directly without this optional panel.

Cancelling a Task preserves existing Records, Action history, tool provenance, and scientific assets while preventing unfinished work from resuming it. Outstanding inventory reservations and pending or approved equipment bookings are returned automatically; explicit early release also uses preview and confirmation.

## Permissions and safety

Research Actions use current Project and resource permissions enforced by the API. A tool or resource type being visible does not bypass Knowledge visibility, Restricted content grants, object-level resource access, inventory-operation rights, equipment-booking rights, or Project access. External results require an authenticated user with research execution capability; the event key alone is not authorization. Rejecting an Aira proposal cancels its typed execution record, records the reason, and returns that reason to the next planning round.
