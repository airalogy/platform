# Research automation

Research automation in Airalogy starts from a bounded `Research Task`, not from an unconstrained chat. A Task keeps its goal, success and stop criteria, Lab and Project, pinned Research Environment, Runs, Actions, Evidence, Claims, and final human review together.

## Start a Research Task

1. Open **Research** and create a Task in the correct Project.
2. State a testable goal, success criteria, and stop conditions.
3. Select any Protocol versions, digital tools, reviewed Knowledge, and Lab resource types that may guide or constrain the work. A Protocol is optional when the research path only needs governed digital tools or an external result.
4. Preview the destination and captured environment, then confirm creation.
5. Start the Task. If Aira is available, it can advance the plan until it reaches a human, approval, tool, external-result, or final-review boundary. If AI is unavailable, the same Task remains usable through explicit Actions.

Changing a Protocol or Knowledge item later does not silently change the captured Research Environment. Create a new plan or Run when the new version should apply.

## Choose the correct Action

- **Protocol work** assigns a version-pinned method to a person. The person completes the normal Record form; a validated Record returns as Evidence without becoming a generic chat message.
- **Research tool** runs an allowlisted, version-pinned digital capability such as reviewed Knowledge search or an optional literature provider. Inputs and outputs are Schema-validated, time-limited, retryable, and recorded in the execution ledger.
- **Wait for an external result** pauses the Run at a typed boundary for a person, instrument, or service. Select and confirm the expected result contract. The generated event key is an immutable delivery reference; in the current version, an authorized user records the received result from the workbench.
- **Reserve resource** resolves a concrete resource from a resource type pinned in the Research Environment. For inventory, select a container, exact quantity, UCUM unit, and optional expiry. For equipment, select the booking window. Platform previews current availability and policy, rejects stale or conflicting confirmation, and records the authoritative inventory reservation or equipment booking behind the Action.

Aira can request a pinned resource type, quantity, unit, or equipment window, but it cannot pick an arbitrary hidden resource or reserve it directly. Platform selects an accessible candidate deterministically and presents the exact impact for approval. If inventory, permissions, the resource revision, or a booking window changes before approval, the proposal is rejected and must be replanned.

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

Cancelling a Task preserves existing Records, Action history, tool provenance, and scientific assets while preventing unfinished work from resuming it. Outstanding inventory reservations and pending or approved equipment bookings are returned automatically; explicit early release also uses preview and confirmation.

## Permissions and safety

Research Actions use current Project and resource permissions enforced by the API. A tool or resource type being visible does not bypass Knowledge visibility, Restricted content grants, object-level resource access, inventory-operation rights, equipment-booking rights, or Project access. External results require an authenticated user with research execution capability; the event key alone is not authorization. Rejecting an Aira proposal cancels its typed execution record, records the reason, and returns that reason to the next planning round.
