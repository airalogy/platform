# Lab Access Control

This document describes organizational units and research-resource permissions when `LAB_STRUCTURE_MODE=structured`. The single-Lab profile enables this mode by default. The Community profile defaults to `flat` but may opt in explicitly.

## Core Model

The model separates organizational membership from access to research resources:

- **Organization structure**: a Lab contains an organizational-unit tree with at most three levels. A unit can be a department, research group, core facility, project team, committee, or another organization type.
- **Resource structure**: a Lab contains a Project tree with at most three levels. Projects contain Protocols, and Protocols produce Records.
- **Connection**: scoped grants connect a User or organizational unit to a Lab, Project, or Protocol.

Organizational membership does not imply research access. An organizational-unit manager can maintain that unit and its descendants but needs a separate scoped grant to access research resources. A Project remains a resource container and should not be used to represent a department or research group.

## Organizational Units

### Types

| Type | Typical use |
| --- | --- |
| `department` | Stable administrative branches such as a research center, discipline division, or R&D department |
| `research_group` | PI labs, experimental groups, or specialist research groups |
| `core_facility` | Shared mass-spectrometry, imaging, sequencing, or screening facilities |
| `project_team` | Cross-functional programs, joint task forces, or time-bounded project teams |
| `committee` | Safety, data-governance, instrumentation, or academic committees |
| `other` | Units outside the standard types and historical Groups upgraded from earlier releases |

The type expresses business meaning and controls display labels. It does not currently change authorization semantics. One generic entity can represent academic, administrative, shared-facility, and temporary structures without parallel Department and Team membership systems.

### Why Three Levels

The Lab itself does not count toward the three levels. A full structure may use a department at level one, a research group or core facility at level two, and a project team at level three.

Three levels are an enforced product boundary, not a database limitation. The API validates the limit when a unit is created or moved. This keeps delegation, inheritance explanations, and navigation manageable. Most individual laboratories and medium-sized research centers can express their stable hierarchy within three levels; matrix relationships are represented by adding one person to multiple units.

If a real administrative hierarchy consistently needs four or more levels, first determine whether the upper branch should be a separate Lab or a future Organization/Tenant. The limit should be expanded only with explicit deployment requirements, delegation rules, and a migration plan, rather than making one Lab arbitrarily deep.

### Representative Structures

**Single-PI laboratory**

```text
Lab
`- Xu Lab (research_group)
   |- Molecular Biology Group (research_group)
   `- Proteomics Project Team (project_team)
```

A smaller Lab may create only one root research group. Empty hierarchy levels are not required.

**Drug-discovery center**

```text
Lab
|- Small-Molecule R&D (department)
|  |- Medicinal Chemistry (research_group)
|  `- Lead A Program (project_team)
|- Biology R&D (department)
|  `- Cell Function Group (research_group)
`- High-Throughput Screening (core_facility)
```

Stable departmental membership and time-bounded project collaboration can coexist. A scientist may belong to both Medicinal Chemistry and the Lead A Program.

**Multi-PI center with shared facilities**

```text
Lab
|- Neuroscience Division (department)
|  |- Zhang Lab (research_group)
|  `- Li Lab (research_group)
|- Imaging Facility (core_facility)
`- Data Governance Committee (committee)
```

One member may belong to a PI lab, the imaging facility, and the data-governance committee. This expresses a matrix organization without changing the hierarchy into a graph or adding a separate dotted-line reporting model.

## Permission Subjects

### User

A grant may target one Lab member directly. When the member is removed from the Lab, active direct grants are revoked automatically and those revocations are recorded in the grant audit log.

### Organizational Unit

A grant may target an organizational unit. A user receives grants from:

- each unit they directly belong to;
- every ancestor of those units;
- every additional unit they belong to and its ancestors.

A grant on a parent unit can therefore cover an organizational branch. A parent-unit manager can create and manage descendant units. Root-unit creation and moving an existing unit are reserved for the Lab owner or manager. A member may belong to multiple units, and all effective grants are combined.

## Resource Scopes And Inheritance

| Scope    | Exact target      | With downward inheritance enabled                     |
| -------- | ----------------- | ----------------------------------------------------- |
| Lab      | Current Lab       | Propagates to Projects, child Projects, and Protocols |
| Project  | Selected Project  | Propagates to child Projects and Protocols            |
| Protocol | Selected Protocol | Applies only to that Protocol                         |

Each grant's `inherit_to_children` flag controls whether it propagates downward. Projects and Protocols also have an `inherit_permissions` switch:

- A Project with inheritance disabled no longer receives grants from its parent Project or Lab. Direct grants on that Project still apply.
- A Protocol with inheritance disabled no longer receives grants from its Project or Lab. Direct grants on that Protocol still apply.
- Lab owner and manager membership is Lab-wide administration and cannot be locked out by a resource inheritance break.

For a Protocol, the default lookup chain for a regular member is:

```text
Protocol -> Project -> parent Project -> Lab
```

## Roles And Capabilities

`lab_owner` and `lab_admin` are Lab membership identities managed on the Members screen. They cannot be issued as ordinary scoped grants. Other roles can be granted to a User or organizational unit in the Access workspace.

| Role | Purpose | Main capabilities | Scoped grant |
| --- | --- | --- | --- |
| Lab owner | Lab owner | All capabilities, including Lab ownership | No |
| Lab administrator | Lab manager | All capabilities except Lab ownership | No |
| Project manager | Resource-scope manager | Manage grants and Projects in scope; edit Protocols; create, read, and delete Records | Yes |
| Protocol editor | Protocol editor | Create, read, update, and delete Protocols; run Assigners; create, read, and delete Records | Yes |
| Contributor | Research collaborator | Create and read Protocols; run Assigners; create and read Records | Yes |
| Recorder | Experiment recorder | Currently has the same capabilities as Contributor while preserving distinct intent and legacy-role mapping | Yes |
| Viewer | Read-only user | Read Protocols and Records | Yes |

Authorization checks use capabilities, not display-role names. Query the current capability sets with `GET /api/access/roles`.

## Effective Access And Delegation

A user's final capabilities are the union of Lab owner or manager membership, direct User grants, grants from organizational units and their ancestors, unblocked resource grants, and compatible legacy roles. Only grants that are neither revoked nor expired participate. There is no explicit `DENY`.

The **Effective access** tab can inspect a User at Lab, Project, or Protocol scope and shows effective roles, the merged capability set, and each grant source. Lab owners and managers can inspect any member. A regular member can inspect only their own access.

At the target scope, a delegator must hold `access.manage` and every capability contained in the requested role. A Project manager can assign Contributor or Viewer inside a Project they manage but cannot assign Lab administrator. Organizational-unit manager status does not contain `access.manage` and cannot grant research-resource roles on its own.

## Administrative Workflows

### Build The Organization

1. Invite members on **Members**. Assign Lab manager only when full-Lab administration is required.
2. Create units with their real organizational meaning on **Organization**. All three levels do not need to be filled.
3. Add members to units as `manager` or `member`.
4. Add cross-functional members to multiple units instead of duplicating people or hierarchy nodes.

### Create A Grant

1. Open **Access > Grants** and select **Add grant**.
2. Select a User or organizational unit.
3. Select Lab, Project, or Protocol scope.
4. Select a role and, where relevant, downward inheritance, expiry, and an operational reason.
5. Use **Effective access** to verify the resulting capabilities and sources.

Prefer organizational-unit grants for stable access. Use direct User grants for exceptions and temporary collaboration. Set expiry for external collaborators.

### Revoke And Audit

Revoking a grant ends it without deleting its history. Lab owners and managers can use **Audit** to review grant creation, updates, revocation, and direct-grant revocation caused by Lab-member removal. It is a grant-change audit, not a comprehensive security audit covering every login, data read, or Record modification.

## Common Access Scenarios

- **Read-only organizational branch**: grant Viewer to a parent unit at Lab scope with downward inheritance.
- **Temporary Project participation**: grant Contributor directly to a User on one Project and set an expiry.
- **Sensitive Protocol isolation**: disable resource inheritance on the Protocol, then add direct Protocol grants only for the required Users or organizational units.
- **Matrix collaboration**: add a member to both a discipline research group and a cross-functional project team. Grants from both branches are combined.

## API Index

Default same-origin deployments expose these routes under `/api`:

| Purpose | Endpoint |
| --- | --- |
| Role catalog | `GET /api/access/roles` |
| Organizational-unit tree | `GET /api/access/labs/{lab_id}/organizational-units` |
| Create organizational unit | `POST /api/access/organizational-units` |
| Update or delete organizational unit | `PUT` / `DELETE /api/access/organizational-units/{unit_id}` |
| Organizational-unit members | `POST /api/access/organizational-units/{unit_id}/members` / `DELETE /api/access/organizational-units/{unit_id}/members/{user_id}` |
| Grant list | `GET /api/access/labs/{lab_id}/grants` |
| Create, update, revoke grant | `POST /api/access/grants` / `PUT /api/access/grants/{grant_id}` / `POST /api/access/grants/{grant_id}/revoke` |
| Manageable scopes | `GET /api/access/labs/{lab_id}/manageable-scopes` |
| Effective-access explanation | `GET /api/access/labs/{lab_id}/effective` |
| Grant audit | `GET /api/access/labs/{lab_id}/audit` |
| Project / Protocol inheritance | `PUT /api/access/projects/{project_id}/inheritance` / `PUT /api/access/protocols/{protocol_id}/inheritance` |

New grants use `subject_type=org_unit` and `org_unit_id`. To support rolling upgrades, the API still accepts historical `subject_type=team` / `group_id` input and `/access/teams` routes. Those compatibility routes are hidden from OpenAPI and must not be used by new integrations.

The API enforces Lab membership, delegation ceilings, and subject/resource ownership. Hidden frontend controls are not the security boundary.

## Troubleshooting

| Symptom | Checks |
| --- | --- |
| Organization or Access is missing | Confirm `LAB_STRUCTURE_MODE=structured` and restart the API. Rebuild the single-Lab Web image after relevant Web configuration changes. |
| Member cannot see a Project | Confirm Lab membership, grant subject, expiry/revocation, `inherit_to_children`, and the Project inheritance switch. |
| Member can read but cannot edit | Inspect Effective access for the required `protocol.*` or `record.*` capability. |
| A role cannot be assigned | Confirm the delegator has `access.manage` at the target scope and does not exceed the delegation ceiling. Manage owner/admin on Members. |
| Organizational-unit manager cannot access resources | This is expected. Add a separate User or organizational-unit resource grant. |
| Revoked history is not listed | Enable **Include revoked** on Grants or inspect Audit. |

## Explicit Boundaries

The model intentionally remains explainable and operable. It does not provide:

- unlimited organizational depth;
- explicit deny rules or allow/deny precedence;
- arbitrary ABAC or policy expressions;
- field-level, individual-Record, or data-masking policy;
- comprehensive security-event auditing, SSO / LDAP, or automated identity lifecycle management.

If these become deployment requirements, treat them as a separate enterprise identity and compliance project rather than adding more organizational depth or ad hoc roles.
