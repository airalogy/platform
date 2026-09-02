# Research automation

Research automation in Airalogy starts from a bounded `Research Task`, not from an unconstrained chat. A Task keeps its goal, success and stop criteria, Lab and Project, pinned Research Environment, Runs, Actions, Evidence, Claims, and final human review together.

## Start a Research Task

1. Open **Research** and create a Task in the correct Project.
2. State a testable goal, success criteria, and stop conditions. Add a deadline and one-currency budget ceiling when the Task must operate inside hard time or cost boundaries.
3. Select any Protocol versions, digital tools, reviewed Knowledge, and Lab resource types that may guide or constrain the work. A Protocol is optional when the research path only needs governed digital tools or an external result.
4. Preview the destination and captured environment, then confirm creation.
5. Start the Task. If Aira is available, it can advance the plan until it reaches a human, approval, tool, external-result, or final-review boundary. If AI is unavailable, the same Task remains usable through explicit Actions.

Changing a Protocol or Knowledge item later does not silently change the captured Research Environment. Create a new plan or Run when the new version should apply.

## Turn Knowledge into a Protocol draft

Open **Knowledge**, switch to **Knowledge Notes**, and choose **Generate Protocol draft** on an active item. Review the pinned source revision, choose an eligible target Project, and open the Aira draft. Platform loads the protected Knowledge content into the editable generator without putting it in the URL. Review and revise the generated AIMD, then choose **Save Protocol** and confirm the Project destination.

The Protocol does not exist until that final confirmation. At save time, Platform checks that you can still read the Knowledge, can create Protocols in the Project, and are still using the same revision. A changed, archived, superseded, cross-scope, or inaccessible source is rejected instead of silently producing an untraceable asset. The accepted Protocol version retains immutable Knowledge provenance. When AI is disabled, the entry is hidden while template, reuse, import, and manual Protocol creation remain available.

## Turn validated results into candidate Knowledge

On a Research Task, register a Record or exact DataAsset version as Evidence and have an authorized reviewer validate it. In **Scientific assets**, choose **Propose Knowledge**, write the reusable finding, method, decision, or note, and select one or more validated Evidence items. Preview the Project destination and exact source set, then confirm.

Platform creates editable Project-scoped Suggested Knowledge and preserves immutable Evidence snapshots and version links. It does not declare the candidate true or adopted. Open Project Knowledge to revise it and use the separate **Review and adopt** action when a Knowledge Reviewer has assessed the evidence. Pending, rejected, or non-Record/DataAsset Evidence is intentionally unavailable. This deterministic path works when AI is disabled.

## Improve a Protocol from validated Evidence

In **Scientific assets**, choose **Propose Protocol improvement**. Select a Protocol already pinned to the Task, describe the scientific rationale and concrete proposed changes, and attach validated Record or DataAsset Evidence. Preview the exact Project, base Protocol version, and immutable Evidence snapshots before confirming. This creates a proposal only; it does not edit the Protocol.

An authorized research approver who can update the Protocol must inspect and accept the proposal. Choose **Create version draft** only after that review, then edit the copied package in the normal Protocol Editor. When saving, choose a version higher than the current Protocol and confirm the package. Platform rechecks the reviewed proposal, Evidence lineage, and base version under lock. If another version was published in the meantime, or the proposal changed or was already applied, saving stops and the proposal must be recreated against the latest method. A successful save marks the proposal Applied and links it to the exact new Protocol version. Existing versions and active Runs remain unchanged. This complete path also works with AI disabled.

When AI is enabled, select the target Protocol and Evidence first, optionally give Aira a focus or constraint, then choose **Draft with Aira**. Review and freely edit the returned content before previewing it. The signed generation receipt expires after one hour and cannot be reused after confirmation; if the scientific context changes, regenerate the draft. Aira never performs the expert review or applies the Protocol version. With AI disabled, all manual fields and the remainder of this flow stay available.

## Repeat, replicate, or continue a Run

After the current Run and Task are completed, failed, or cancelled, choose **New Run** on the Task page. A completed scientific result must receive its human review before another Run is opened. Select any terminal source Run, classify the relationship as retry, replication, or continuation, and explain the intended difference. The preview shows the new Run number, source, destination, and exact Research Environment digest before confirmation.

The new Run preserves every earlier execution and scientific asset and inherits the source environment exactly. It does not automatically adopt later Protocol, Knowledge, Tool, executor-policy, or resource-definition changes. The Task returns to Draft so the next execution starts explicitly, while its original deadline and shared budget ledger still apply. The Run lineage panel keeps each result and human-reviewed conclusion available for comparison.

## Choose the correct Action

- **Protocol work** assigns a version-pinned method to a person. Lab managers can configure the corresponding Executor Binding to use the future Task owner or a specific eligible Project member. The person completes the normal Record form; a validated Record returns as Evidence without becoming a generic chat message. Platform checks the assignee's current membership and permission again at dispatch time.
- **Research tool** runs an allowlisted, version-pinned digital capability such as reviewed Knowledge search or an optional literature provider. Inputs and outputs are Schema-validated, time-limited, retryable, and recorded in the execution ledger.
- **Wait for an external result** pauses the Run at a typed boundary for a person, instrument, or service. Select and confirm the expected result contract. The generated event key is an immutable delivery reference; in the current version, an authorized user records the received result from the workbench.
- **Reserve resource** resolves a concrete resource from a resource type pinned in the Research Environment. For inventory, select a container, exact quantity, UCUM unit, and optional expiry. For equipment, select the booking window. Platform previews current availability and policy, rejects stale or conflicting confirmation, and records the authoritative inventory reservation or equipment booking behind the Action.

Aira can request a pinned resource type, quantity, unit, or equipment window, but it cannot pick an arbitrary hidden resource or reserve it directly. Platform selects an accessible candidate deterministically and presents the exact impact for approval. If inventory, permissions, the resource revision, or a booking window changes before approval, the proposal is rejected and must be replanned.

## Control time and budget

The Task page shows the pinned deadline and the budget's reserved, actual, committed, and remaining amounts. Users with research approval capability can record a reservation, release, expense, or credit. Each entry must be previewed and confirmed against the current Task revision and cannot be edited afterward. Release only an existing reservation; credit only an existing actual expense. Record the offset and the replacement as separate entries when correcting a mistake.

Platform checks these limits in the API before any new manual or Aira-created Protocol, Tool, Wait, or Resource Action. It rejects stale or over-limit writes, pauses immediately when a confirmed budget entry exhausts the ceiling, and otherwise pauses at the next runtime boundary after a deadline or budget limit is detected. The current version does not infer monetary cost from model, compute, inventory, or external-service usage; record those actual costs explicitly until an authoritative provider integration supplies them.

Search candidates remain Action output. Platform does not silently approve them as Knowledge, Evidence, or Claims.

At each next-action boundary, Aira first chooses between a pinned Protocol, an available Tool, a pinned Resource requirement, a typed external Wait, or finishing the path. This Action Planner does not execute arbitrary model output: Platform validates the chosen type, allowlist entry, pinned version, arguments, resource need, and result contract before creating an Action. Aira-proposed digital, resource, and human Actions are approval-gated until an explicit Lab policy allows that exact risk class.

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
