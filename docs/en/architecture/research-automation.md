# AI Research Automation Architecture

## Status

This document is the architecture contract for research automation in Airalogy Platform. Implementations must preserve its object, authorization, and compatibility boundaries. Unimplemented capabilities must remain explicit and must not be simulated by a chat transcript or static UI.

## Product goal

Airalogy Platform is evolving into an AI-native Research OS. A user provides a research goal and success criteria; Aira plans, executes, waits, validates, and replans within a real Research Environment, then delivers a traceable Research Result Package.

AI is the intelligent orchestration layer, not the system of record or the authorization system. Platform remains the deterministic control plane for tasks, methods, execution, evidence, approvals, and audit. If AI is disabled or temporarily unavailable, people can still create tasks, schedule methods, submit Record/DataAsset evidence, validate results, and complete research.

## Layers

1. **Experience**: Research Task Workbench plus the Aira intent entry point.
2. **Intelligence**: AIRA Method for goal interpretation, strategy, planning, interpretation, and replanning.
3. **Runtime**: Research Run, Research Action, events, queues, concurrency, retries, pause, and recovery.
4. **Methods and capabilities**: Protocol, Workflow, Tool Connector, and Executor Binding.
5. **Scientific assets**: Paper, Record, DataAsset, Evidence, Claim, Knowledge, and Report.
6. **Operational resources**: People, Equipment, Inventory, Sample, Budget, Compute, and External Service.
7. **Governance**: Permission, Approval, Policy, Risk, and Audit.

## Core objects

### Research Task

A `Research Task` is the top-level user-facing object for a bounded research objective. It includes the goal, success and stop criteria, Lab/Project scope, owner and participants, autonomy level, budget/time limits, applicable policies, one or more Research Runs, and a scientific terminal outcome distinct from execution success.

The Aira intent entry is a goal-to-Task adapter, not a privileged write path. Platform first resolves a least-privilege catalog for the selected Project, user, and autonomy level. The model sees only currently readable reviewed Knowledge and capabilities with an executable, non-denied binding, and it may return only exact catalog identifiers plus bounded Task fields, assumptions, and warnings. No database transaction stays open during the provider call. After generation, Platform resolves every selected object and binding again; any permission, version, availability, or policy change fails closed. The result remains an editable `ResearchTaskDraft` and enters the ordinary preview-confirm contract. It creates no Task, approval, reservation, order, Compute Job, or instrument command, and disabling AI leaves the manual Task path unchanged.

### Research Run

A `Research Run` is one recoverable execution, branch, replication, retry, or continuation. It pins a Research Environment snapshot, Protocol versions, and every plan revision. It resumes from durable events and never depends on one browser session or a single AI request.

After a Run reaches a terminal state, an authorized user can preview and create another Run from it. Platform clones the source Run's exact Research Environment, records the source Run plus environment and result digests in `run_origin`, starts a new plan lineage, and leaves all previous Actions and scientific assets unchanged. This makes retry and replication reproducible rather than silently adopting newer Protocol, Knowledge, Tool, executor-policy, or resource-definition versions. A Task may have only one non-terminal Run at a time in the current runtime; Task-level deadline and budget ledgers continue to govern every Run.

A Run declared as a replication also creates a deterministic comparison boundary. Platform resolves the exact source Run, verifies its pinned environment and result digest, prefers its immutable human-finalized Result Package snapshot, and compares effective Research Environments after excluding only lineage metadata. Source Evidence comes only from that source package; replication Evidence must be validated and belong to the current Run. Completion requires a structured outcome, every original success criterion in its original order, a rationale per criterion, explicit deviations and limitations, and Evidence from both sides for any conclusive judgment. The authorized human's assessment is sealed into the replication Result Package with the source, target, context digest, reviewer, time, and optional advisory-review reference.

### Research Action

A `Research Action` provides a common orchestration envelope without collapsing domain semantics into one generic JSON table. Actions share lifecycle state, dependencies, idempotency, preview digest, executor, and timestamps. Typed implementations retain their own contracts:

- Protocol Run
- Tool Job
- Human Work Item
- Instrument Job
- External Service Job
- Approval Request
- Resource Reservation
- Wait Event

Protocol Run, Human Work Item, Tool Job, Instrument Job, External Service Job, Resource Reservation, and Wait Event now use this lifecycle contract. Future dedicated approval-request types extend the same boundary as their executor integrations arrive.

Typed Human Work, Tool, Instrument, External Service, Resource, and Wait results are appended to bounded result channels in the Run's durable AIRA state. Both the next-action planner and the legacy AIRA Method receive those channels as untrusted evidence. This preserves the semantic distinction between execution output, Records, and Protocols while ensuring later planning and conclusions do not lose operational results.

### Protocol and Capability

A `Protocol` is a repeatable, scientifically meaningful, versioned method with defined inputs, outputs, evidence requirements, and validation rules. It may describe experimental, literature, computational, data-processing, analytical, evaluation, or reporting methods.

`Capability` does not replace Protocol. The Capability Registry is a current, composed view over Protocols, tools, people and skills, equipment, services, resources, availability, and policy. It is not a second method source of truth.

Platform derives the registry view from the Project's current Protocol versions, the built-in versioned structured Human Work contract, the instance's allowlisted digital tools, Lab resource-type revisions, allowlisted instrument commands, external-service contracts, and Compute Environments. Creating a Research Task explicitly selects executable capabilities, pins their source versions in `airalogy.research-environment.v2`, and records the initial human, Platform-worker, or selected external-service binding. A concrete instrument command and its approved booking are intentionally resolved later; their exact Gateway binding and policy revision are captured by the Action preview before confirmation. Runtime and manual controls reject an executable capability that is absent from the relevant snapshot or whose pinned implementation version is no longer available. Resource definitions remain requirements, not executable methods; concrete reservation and consumption are resolved at Action time.

Lab Owners and Managers can add version-specific Executor Binding overrides from Project Research. A Protocol or structured Human Work binding may resolve to the future Task owner, directly to a current Lab member who can run Research in that Project, or to a governed skill pool. An Instrument binding must resolve the exact command revision to its Lab-owned Gateway, while an external-service binding must resolve the exact offering version to its registered provider; neither physical nor external work can use read-only auto-approval. Human Executor profiles are revisioned Lab records of availability windows, maximum concurrent work, and skill claims with levels, management verification, and optional expiry. Skill-pool resolution accepts only available profiles with every required verified and unexpired skill plus current `research.run` permission, then selects the lowest normalized active workload, active item count, and stable user ID in that order. The selected person, profile revision, matched skill evidence, workload, capacity, and digest are pinned in the Research Environment.

Each binding and profile change uses preview and confirmation and appends an immutable audit snapshot. A binding can require approval, deny use, or allow only an internal read-only Tool; it can also restrict Projects, autonomy levels, Actions per Run, and required human skill level. Later policy or profile edits never rewrite a captured Research Environment or confirmed Action. Before dispatch, Platform locks and rechecks the relevant membership, qualifications, provider, Gateway, command, contract, booking, and capability limits; revocation, expiry, saturation, or target drift therefore fails closed. Tasks captured before external-service bindings existed retain the prior safe default of mandatory approval. Manual human assignment, instrument execution, and service ordering remain available without AI through the same preview-confirm path.

Actionable handoffs are projected from the append-only `work_item.assigned` and `approval.requested` events into a private Research attention inbox in the same database transaction. Starting or completing the work, deciding its approval, cancellation, or reassignment closes the corresponding stale reminder transactionally. The inbox is the authoritative reminder path and is filtered again by current Research access, so former members cannot read stale task context. An optional SMTP channel creates a separate durable delivery record and retryable persistent job. Immediately before sending, it rechecks that the reminder remains open, current Research access, and the user's current address; resolved work, changed authority, or changed identity skips the stale delivery. Its destination is masked in the API, a deterministic message ID limits accidental duplicate presentation, and terminal delivery failure is visible without changing or blocking the underlying work item. Email is disabled by default and never carries permission or execution authority.

Assets, coordination objects, resources, notifications, approvals, reservations, waits, audit events, and payments are not forced into Protocols. Platform supports progressive formalization:

`Ad-hoc Action → Saved Preset → Protocol Draft → Reviewed Protocol → Validated SOP`

## Scientific and operational state

Planning reads two state spaces:

- **Epistemic State**: question, hypotheses, papers, Records, Evidence, Claims, Knowledge, and uncertainty.
- **Operational State**: Protocols, people, equipment, inventory, samples, budget, compute, permissions, approvals, and availability.

A `Research Environment` is a versioned snapshot of the methods, bindings, data/knowledge, resources, and policies available to a Run. Environment changes emit events that wake or replan Runs; Aira may not invent resources or assume availability.

## Execution loop

```text
Research Task
  → interpret goal and success criteria
  → create Research Plan Version
  → resolve Research Environment
  → propose the next Research Action
  → permission, policy, resource, and budget gates
  → execute, request approval, wait for a person, or wait for an external event
  → produce Record/DataAsset/Evidence
  → deterministic validation
  → update scientific and operational state
  → replan or terminate
```

The target plan is a versioned adaptive DAG supporting branches, parallel actions, cycles, retries, resource waits, and approvals. The current runtime supports a bounded parallel frontier for two to four independent read-only Tool Actions, an acyclic dependency graph of two to eight read-only Tool Actions, and a mixed acyclic graph of two to eight Protocol Run, structured Human Work, Tool, Resource Reservation, Instrument Job, External Service Job, isolated Compute, and typed Wait Actions. Dependency edges are persisted, roots alone are initially released, each downstream node enters its own permission/policy/approval/resource/budget/executor boundary only after every parent completes, and a failed or rejected parent deterministically skips its descendants before replanning. In a homogeneous Tool graph, a downstream node may bind one declared argument from a bounded structured-output path on a direct parent. Platform resolves the value only after that parent completes, records the source Action revision and output digest, reconstructs the downstream preview digest, and validates the complete input Schema before seeking approval or execution. Missing paths, out-of-range indexes, undeclared targets, or invalid resolved types fail closed and propagate through the graph. Mixed graphs currently use complete static inputs, existing approved equipment bookings, exact pinned service requests, and exact pinned DataAsset versions rather than cross-type result bindings. Protocol Record submission plus Human Work review and Resource, Instrument, and External Service completion, cancellation, and failure feed the same graph barrier, so the Run cannot replan while dependent human, physical, or outsourced work remains unresolved. A graph-planned Protocol Run keeps its Human Work Item unassigned until its parents complete and the normal approval and pinned Executor Binding checks pass; the assignee then uses the existing Record workflow, and only a validated matching Record completes the node. A graph-planned structured Human Work node follows the same dependency and assignment gates, validates a fixed typed-field and DataAsset-version contract, and remains immutable after submission until an authorized reviewer accepts it or requests changes. Acceptance seals the Action output, creates validated Evidence, and releases downstream nodes. A graph-planned Service request remains blocked without requesting a quote or creating an order approval; after every parent completes, Platform revalidates its immutable contract snapshot, permission, input Schema, and budget before entering the ordinary quote and order workflow. Cycles and arbitrary multi-agent graphs remain gated future work. Changes to the goal, success criteria, budget, or high-risk path create a new plan version and require renewed confirmation.

A bounded Specialist Agent panel is the deliberate exception to "one model does every cognitive step." Aira may propose two to four independent `aira.specialist` Tool Actions for one shared question, using distinct Literature Analyst, Experimental Designer, Data Analyst, or Research Critic roles. Every branch receives the same digest-bound snapshot of the Task, current strategy, reviewed non-Restricted Knowledge, and bounded typed Action results. The model has no web or Tool access inside the call; every finding and recommendation must cite a source reference from that snapshot, and Platform rejects unknown references. Specialist output is advisory, never Evidence, approval, an asset write, an order, code execution, or device control. Each call remains approval-gated, metered to the Task budget, durable, auditable, and limited to four per Run. Only after the entire panel settles does the coordinator return to the ordinary Planner and typed Action boundaries. Dependent agent conversations, recursive delegation, shared hidden memory, and arbitrary agent swarms remain unsupported.

## Human collaboration

A physical experiment is an asynchronous executor, not an exception:

1. Aira selects a published Protocol version and proposes parameters.
2. Platform resolves the executor, resources, and approval requirements.
3. Platform creates a durable Human Work Item and moves the Run to a waiting state.
4. A person executes through the deterministic Protocol/Record UI or a fixed structured Human Work form and submits Record/DataAsset evidence or typed results.
5. The API validates authorization, pinned capability and contract versions, Schema, resources, and completeness; generic Human Work also requires a separate authorized review.
6. A completion event wakes the Run and AIRA continues from real evidence.

Email, Slack, and similar channels are notification transports. The Human Work Item remains authoritative.

## Governance and autonomy

Every action type uses an `allow / ask / deny` policy. User-facing autonomy levels are Assisted, Bounded Autopilot, and Autonomous within Policy. There is no Lab-wide unlimited switch: automatic execution is admitted for one exact Lab + Capability version + Executor contract at a time, and a global autopilot option can never override a denial.

The Lab Research autonomy policy is a versioned governance asset. Assisted always asks for every Aira-proposed Action. Bounded Autopilot and Autonomous within Policy can automatically run only an internal read-only Tool, a passive typed Wait Event, or low-risk Compute whose pinned environment disables network access and whose cost and runtime remain inside explicit ceilings. People, instruments, resources, Protocol work, structured Human Work, and external-service commitments remain approval-gated.

An eligible digital boundary needs all three independent gates: the relevant category must be enabled in the Lab policy; the exact Executor Binding and technical, risk, cost, and runtime controls must permit the Action; and an unexpired evaluated autonomy grant must match the exact capability key, capability version, executor type, and executor-reference digest. Platform derives the current evaluation from the most recent ten terminal supervised Actions for that exact target. Manual Actions and Aira Actions that passed through approval count as supervised; the current admission rule requires at least five completions and no failure or cancellation in the sample. A version, executor, or digest change creates a different target and cannot inherit the grant.

Only a Lab Owner or Manager can create, renew, or revoke a grant. The operation uses preview-confirm, records the evaluation snapshot and immutable audit, selects the allowed autonomy levels, requires a reason, and expires within one year. Policy and grant changes affect only Research Environments captured afterwards; every Run pins its exact policy and grant snapshot, while grant expiry is still checked at Action time. Revocation prevents the grant from entering future environments but does not rewrite an already captured Run, so urgent intervention requires pausing or cancelling that Run through its normal operational controls. Every Action records the final policy decision and reason.

Important writes follow one contract:

```text
express intent → generate draft → preview impact → user confirms
  → deterministic execution → return result, destination, and next step
```

Approvals bind to a preview version or digest and become invalid when source data changes. API authorization and policy checks are authoritative; hiding controls in the frontend is never a security boundary.

The P0 policy is intentionally fail-closed: a manually created Protocol or structured Human Work Action is `allow` only after its deterministic preview is confirmed, while every Aira-proposed human Action is `ask` at all autonomy levels. Approval activates that exact digest-bound Action and only then creates the Human Work Item. Rejection cancels the proposal, records the reason, and requests replanning. For eligible digital Actions, an `allow` decision still requires the exact Lab policy, Executor Binding, evaluated grant, risk, resource, time, and budget controls described above; a missing gate falls back to `ask` rather than broadening authority.

## Scientific reliability

Execution state and scientific outcome are separate. A correctly executed experiment may contradict the hypothesis or remain inconclusive; a negative result is not an execution failure.

Aira cannot declare success by itself. Validation records Schema/QC, Protocol compliance, calibration, controls, sample size, statistical thresholds, replication, deviations, and failed attempts. Structured phased and final conclusions include Claims, supporting and contradicting Evidence, uncertainty, anomalies, goal progress, capability gaps, and proposed next actions.

Before human completion, an optional independent Reviewer Agent receives the exact current Task, latest Run, Action ledger, Result Package, and scientific assets through a separate deep-model prompt. For a replication Run, the same prompt must also return the strict criterion-level comparison against the two scoped Evidence sets. The model call does not hold a database transaction; Platform rechecks the Task revision and full context digest after it returns. Evidence references outside the available context or the correct side of a replication are rejected, and the immutable recommendation explicitly separates support, contradiction, uncertainty, missing checks, risk flags, and any reproduction draft. It is advisory only: it cannot approve, mutate, or complete the Task. An authorized owner or research approver must deliberately copy it into the editable review, may change any field, and remains the recorded scientific decision-maker. With AI disabled, the same deterministic human review and replication form remain available.

Aira may also synthesize one editable Suggested Claim from an explicit set of validated Task Evidence. Its strict output must assess every selected Evidence item exactly once as supporting, contradicting, or contextual, explain each relation, bound the statement to those sources, and preserve material uncertainty. The model call holds no database transaction. Platform then locks and revalidates the Evidence and its referenced artifact versions, rejects a changed context, and signs a one-hour receipt bound to the user, Task, exact generation, and source digest. Preview and confirmation revalidate the same context, while a unique generation ID prevents replay. Users may edit the proposed statement, confidence, uncertainty, and relations before confirming; the original generated output remains in immutable provenance. The result is still a normal Suggested Claim that only a separately authorized human can review. Manual Claim creation and review remain available when AI is disabled.

The final `Research Result Package` contains the summary, goal status, Claims and confidence, Evidence, pinned Protocol versions, Records, DataAssets, candidate Knowledge, Protocol improvement proposals, failed attempts, validation reports, unresolved questions, budget state, and a reproducibility manifest. Aira-driven and fully manual Runs use the same package builder; AI is not required to produce a complete result artifact.

Only the final human review seals a package. Platform stores one append-only snapshot per Run with the exact Task revision, reviewer, finalization time, and canonical SHA-256 digest. Every sealed read verifies the digest before returning content. Historical packages created before sealing was introduced remain readable and exportable but are explicitly identified as unsealed rather than being presented as immutable. The Task workbench can inspect the complete snapshot and export portable JSON or bilingual Markdown; both formats remain views of the same structured package.

## Knowledge, Log, and feedback loops

`Research Log` records what happened by combining immutable system events with revisioned human entries. `Knowledge` is curated, reusable, reviewable understanding; Paper Library is its literature-specific view. Record remains structured evidence from one Protocol execution and is not converted into a generic log entry.

Paper-to-Knowledge is an explicit proposal boundary. A user with Knowledge write access may ask Aira to draft one candidate from a scoped Paper Library entry. Platform discloses that the instance's configured AI provider will process the source and sends only the Paper metadata, library notes, and locally extracted full text that the same user can currently read; Restricted content also requires an explicit research-data-policy confirmation enforced by the API, and every ResearchFile read for the model is appended to the access audit. The full-text excerpt is bounded and treated as untrusted scientific content. No transaction remains open during model latency. After generation, Platform reauthorizes the Paper and every included ResearchFile, recomputes the source digest, and issues a one-hour receipt bound to the user, source entry, exact model output, and source snapshot. The candidate remains freely editable, but preview and confirmation recheck the current source and receipt, and a unique generation ID prevents replay. The saved object is ordinary versioned Knowledge with the original generation provenance: Project and Lab items remain Suggested until an authorized organizational review, while a user-confirmed Personal item becomes a private Draft because Personal Knowledge has no organizational review state. Neither state is evidence of independent validation. AI-disabled instances keep the complete manual Paper-to-Knowledge editor.

Knowledge-to-method flow is explicit and versioned. An authorized user previews the exact Knowledge revision and destination Project before opening Aira's Protocol generator. The Knowledge body is fetched through its normal access control rather than placed in a URL. Saving the resulting Protocol rechecks source visibility, scope, target-Project write permission, and revision freshness, then atomically records an immutable `Knowledge revision → Protocol version` link and source snapshot. Personal Knowledge may target an accessible Project; Lab and Project Knowledge stay within their own Lab or Project. Archived, superseded, stale, or inaccessible sources fail closed. A Protocol response shows a source only when the reader can still read both assets, so provenance cannot reveal Restricted Knowledge.

Completed structured Action output has an explicit promotion boundary. An authorized user selects the completed Action, previews the exact output digest, and confirms creation of pending Evidence. Platform locks the Action and seals one append-only snapshot containing its Task, Run, Action revision, kind, output, and canonical SHA-256 digest; reads and result-package exports verify that digest. The output is not accepted as scientifically valid until a human reviews the pending Evidence. This turns Tool, Instrument, Resource, Wait, External Service, and Compute results into an auditable scientific source without relabeling them as a Record or silently treating them as truth. Structured Human Work uses its submission review as this boundary: acceptance seals the same immutable Action output and creates validated Evidence directly, so the assignee's submission is never self-validating.

The reverse flow is evidence-gated. A Project member with Knowledge write access may select only validated Evidence backed by an exact Record, DataAsset version, or immutable Action-output snapshot, preview the destination and source set, and create editable Project-scoped Suggested Knowledge. Confirmation locks and revalidates every Evidence row, binds the preview digest to its review state and immutable source version, and stores a source snapshot plus an exact `Evidence → Knowledge revision` link. The result is still a candidate: it becomes reviewed organizational Knowledge only through the separate Knowledge review capability. Pending or rejected Evidence, external links, papers, and existing Knowledge cannot enter through this path, and AI availability is not required.

Protocol evolution uses a separate, method-specific gate. An authorized user selects a Protocol version already pinned to the Research Task plus validated Record, DataAsset, or immutable Action-output Evidence, previews the exact version, Evidence snapshots, rationale, and proposed changes, then creates a Suggested `Protocol Improvement Proposal`. When AI is available, Aira may prepare the editable title, rationale, and proposed changes from that same pinned context. Platform does not keep a database transaction open during the model call; after the response it revalidates the sources and issues a user-, Task-, Protocol-, context-, and expiry-bound signed receipt. The receipt and exact generation snapshot are verified again when the user previews and confirms, and one generation ID can be confirmed only once. Editing remains allowed and is recorded as Aira-assisted, not as approval. A research approver who can also update that Protocol must review the proposal before the existing Protocol Editor can open an editable version draft. Saving re-locks the proposal and Protocol, requires the reviewed revision to remain current and unapplied, and rejects the write if the Protocol has advanced beyond the pinned base. A successful save creates a normal higher Protocol version, marks the proposal Applied, and records the exact Evidence → proposal → Protocol-version provenance. It never mutates an existing version or changes a live Run's pinned environment. If AI is disabled, the complete manual path remains available.

Three connected loops stay distinct:

1. Research execution: Protocol/Action → Record/Evidence → phased state → next Action.
2. Protocol evolution: Records/DataAssets → improvement proposal → expert intent review → editable Protocol Draft → validated new version/SOP.
3. Knowledge evolution: Runs/Evidence → Suggested Knowledge → review → Project/Lab Knowledge.

Aira may create proposals and Suggested Knowledge. It never silently edits a published Protocol or switches a live Run to a different version.

## Resources, instruments, and external services

Planning reserves resources; execution confirms consumption or release. A Task now pins the selected Lab resource-type revisions as requirements without pretending that transient availability is part of the method. For a manual Action, the user selects and preview-confirms a concrete resource. Aira may instead request only a pinned resource type, exact inventory quantity and unit, or equipment window; Platform deterministically selects a concrete candidate within the requesting user's permissions, then always asks for approval. Approval revalidates the selected revision, access, balance version or booking window under the authoritative ledger before committing anything. The reservation is linked one-to-one to the Research Action while the existing inventory and booking ledgers remain authoritative. Balance-version changes, insufficient stock, schema drift, booking conflicts, and unauthorized Restricted resources fail closed. Equipment policies may leave the Action waiting for a second, resource-custodian approval; synchronization resumes the Run from the authoritative booking state. When a validated Record references the inventory reservation, committing its resource fields atomically writes the authoritative inventory event and an append-only `ResearchResourceConsumption` linked to that exact Record revision. Partial use preserves the remaining reservation; full use closes it. Retries reuse the same event, and the Task exposes every consumption with a link back to its Record while also returning the typed result to subsequent Aira planning. Explicit release and Task terminal transitions return outstanding commitments with audit events.

At each planning boundary, Aira receives only a bounded, permission-filtered live view of accessible inventory balances, units, lot expiry dates, equipment booking policy, and busy windows. Unauthorized and Restricted resources never enter that view. If deterministic reservation fails, Platform records the exact request and reason as an audited planning constraint and gives the planner one opportunity to choose a valid alternative. A repeated equivalent failure opens a typed `resource.available` Wait with a stable idempotency key, so the Run cannot loop or silently relax the scientific requirement.

A Task may also pin a deadline and a single-currency budget ceiling. Budget changes append immutable reserve, release, expense, or credit entries through a revision- and digest-bound preview-confirm flow; reservations and actual costs remain separate so the audit trail does not erase prior commitments. Platform recomputes the ledger at confirmation and before every new Protocol, Tool, Wait, Resource, Instrument, External Service, or Compute Action. A stale preview, mismatched currency, negative balance, or over-budget entry fails closed. Provider-reported model cost is appended idempotently as an actual expense when its currency matches the Task, and crossing the ceiling pauses the Run before that model response can materialize another plan or Action. Missing or different-currency model charges remain in the immutable usage meter for explicit accounting; Platform never invents a price or exchange rate. Exhausting the ceiling through any recorded entry pauses the active Run immediately; a reached deadline or budget detected elsewhere pauses it at the next runtime boundary with an explicit `stopped_time` or `stopped_budget` outcome. An authorized amendment replaces the whole current boundary through the same revision- and digest-bound flow, preserves old and new values plus the reason in an append-only event, and refuses to change or remove a budget currency after ledger activity. It never resumes a paused Run automatically; continuation remains a separate explicit transition.

Inventory includes lots, expiry, location, containers, quantity, and sample lineage. Equipment includes capability, schedule, calibration/maintenance, risk, and output formats. Budgets distinguish total, reserved, and actual cost. People are constrained by skills, certification, availability, workload, permissions, and approval authority.

Sample is a governed Resource semantic, not a second inventory system. A resource-definition revision opts into the `sample` capability and supplies discipline-specific fields such as specimen class, source, collection context, storage, biosafety, or use restrictions. Stable Resource identity, revisions, Restricted access, lots, containers, locations, and quantities continue to use the shared resource ledger. Sample identity lineage uses controlled `derived_from`, `aliquot_of`, `split_from`, and `pooled_from` edges. Manual assertions require read and operate access to both Samples and use preview-confirm against their exact current revisions; confirmation locks both resources, rejects cross-Lab edges, duplicate direct origins, self-links, and cycles, then appends an immutable reasoned event. Record input-to-output lineage remains automatic. Neither lineage nor external-service custody changes inventory quantity; transfers, consumption, and disposal remain separate authoritative events.

Platform does not need to replace a complete ERP or LIMS. Small Labs can use minimal native modules; mature organizations can connect existing systems. Platform owns normalized references, requirements, reservations, Action links, authorization, and audit.

External research services use the same separation between a versioned capability and a governed execution. A Lab service manager registers a provider through preview-confirm, then publishes immutable offering revisions with local-only request/result JSON Schemas, version, risk, quote policy, optional base price and currency, SLA target, sample requirements, logistics policy, and terms. Task creation may pin an approved offering's exact provider and contract revision into the Research Environment. This proves what the Run is allowed to request, but it is not an order, payment authorization, shipment, or result. Provider edits or later offering revisions never rewrite an active Task's snapshot.

An External Service Job is the governed execution object. The Aira planner can select only an exact offering pinned to the Research Environment and submit a request that validates against its pinned input Schema; this creates a draft request, never an order. Aira and manual requests converge on the same state machine. A provider quote, or the pinned catalog price, becomes an immutable quote and creates a digest-bound order approval. Approval re-resolves the pinned contract, checks quote validity and Task currency/limit under lock, then reserves the exact amount; no approval means no order or sample-transfer state. Fulfilment updates and failures are explicit transitions. Sample custody is an append-only sequence over authorized Lab resources and optional containers, without pretending that custody alone consumes inventory. Result receipt validates the pinned result Schema, links exact Task DataAsset versions, releases the approved reservation, records actual expense, and feeds a typed Service result back into the Run. Actual cost above the approved quote fails closed and requires a new approval boundary. AI-disabled instances retain this complete deterministic flow.

Compute uses the same separation between a versioned capability contract and a later execution object. A Lab compute manager creates or revises a `Compute Environment` through preview-confirm. Each immutable revision pins an OCI image by SHA-256 digest, runner protocol version, Python/R language allowlist, CPU/memory/GPU/timeout/output ceilings, network denial or an exact egress-host allowlist, local input/result JSON Schemas, software manifest, risk, and optional hourly cost. A Research Task may pin an exact revision; later changes never rewrite the captured environment.

The execution plane is a separately authenticated `Compute Runner`. A Lab compute manager creates or rotates its credential through preview-confirm, limits concurrency, and binds the Runner only to reviewed, exact Compute Environment revisions. A binding never follows a mutable environment lineage automatically. The Runner status contract reports its protocol/backend/capacity and four mandatory isolation controls: non-root execution, read-only root filesystem, network isolation, and no host mounts. Missing controls make the Runner ineligible rather than weakening the policy.

A `Compute Job` is the approval-gated execution object. Manual requests and Aira proposals converge on this same object and bind source bytes by SHA-256, language, a Schema-validated JSON input, exact Project DataAsset file versions, explicitly declared output files, the Task-pinned environment revision, resource and network limits, and the maximum estimated cost. The planner sees only currently usable pinned revisions backed by an authorized Runner and eligible current DataAsset versions; it cannot name an arbitrary image, asset, path, secret, or network destination. Each output declaration pins a safe mount name, media type, asset kind, maximum byte count, requirement flag, and destination metadata before approval. Aira-generated source is additionally response-size bounded. Preview confirmation or a validated planner proposal creates a proposed Action and a separate approval, where the complete source, source digest, exact inputs, limits, cost, and outputs remain inspectable. Approval re-resolves the immutable contract and authorized Runner binding under lock, then reserves the maximum cost when the Task has a budget. Selection of an environment or Runner is never itself permission to execute.

An execution-ready Runner pulls only queued jobs for environment revisions explicitly bound to it. Platform returns a canonical `airalogy.compute-job.v1` envelope, HMAC signature, and short job-scoped lease. The lease alone authorizes downloads of the exact input blobs and uploads to the exact declared output IDs. Start, heartbeat, and bounded output upload renew it; an expired pre-start lease can be safely requeued, while a lease lost after execution starts fails closed to a paused Task because execution outcome is uncertain. Task pause or cancellation becomes an explicit Runner cancellation request. Completion validates declared usage against hard limits, the structured result against the pinned Schema, and every output receipt against its stored byte count, media type, and SHA-256. Only then does Platform create Project-scoped `ResearchFile`, draft `DataAsset`, and version provenance linked to the Job, Action, environment revision, source digest, and declared output. It converts the maximum reservation into deterministic actual cost, records immutable events, and appends a typed Compute result for replanning or manual continuation. Failure and acknowledged cancellation record partial usage when provided and release only unused reservation; uploaded but incomplete files never gain a logical permission-bearing asset.

Platform never runs research code in its API process or mounts a container-runtime socket into it. The repository provides the independently supervised reference process under `apps/compute-runner`. It verifies the signed envelope and exact input/output paths again, streams checksum-verified inputs into a job-specific size-bounded tmpfs volume managed by Docker or Podman, and executes the digest-pinned image as UID/GID 65532 with a read-only root filesystem, dropped capabilities, resource limits, and no host bind mounts. Network-denied jobs use the isolated engine network; an allowlisted job is accepted only when its exact host set maps to an independently enforced, preconfigured container network. After the research container stops, a digest-pinned read-only helper alone measures, hashes, and streams declared output files; the Runner cannot nominate an arbitrary host or container path. An owner-only crash journal stops uncertain containers before reconciliation and replays uploads and callbacks idempotently without accepting another job.

Instrument integration progresses through data import, guided execution, device-confirmed assisted control, and policy-bounded closed-loop automation. Aira never sends arbitrary commands directly to equipment. At a next-action boundary it may choose only an exact command ID that Platform supplied from the active Research Environment and the requesting user's approved equipment bookings, plus arguments that satisfy the command input Schema. Platform deterministically selects the earliest eligible booking, pins the full command and resource state, and always requests human approval. Approval locks and re-resolves the command, Gateway, equipment, permission, booking, Schema, and competing-job state before the Action becomes queueable. A local Instrument Gateway accepts only signed, structured, allowlisted jobs and provides state checks, audit, and governed stop requests.

The Gateway boundary and its first execution loop are implemented. A Lab Owner or Manager registers a Gateway through preview-confirm and receives a high-entropy credential only once. The stored credential is a digest; rotation invalidates the previous value and is blocked while that Gateway owns an active lease. Each allowed command is tied to one exact equipment Resource revision and versioned command key, with local-only JSON Schemas for inputs and results, a timeout, a risk level, mandatory physical-device confirmation for medium- and high-risk operations, and a pinned safety contract. The contract can require named hardware interlocks, local operator presence, and emergency-stop availability. New high-risk revisions must require both operator presence and emergency stop. All configuration changes create immutable audit snapshots, and disabling a Gateway or command blocks future leasing.

An Instrument Job must reference a resource type already pinned in the Research Environment, the exact allowlisted command revision, and an approved unexpired equipment booking. The Gateway independently authenticates and pulls a canonical signed envelope under a short-lived one-job lease. Immediately before start, the independently installed local adapter reads the required hardware conditions and returns a bounded attestation. The Gateway and Platform both reject a missing or false required interlock; Platform records the accepted attestation with the Job. It must then start within the booking window, provide the required device-local confirmation reference, renew the lease by heartbeat, and return a result that satisfies the pinned output Schema. Platform never retries a physical operation automatically. An expired running lease, timeout, booking end, explicit stop, Task pause, failure, or cancellation pauses the Run and requires Gateway acknowledgement plus human equipment inspection. This is a governed remote-stop protocol, not a claim that software can guarantee an electrical emergency stop; hardware interlocks remain authoritative.

An `Instrument Control Session` is the next bounded tier; it is not a remote script or a privileged model channel. An authorized user previews and confirms either an acyclic `bounded_sequence` or a deterministic `feedback_loop`, one approved booking, one Gateway and equipment Resource, one to twenty step templates, an entry step, at most fifty executions, and at most twenty-four hours. Every template pins the exact command revision, input and output Schemas, Executor Binding, safety contract, literal arguments, and one explicit transition. A feedback guard may read only a bounded object path from that step's already Schema-validated result and apply `eq`, `ne`, numeric ordering, membership, or existence; it cannot evaluate code, interpolate an untrusted value into a command, or invent an argument.

The session never reaches the device directly. It creates one ordinary Instrument Job, waits for its validated terminal result, records the chosen transition, rechecks permission, booking, Resource revision, command revision, Executor Binding and competing use, and only then creates the next ordinary Job. Missing paths take the explicit false branch; an invalid ordered comparison, stale pin, unavailable booking, reached step/time limit, or explicit `pause` target fails closed into human review. The initial confirmation can release the entry step, but every later high-risk command pauses for a new preview-confirm checkpoint. Stop, Task pause, cancellation, job failure, timeout, lost heartbeat and Gateway safe-stop acknowledgement propagate to the session. Physical commands still have no automatic retry. This produces deterministic bounded feedback while retaining the existing per-command lease, device confirmation, preflight attestation, audit and emergency-stop boundary. It works with AI disabled.

When AI is enabled, Aira has a separate draft-only entry. The user first fixes the booking, mode, template limit, execution limit, and duration, then describes the desired equipment process. Aira receives only currently authorized commands on that booking and may return literal inputs plus explicit transitions. The response is parsed by a strict schema, rejected if it names anything outside the catalog or violates an input Schema or graph bound, and revalidated against the current Task, Run, booking, permissions, command revisions, safety contracts, and Executor Bindings after model latency. It creates no Session, Action, Job, approval, or reservation. The user can edit every field; only the ordinary deterministic preview-confirm endpoint pins the final program and releases its first Job. The planner's automatic next-action loop still proposes only individual Instrument Actions and cannot invoke this drafting endpoint as device authority.

The runtime contract is pull-only under TLS. The Gateway authenticates with `X-Airalogy-Gateway-Token` and calls `POST /instrument-gateway/v1/jobs/lease`. A successful response contains a canonical `airalogy.instrument-job.v1` envelope, a job-scoped lease token, and an HMAC-SHA256 signature. The Gateway verifies the signature with `SHA256(gateway credential)` as the HMAC key, then sends the lease token only in `X-Airalogy-Instrument-Lease` for `start`, `heartbeat`, `complete`, `fail`, or `stopped`. Secrets are never accepted in query parameters or command payloads. A heartbeat response with `stop_requested: true` is authoritative; the adapter must stop through its hardware-specific safe-stop routine and acknowledge `stopped`.

The repository includes a standalone, standard-library-only Gateway runtime and adapter SDK under `apps/instrument-gateway`. It refuses cross-origin redirects, unsigned or stale envelopes, and command versions absent from a separately installed local adapter. A single active lease is atomically journaled with owner-only permissions before device start. Completion, failure, and stop acknowledgements are replayable after uncertain network outcomes; a restart during possible physical execution invokes the adapter's idempotent safe-stop before reconciliation. Shutdown, control-channel loss, failed safe-stop, or a worker that will not stop prevents the process from accepting another job. Platform-delivered code and arbitrary shell execution are outside this boundary.

## Responsibility boundaries

| Subsystem | Authoritative responsibility |
| --- | --- |
| Platform | Tasks, runtime, permissions, policies, resources, approvals, notifications, audit, and scientific assets |
| Masterbrain/AIRA | Goal interpretation, strategy, planning, Action selection, result interpretation, and replanning |
| Protocol/Engine | Executable methods, Schema, validation, deterministic computation, and Record generation |
| Scholar/Literature Provider | Optional search, DOI resolution, and metadata candidates; never direct writes to formal assets |
| Executor/Gateway | Human, tool, instrument, or external-service execution within explicit contracts and policy |

## Delivery phases

### P0: end-to-end human-in-the-loop execution

- Research Task/Run/Action/Event and plan versions
- durable planning and replanning through the current AIRA Method
- Protocol Run plus Human Work Item
- assignment, in-app work queue, and optional notifications
- prefilled Protocol execution, Record/DataAsset submission, validation, and event-driven resumption
- pause, resume, cancel, idempotency, retry, authorization, and audit
- manual planning/execution with AI disabled
- Research Result Package
- compatibility with legacy Protocol Workflow

The acceptance benchmark is a CNT-style iterative experiment: Aira selects the next Protocol, a person submits a real Record, the Run resumes and forms a phased conclusion, and execution continues until a terminal result. Its platform-state and governance contract is now part of the executable acceptance suite.

### P1: Knowledge and digital automation

- private Lab Paper Library, Knowledge, Evidence, and Claim
- optional Scholar Literature Provider
- literature research, Python/R compute, and external tool Actions
- governed Paper → Suggested Knowledge → Protocol Draft and Record/DataAsset → Suggested Knowledge (delivered)
- fermentation-style multi-source data integration benchmark (delivered in the executable acceptance suite)

### P2: operational resources and governance

- derived Capability Registry and task-scoped version pinning (delivered)
- governed, Lab-configurable Protocol, structured Human Work, Tool, Instrument Gateway, and external-service Executor Bindings; direct eligible-member or verified-skill-pool assignment; Task- or Action-time pinning; and dispatch-time revalidation (delivered)
- revision-pinned resource requirements plus inventory/equipment reservation and release Actions (delivered)
- Aira resource requests, deterministic candidate resolution, approval, and stale-state rejection (delivered)
- Task deadlines, budget ceilings, immutable budget ledger, execution stop gates, and audited explicit limit amendments (delivered)
- revisioned people availability, capacity, and verified skills, governed Sample resource semantics and acyclic immutable lineage, and same-currency provider-reported model-cost ingestion (delivered)
- immutable Compute Environment catalog, scoped permissions, preview-confirm revisions, exact Research Environment pinning, governed Runner identity/readiness/environment bindings, manual and Aira-planned approval/budget/lease/result Compute Jobs, declared output ingestion, draft DataAsset registration, and an independently supervised reference Runner (delivered)
- Record-linked inventory consumption completion and immutable traceability, versioned risk policy and bounded automatic-execution thresholds, and resource-aware replanning with a typed availability Wait (delivered)

### P3: instruments, RaaS, and self-improvement

- Instrument Gateway registration, governed command allowlists, signed job leasing, hardware-specific preflight interlock attestations, heartbeat, validated result receipt, and acknowledged remote stop (delivered); human-confirmed bounded sequences and deterministic result-guarded feedback loops that reuse ordinary Instrument Jobs and pause before later high-risk commands (delivered)
- governed provider catalog, immutable service contracts, scoped permissions, and exact Research Environment pinning (delivered)
- Aira-planned and manual external-service requests sharing quote, order approval, budget reservation, logistics, chain of custody, fulfilment, and result receipt governance (delivered)
- evidence-backed, reviewed Protocol improvement proposals and exact new-version lineage (delivered without AI dependency)
- independent advisory Reviewer Agent, a source-grounded two-to-four-role Specialist Agent panel, formal human-finalized reproduction evaluation, bounded parallel and dependent read-only Tool graphs, and bounded mixed Protocol/structured Human Work/Tool/Resource/Instrument/External Service/Compute/Wait graphs (delivered); bounded Instrument feedback cycles are isolated inside their explicit control-session contract, while arbitrary Action-graph cycles, dependent agent conversations, and unrestricted multi-agent execution remain future work
- protein-purification method evolution and OT-2 governance benchmarks (delivered in the executable acceptance suite)

### Executable acceptance suite

Run `pnpm research:benchmarks` from the repository root to exercise the four stable cross-cutting scenarios defined in `benchmarks/research-automation/scenarios.json`: CNT human-in-the-loop iteration, fermentation multi-source integration, protein-purification method evolution, and OT-2 governed instrument control. The suite checks typed state transitions, real Record boundaries, immutable Action-output Evidence, human-finalized Result Packages, exact Protocol-improvement lineage, bounded device programs, safety interlocks, and fresh review before later high-risk physical steps. It also carries explicit prohibited shortcuts so a future refactor cannot silently turn model output into a Record, auto-apply an AI proposal, bypass a safety check, or retry physical work.

These are software acceptance benchmarks, not synthetic scientific success claims. They prove Platform orchestration and governance contracts. A real deployment must still qualify its Protocols, operators, device adapters, interlocks, data quality, and scientific conclusions in the target laboratory.

## Definition of complete

A phase is complete only when its vertical slice includes database migration, API authorization, backend validation, complete frontend states, English and Chinese localization, AI-on and AI-off paths, errors and recovery, versioning/audit, compatibility, tests, production build, documentation, and changelogs. A Schema-only, chat-only, UI-only, or AI-only demonstration is not complete.
