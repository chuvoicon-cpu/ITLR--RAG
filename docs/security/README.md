# Security documentation

- [Trust boundaries, sessions, CSRF, rate limits, and artifact integrity](../SECURITY.md)
- [Agent tool authorization and storage boundaries](../architecture/SECURITY_REVIEW.md)
- [Single-tenant staging and cloud authorization decision](../decisions/ADR-015-staging-boundaries.md)
- [Current scanner results and outstanding findings](../../reports/cleanup/SECURITY_AUDIT.md)
- [Private reporting policy](../../SECURITY.md)

Restrict credentials and user data to the service that needs them. A trusted host is
required for the optional monitoring profile, which mounts host telemetry paths and
includes privileged cAdvisor. Review retention and access before using it in staging.
