# Get started with Airalogy Platform

Airalogy Platform organizes research work so that a procedure, the data collected with it, and the people responsible for it stay connected. The exact sign-in and account-admission flow depends on how your organization operates its instance; the research workflow is the same in Community Edition and private deployments.

## Sign in or join an instance

- If self-registration is enabled, create an account with the fields shown on the sign-up page and then sign in.
- If the instance is invite-only, use the invitation link supplied by a Lab administrator. Existing users can accept the invitation after signing in; new users create their account through the invitation flow.
- If registration is disabled, ask the instance operator or a Lab administrator how accounts are provisioned.

Do not reuse passwords from other services. If your instance provides a password-reset link, treat it as a short-lived secret and do not forward it.

## Understand the workspace

Platform uses four connected resource types:

| Resource | Purpose                                                                     |
| -------- | --------------------------------------------------------------------------- |
| Lab      | Owns the research workspace, membership, and top-level governance.          |
| Project  | Groups work around a study, team, or objective.                             |
| Protocol | Defines what should be done and which structured fields should be recorded. |
| Record   | Captures one completed or in-progress use of a Protocol.                    |

A deployment may present one fixed Lab or allow users to join several Labs. Projects and Protocols can have additional access rules, so seeing a Lab does not automatically mean that every resource inside it is visible.

## A practical first workflow

1. Open the relevant Lab and Project.
2. Choose an existing Protocol or create one if your role permits it.
3. Review the Protocol description, fields, steps, checks, and current version before recording.
4. Create a Record, enter the requested values, attach files where required, and save or submit it.
5. Open the Record again to confirm that the stored values, files, and context are correct.
6. Share the Project or Protocol with collaborators through the membership and access controls provided by your Lab.

## Where to go next

- [Protocols](./protocols) explains creation, versions, editing, and reuse.
- [Records](./records) covers entry, validation, files, history, and safe handling.
- [Collaboration](./collaboration) explains workspace roles and sharing.
- [Search](./search) describes finding resources without assuming access you do not have.
- [Import and export](./import-export) covers CSV import and governed Record exports.

If an interface option described here is absent, it is usually disabled by the deployment profile or unavailable to your current role. Ask the relevant Lab or instance administrator rather than creating a parallel copy of the data elsewhere.
