# Lab administration

This guide is for Lab Owners and Managers. It explains operational choices; the backend access model remains the security boundary. For the complete role, grant, inheritance, and audit model, use the [access control reference](../access-control).

## Members and roles

Review identity and scope before adding a member. Assign the least powerful role that supports the intended work:

- **Owner** controls Lab ownership, destructive Lab actions, and the highest-level settings. Keep this group small.
- **Manager** performs delegated administration but should not be treated as the legal or institutional owner of the data.
- **Member** participates through Project roles and explicit access made available within the Lab.

When removing or downgrading a member, first reassign resources and pending responsibilities. Do not delete shared research data merely because its original recorder leaves the Lab.

## Project and organizational access

Use Project membership for a specific research boundary. In structured Labs, organizational units and scoped grants can represent real teams without granting broad Lab management privileges. Keep inheritance enabled only where child resources are intended to follow the parent’s access model.

Periodically review:

- owners and managers;
- expired or revoked grants;
- public access settings;
- Projects or Protocols with exceptional inheritance;
- members who no longer need access.

Use the Effective access view and audit history when available instead of inferring permission from a single role label.

## Data ownership

Research data belongs to the Lab or organization under its applicable agreements and policy, not to an individual browser session or export. Keep Protocols, Records, files, and revision history in the owning workspace. Define who can approve public release, export data, delete resources, and restore backups.

Exports are controlled copies. Their creation does not transfer ownership or relax confidentiality obligations. Maintain a record of material exports and their destination.

## Lab settings

Treat IDs as durable identifiers and names/descriptions as editable labels. Before changing public visibility, default roles, organization structure, or deletion settings, assess the effect on existing Projects and links.

For Single-Lab deployments, coordinate changes to the fixed Lab and default Project with the instance operator. Some settings are established through deployment configuration and require a verified configuration change or image rebuild rather than an interface-only edit.

## Administration checklist

1. Keep at least one verified Owner account and protect its recovery path.
2. Review managers and external collaborators on a defined schedule.
3. Confirm sensitive Projects do not inherit unintended public access.
4. Test governed exports and operator backups separately.
5. Record major membership, access, and deletion decisions in the appropriate audit or institutional system.
