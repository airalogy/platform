# Lab Access Control

This document describes teams and research-resource permissions when `LAB_STRUCTURE_MODE=structured`. The single-Lab profile enables this mode by default. The Community profile defaults to `flat` but may opt in explicitly.

## Design Goals

The model separates organizational membership from access to research resources:

- **Organization structure**: a Lab contains a team tree with at most three levels. A member may belong to multiple teams, which also represents matrix organizations.
- **Resource structure**: a Lab contains a Project tree with at most three levels. Projects contain Protocols, and Protocols produce Records.
- **Connection**: scoped grants connect a User or Team to a Lab, Project, or Protocol.

A Team does not imply research access. A team manager can maintain that Team and its descendants but needs a separate scoped grant to access research resources.

## Permission Subjects

### User

A grant may target one Lab member directly. When the member is removed from the Lab, active direct grants are revoked automatically and those revocations are recorded in the grant audit log.

### Team

A grant may target a Team. A user receives grants from:

- each Team they directly belong to;
- every ancestor of those Teams;
- every additional Team they belong to and its ancestors.

A grant on a parent Team can therefore cover an organizational branch. A parent-team manager can create and manage descendant Teams. Root-Team creation and moving an existing Team are reserved for the Lab owner or manager.

## Resource Scopes And Inheritance

Grants have three scopes:

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

The lookup stops at a resource inheritance break. An ancestor grant without downward inheritance does not propagate to the current resource.

## Roles And Capabilities

`lab_owner` and `lab_admin` are Lab membership identities managed on the Members screen. They cannot be issued as ordinary scoped grants. Other roles can be granted to a User or Team in the Access workspace.

| Role | Purpose | Main capabilities | Scoped grant |
| --- | --- | --- | --- |
| Lab owner | Lab owner | All capabilities, including Lab ownership | No |
| Lab administrator | Lab manager | All capabilities except Lab ownership | No |
| Project manager | Resource-scope manager | Manage grants and Projects in scope; edit Protocols; create, read, and delete Records | Yes |
| Protocol editor | Protocol editor | Create, read, update, and delete Protocols; run Assigners; create, read, and delete Records | Yes |
| Contributor | Research collaborator | Create and read Protocols; run Assigners; create and read Records | Yes |
| Recorder | Experiment recorder | Currently has the same capability set as Contributor, while preserving distinct intent and legacy-role mapping | Yes |
| Viewer | Read-only user | Read Protocols and Records | Yes |

Authorization checks use capabilities, not display-role names. Query the exact current capability sets with `GET /api/access/roles`.

## Effective Access

A user's final capabilities are the **union** of all effective sources:

1. Lab owner or manager membership;
2. direct grants to the User;
3. grants from the User's Teams and their ancestors;
4. grants on the current resource and unblocked ancestor resources;
5. compatible legacy Project, Lab Group, Protocol, and Project Group roles.

Only grants that are neither revoked nor expired participate. There is no explicit `DENY`. If one source gives Viewer and another gives Contributor, the final result includes the additional Contributor capabilities.

The **Effective access** tab can inspect a User at Lab, Project, or Protocol scope and shows:

- effective roles;
- the merged capability set;
- each source's subject, scope, grant ID, and inheritance status.

Lab owners and managers can inspect any member. A regular member can inspect only their own effective access.

## Delegation

At the target scope, a delegator must:

1. hold `access.manage`;
2. hold every capability contained in the requested role.

This is the delegation ceiling. A Project manager can assign Contributor or Viewer inside a Project they manage but cannot assign Lab administrator. Team-manager status does not contain `access.manage` and cannot grant research-resource roles on its own.

## Administrative Workflows

### Build The Organization

1. Invite members on **Members**. Assign Lab manager only when full-Lab administration is required.
2. Create root and descendant Teams on **Teams**.
3. Add members to Teams as `manager` or `member`.
4. Add a cross-functional member to multiple Teams instead of duplicating Teams.

### Create A Grant

1. Open **Access > Grants** and select **Add grant**.
2. Select a User or Team.
3. Select Lab, Project, or Protocol scope.
4. Select a role and, where relevant, downward inheritance, expiry, and an operational reason.
5. Use **Effective access** to verify the resulting capabilities and sources.

Prefer Team grants for stable organizational access. Use direct User grants for exceptions and temporary collaboration. Set expiry for external collaborators.

### Revoke And Audit

Revoking a grant ends it without deleting its history. Lab owners and managers can use **Audit** to review grant creation, updates, revocation, and direct-grant revocation caused by Lab-member removal. It is a grant-change audit, not a comprehensive security audit covering every login, data read, or Record modification.

## Common Scenarios

### Read-Only Organizational Branch

Grant Viewer to a parent Team at Lab scope with downward inheritance. Members of descendant Teams can read Projects and Protocols that have not disabled resource inheritance.

### Temporary Project Participation

Grant Contributor directly to a User on one Project, set an expiry, and enable downward inheritance only if child Projects should also be accessible.

### Sensitive Protocol Isolation

Disable resource inheritance on the sensitive Protocol, then add direct Protocol grants only for the required Users or Teams. Because there is no explicit `DENY`, disabling inheritance is necessary to stop ancestor grants from entering the Protocol.

### Matrix Collaboration

Add a member to both a discipline Team and a project Team. The grants from both Team branches are combined automatically; a separate matrix-role system is unnecessary.

## API Index

Default same-origin deployments expose these routes under `/api`:

| Purpose | Endpoint |
| --- | --- |
| Role catalog | `GET /api/access/roles` |
| Team tree | `GET /api/access/labs/{lab_id}/teams` |
| Create, update, delete Team | `POST /api/access/teams` / `PUT` / `DELETE /api/access/teams/{team_id}` |
| Team members | `POST /api/access/teams/{team_id}/members` / `DELETE /api/access/teams/{team_id}/members/{user_id}` |
| Grant list | `GET /api/access/labs/{lab_id}/grants` |
| Create, update, revoke grant | `POST /api/access/grants` / `PUT /api/access/grants/{grant_id}` / `POST /api/access/grants/{grant_id}/revoke` |
| Manageable scopes | `GET /api/access/labs/{lab_id}/manageable-scopes` |
| Effective-access explanation | `GET /api/access/labs/{lab_id}/effective` |
| Grant audit | `GET /api/access/labs/{lab_id}/audit` |
| Project / Protocol inheritance | `PUT /api/access/projects/{project_id}/inheritance` / `PUT /api/access/protocols/{protocol_id}/inheritance` |

The API enforces Lab membership, delegation ceilings, and subject/resource ownership. Hidden frontend controls are not the security boundary.

## Troubleshooting

| Symptom | Checks |
| --- | --- |
| Teams or Access is missing | Confirm `LAB_STRUCTURE_MODE=structured` and restart the API. Rebuild the single-Lab Web image after relevant Web configuration changes. |
| Member cannot see a Project | Confirm Lab membership, grant subject, expiry/revocation, `inherit_to_children`, and the Project inheritance switch. |
| Member can read but cannot edit | Inspect Effective access for the required `protocol.*` or `record.*` capability. |
| A role cannot be assigned | Confirm the delegator has `access.manage` at the target scope and does not exceed the delegation ceiling. Manage owner/admin on Members. |
| Team manager cannot access resources | This is expected. Add a separate User or Team resource grant. |
| Revoked history is not listed | Enable **Include revoked** on Grants or inspect Audit. |

## Explicit Boundaries

The model intentionally remains explainable and operable. It does not provide:

- unlimited organizational depth;
- explicit deny rules or allow/deny precedence;
- arbitrary ABAC or policy expressions;
- field-level, individual-Record, or data-masking policy;
- comprehensive security-event auditing, SSO / LDAP, or automated identity lifecycle management.

If these become deployment requirements, treat them as a separate enterprise identity and compliance project rather than adding more Team depth or ad hoc roles.
