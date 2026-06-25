# Security Policy

[中文版](SECURITY.zh-CN.md)

## Supported Versions

Community Edition is currently in early public-preparation status. Security fixes should target the latest `main` branch unless a release branch is explicitly maintained.

## Reporting a Vulnerability

Please report suspected vulnerabilities privately to the maintainers instead of opening a public issue with exploit details.

Do not include real credentials, private keys, patient data, unpublished research data, or institution-private datasets in public issues or pull requests.

## Data Handling

Airalogy Platform can manage sensitive research records and large scientific files. Self-hosted operators are responsible for configuring:

- HTTPS termination
- database backups
- object-storage access policies
- secret management
- authentication providers
- audit retention
- local regulatory requirements
