# Self-hosting operations

This section is for instance operators. Platform currently supports a Community profile and a production-oriented Single-Lab profile. Use the deployment guide matching the installation rather than combining fragments from different profiles.

## Choose the deployment path

- [Community Edition](../community-edition) describes the public multi-Lab product and local-first defaults.
- [Single-Lab deployment](../single-lab-deployment) documents the bundled production stack, bootstrap flow, security settings, validation, and operational commands.
- [Self-hosted architecture](../architecture/self-hosted-architecture) explains the service and storage boundaries for larger installations.

Customer-specific hostnames, accounts, topology, SLA terms, support cases, and delivery records belong in the customer’s private operations system, not this public documentation.

## Deploy

1. Select a clean, committed Platform revision or an immutable release manifest.
2. Generate unique application, encryption, database, storage, internal API, and initial-admin secrets.
3. Configure the public site URL, deployment mode, documentation profile, storage, mail/identity options, and AI providers required by the installation.
4. Build or pull images identified by Platform version and immutable Git SHA.
5. Run the deployment validator and database migrations before serving traffic.
6. Verify `/api`, object-storage proxying, the Platform SPA, and `/docs/` on the deployed origin.

Never use example secrets in production. Record the version, Git SHA, image digests, database revision, deployment ID, and configuration change reference for every deployment.

## Upgrade

Read both changelogs and the release manifest before upgrading. Back up the database, object storage, configuration, and required local Protocol data. Pull or build all components from the same release identity, run preflight validation, then apply migrations once.

After the upgrade, verify sign-in, instance status, core Lab/Project/Protocol/Record paths, uploads/downloads, background jobs, documentation, and any configured AI or executor path. Keep the previous immutable images and a tested restore point until acceptance is complete. A database downgrade is not assumed to be safe unless the release explicitly documents it.

## Back up

A usable backup set includes:

- a transactionally consistent PostgreSQL backup;
- MinIO or external object-storage objects and bucket metadata;
- deployment configuration and secrets through an approved secret-management backup process;
- persistent Protocol/executor data and release/deployment metadata;
- enough documentation to restore DNS, TLS, and external integrations.

Encrypt backup media, restrict access, keep at least one copy outside the primary failure domain, and monitor scheduled job results. Application-level exports do not replace an instance backup.

## Restore

Practice restoration in an isolated environment. Restore the database and object storage from a compatible point, apply the matching configuration and image release, then run migrations only as prescribed for that release. Verify file resolution, counts, recent Records, access rules, and background processing before reopening the instance.

Define recovery point and recovery time objectives with the organization operating the service. A backup that has never completed a restore test is not sufficient evidence of recoverability.

## Routine operations

- Monitor service health, disk capacity, database growth, object-storage availability, certificate expiry, and backup completion.
- Retain API, proxy, and audit logs according to policy without logging request bodies that may contain passwords or unpublished data.
- Rotate secrets through a planned change and verify all dependent services.
- Produce a sanitized support bundle when seeking help; do not place customer identities or secrets in public issues.
- Use [release and deployment identity](../release-and-deployment-identity) to prove exactly what is running.

The documentation bundled at `/docs/` is built from the same source revision as the Platform Web artifact. It is public product information; navigation visibility inside Platform is not a confidentiality boundary.
