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

### Research Run

A `Research Run` is one recoverable execution, branch, replication, or retry. It pins a Research Environment snapshot, Protocol versions, and every plan revision. It resumes from durable events and never depends on one browser session or a single AI request.

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

Protocol Run, Human Work Item, Tool Job, Resource Reservation, and Wait Event now use this lifecycle contract. Instrument, external-service, and approval-request types extend the same boundary as their executor integrations arrive.

### Protocol and Capability

A `Protocol` is a repeatable, scientifically meaningful, versioned method with defined inputs, outputs, evidence requirements, and validation rules. It may describe experimental, literature, computational, data-processing, analytical, evaluation, or reporting methods.

`Capability` does not replace Protocol. The Capability Registry is a current, composed view over Protocols, tools, people and skills, equipment, services, resources, availability, and policy. It is not a second method source of truth.

Platform derives the first registry view from the Project's current Protocol versions, the instance's allowlisted digital tools, and the Lab's current resource-type revisions. Creating a Research Task explicitly selects Protocol and Tool capabilities, pins their source versions in `airalogy.research-environment.v2`, and records the initial human or Platform-worker executor binding. The runtime and manual controls both reject a Tool that is absent from that snapshot or whose implementation version is no longer available. Resource definitions are discoverable but remain requirements, not executable methods; concrete reservation and consumption are resolved at Action time.

Lab Owners and Managers can add version-specific Executor Binding overrides from Project Research. Each change uses preview and confirmation, increments the binding revision, and appends an immutable audit snapshot. A binding can require approval, deny use, or allow only an internal read-only Tool; it can also restrict Projects, autonomy levels, and Actions per Run. Task creation resolves these rules deterministically and embeds the exact binding revision, resolved executor, policy, and constraints. Later policy edits never mutate an active Run.

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

The plan is a versioned adaptive DAG supporting branches, parallel actions, cycles, retries, resource waits, and approvals. Changes to the goal, success criteria, budget, or high-risk path create a new plan version and require renewed confirmation.

## Human collaboration

A physical experiment is an asynchronous executor, not an exception:

1. Aira selects a published Protocol version and proposes parameters.
2. Platform resolves the executor, resources, and approval requirements.
3. Platform creates a durable Human Work Item and moves the Run to a waiting state.
4. A person executes through the deterministic Protocol/Record UI and submits Record/DataAsset evidence.
5. The API validates authorization, Protocol version, Schema, resources, and completeness.
6. A completion event wakes the Run and AIRA continues from real evidence.

Email, Slack, and similar channels are notification transports. The Human Work Item remains authoritative.

## Governance and autonomy

Every action type uses an `allow / ask / deny` policy. User-facing autonomy levels are Assisted, Bounded Autopilot, and Autonomous within Policy. Autonomy is granted per Lab + Capability + Executor after replay, shadow execution, and evaluation. A global autopilot option can never override a denial.

Important writes follow one contract:

```text
express intent → generate draft → preview impact → user confirms
  → deterministic execution → return result, destination, and next step
```

Approvals bind to a preview version or digest and become invalid when source data changes. API authorization and policy checks are authoritative; hiding controls in the frontend is never a security boundary.

The P0 policy is intentionally fail-closed: a manually created Protocol Action is `allow` only after its deterministic preview is confirmed, while every Aira-proposed human Protocol Action is `ask` at all autonomy levels. Approval activates that exact digest-bound Action and only then creates the Human Work Item. Rejection cancels the proposal, records the reason, and requests replanning; broader automatic `allow` rules require the later Lab policy, resource, risk, and budget controls.

## Scientific reliability

Execution state and scientific outcome are separate. A correctly executed experiment may contradict the hypothesis or remain inconclusive; a negative result is not an execution failure.

Aira cannot declare success by itself. Validation records Schema/QC, Protocol compliance, calibration, controls, sample size, statistical thresholds, replication, deviations, and failed attempts. Structured phased and final conclusions include Claims, supporting and contradicting Evidence, uncertainty, anomalies, goal progress, capability gaps, and proposed next actions.

The final `Research Result Package` contains the summary, goal status, Claims and confidence, Evidence, pinned Protocol versions, Records, DataAssets, failed attempts, validation reports, unresolved questions, and a reproducibility manifest. Human-readable reports are views over that structured package.

## Knowledge, Log, and feedback loops

`Research Log` records what happened by combining immutable system events with revisioned human entries. `Knowledge` is curated, reusable, reviewable understanding; Paper Library is its literature-specific view. Record remains structured evidence from one Protocol execution and is not converted into a generic log entry.

Three connected loops stay distinct:

1. Research execution: Protocol/Action → Record/Evidence → phased state → next Action.
2. Protocol evolution: Records → improvement proposal → Protocol Draft → expert review → new version/SOP.
3. Knowledge evolution: Runs/Evidence → Suggested Knowledge → review → Project/Lab Knowledge.

Aira may create proposals and Suggested Knowledge. It never silently edits a published Protocol or switches a live Run to a different version.

## Resources, instruments, and external services

Planning reserves resources; execution confirms consumption or release. A Task now pins the selected Lab resource-type revisions as requirements without pretending that transient availability is part of the method. For a manual Action, the user selects and preview-confirms a concrete resource. Aira may instead request only a pinned resource type, exact inventory quantity and unit, or equipment window; Platform deterministically selects a concrete candidate within the requesting user's permissions, then always asks for approval. Approval revalidates the selected revision, access, balance version or booking window under the authoritative ledger before committing anything. The reservation is linked one-to-one to the Research Action while the existing inventory and booking ledgers remain authoritative. Balance-version changes, insufficient stock, schema drift, booking conflicts, and unauthorized Restricted resources fail closed. Equipment policies may leave the Action waiting for a second, resource-custodian approval; synchronization resumes the Run from the authoritative booking state. Explicit release and Task terminal transitions return outstanding commitments with audit events.

A Task may also pin a deadline and a single-currency budget ceiling. Budget changes append immutable reserve, release, expense, or credit entries through a revision- and digest-bound preview-confirm flow; reservations and actual costs remain separate so the audit trail does not erase prior commitments. Platform recomputes the ledger at confirmation and before every new Protocol, Tool, Wait, or Resource Action. A stale preview, mismatched currency, negative balance, or over-budget entry fails closed. Exhausting the ceiling through a budget entry pauses the active Run immediately; a reached deadline or budget detected elsewhere pauses it at the next runtime boundary with an explicit `stopped_time` or `stopped_budget` outcome. Existing Records and ledger history remain intact; continuing requires an explicit future amendment flow rather than silent limit expansion.

Inventory includes lots, expiry, location, containers, quantity, and sample lineage. Equipment includes capability, schedule, calibration/maintenance, risk, and output formats. Budgets distinguish total, reserved, and actual cost. People are constrained by skills, certification, availability, workload, permissions, and approval authority.

Platform does not need to replace a complete ERP or LIMS. Small Labs can use minimal native modules; mature organizations can connect existing systems. Platform owns normalized references, requirements, reservations, Action links, authorization, and audit.

Instrument integration progresses through data import, guided execution, device-confirmed assisted control, and policy-bounded closed-loop automation. Aira never sends arbitrary commands directly to equipment. A local Instrument Gateway accepts signed, structured, allowlisted jobs and provides state checks, audit, and emergency stop.

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

The acceptance benchmark is a CNT-style iterative experiment: Aira selects the next Protocol, a person submits a real Record, the Run resumes and forms a phased conclusion, and execution continues until a terminal result.

### P1: Knowledge and digital automation

- private Lab Paper Library, Knowledge, Evidence, and Claim
- optional Scholar Literature Provider
- literature research, Python/R compute, and external tool Actions
- Paper → Knowledge → Protocol Draft and Record/DataAsset → Suggested Knowledge
- fermentation-style multi-source data integration benchmark

### P2: operational resources and governance

- derived Capability Registry and task-scoped version pinning (delivered)
- governed, Lab-configurable Protocol/Tool Executor Bindings and availability resolution (delivered)
- revision-pinned resource requirements plus inventory/equipment reservation and release Actions (delivered)
- Aira resource requests, deterministic candidate resolution, approval, and stale-state rejection (delivered)
- Task deadlines, budget ceilings, immutable budget ledger, and execution stop gates (delivered)
- people, instrument, and external-service Executor Binding adapters
- people and skills, sample semantics, compute, and automatic cost ingestion
- consumption completion, risk policy, approval thresholds, and resource-aware replanning

### P3: instruments, RaaS, and self-improvement

- Instrument Gateway and tiered control
- quotes, SLA, logistics, chain of custody, and result receipt for external research services
- Protocol evolution, independent Reviewer Agent, parallel/multi-agent execution, and reproduction evaluation
- protein-purification method evolution and OT-2 governance benchmarks

## Definition of complete

A phase is complete only when its vertical slice includes database migration, API authorization, backend validation, complete frontend states, English and Chinese localization, AI-on and AI-off paths, errors and recovery, versioning/audit, compatibility, tests, production build, documentation, and changelogs. A Schema-only, chat-only, UI-only, or AI-only demonstration is not complete.
