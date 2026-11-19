# Security policy

The supported validation scope is the current local checkout. Review the latest release
gates before deploying an instance. [Release status](reports/cleanup/RELEASE_READINESS.md)

## Reporting vulnerabilities

Use the repository's private vulnerability reporting feature if the repository owner has
enabled it. Otherwise contact the maintainer or instance operator through an established
private channel. Include the revision, affected boundary, impact, and the conditions
required to observe the issue. Share only the minimum redacted evidence needed for triage.
Avoid publishing credentials, user data, or vulnerability details in a public issue.

## Deployment boundaries

Express owns user sessions and PostgreSQL permissions. The FastAPI principal signature
supports admission and quota. Tenant membership and multi-host isolation are open release
gates. [Threat boundaries](docs/SECURITY.md) · [Security controls and known gaps](docs/security/README.md)
