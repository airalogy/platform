# Protocols

A Protocol is a reusable, versioned description of a research procedure and its structured data fields. It can combine readable instructions with steps, checks, variables, files, and other typed inputs.

## Find or create a Protocol

Open a Project to see Protocols owned by that Project. Depending on your role, you can create a Protocol directly, start from an available example, import a supported package, or use the AI-assisted drafting flow. Review generated or imported content before it becomes part of a real research process.

Use a stable, descriptive Protocol ID where the interface requests one. Display names and descriptions can explain the scientific purpose; identifiers are used in routes and integrations and may not be safely changeable later.

## Practice without AI or equipment

In a Project, choose **New protocol → From template → First Record practice**. Give the draft a recognizable name, open it in the editor, and choose **Save**. Check the destination Lab, Project and version before confirming. You need permission to create Protocols; a recorder can ask the Protocol owner to prepare this once for the team.

The bilingual practice template contains two required fields, example values and instructions for saving, submitting and revising a Record. It creates an ordinary editable, versioned Protocol, not a separate demo mode. Its data is explicitly synthetic: keep it in a practice Project and do not treat it as research evidence. No AI service is needed.

## Edit with intent

Before changing a Protocol that already has Records:

1. Confirm which version is active and whether downstream work depends on its fields.
2. Prefer additive, compatible changes when existing Records must remain comparable.
3. Treat renamed, removed, or retyped fields as schema changes that need explicit review.
4. Preview the rendered Protocol and resolve validation errors before publishing or recording.

AI assistance can draft or explain changes, but the responsible researcher remains accountable for scientific correctness, safety, and the final field definitions.

## Calculated fields: client or server

Small deterministic calculations can stay in one `protocol.aimd` file:

````aimd
Length: {{var|length: float, ge=0}}
Width: {{var|width: float, ge=0}}
Area: {{var|area: float, ge=0}}
```assigner runtime=client
assigner(
  {mode: "auto", dependent_fields: ["length", "width"], assigned_fields: ["area"]},
  function calculate_area({length, width}) { return {area: length * width}; }
);
```
````

Client modes are `auto`, `auto_first` and `manual`. Inputs and outputs must be declared fields; each output has one writer and dependencies cannot form cycles. Calculations run only in an editable Record, using the restricted AIMD JavaScript runtime. Invalid inputs or outputs show an error rather than saving a partial result. Read-only reports retain their saved values.

Use server-side Python for external services, files, secrets, scientific libraries, heavy computation or authoritative verification. A browser result is not a security or scientific-integrity guarantee. Do not store JavaScript in `assigner.py`; Python may remain in a plain `assigner` fence or a standalone `assigner.py`, without duplicate implementations.

CSV/API imports do not run browser calculations. Supply the derived fields required by the downloaded template; missing or invalid required values are rejected. Review formulas and source observations before using either runtime for real research.

## Reuse and workflows

Protocols can be reused across experiments when the procedure and data contract are genuinely the same. Use a separate Protocol or an explicit new version when the scientific meaning changes.

Where Protocol Workflow is available, multiple Protocols can be connected into a directed research process. Check the starting Protocol, transitions, and data mapping before execution. A workflow should make hand-offs visible; it should not hide undocumented assumptions between steps.

## Share and cite

Access is determined by Lab, Project, and Protocol rules. Share through Platform membership and grants rather than copying unpublished content to an uncontrolled location. Stable Platform routes can be used to reference a Protocol, but recipients still need the required access.

See [Collaboration](./collaboration) for role guidance and [Records](./records) for using a Protocol to capture data.
