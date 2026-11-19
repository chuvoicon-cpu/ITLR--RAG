# Security review

## Verified controls

- Express/PostgreSQL user isolation, CSRF/JWT, idempotent writes and role-gated support
  paths are covered by tests and Compose evidence (`reports/cleanup/SECURITY_AUDIT.md`).
- FastAPI signed-principal admission rejects invalid principals; SSE cancellation releases
  permits.
- Agent tools are typed and bounded; no public shell, filesystem or admin-SQL tool exists.
- Qdrant fixture credentials, approved/versioned filters, manifest checks, alias rollback,
  Redis isolation and PostgreSQL/Qdrant restore drills passed in the isolated scope.
- Secrets are environment/file based and audit output contains no secret value.

## Open risks / P0-P1 blockers

- **P0 HOLD for multi-tenant SaaS.** The service rejects recognized tenant selectors
  and enforces tested user-scoped ownership. Independent tenant membership and isolation
  require two separate tenant data scopes and end-to-end verification. One-organization
  education staging uses the existing single-scope design with cross-user and role
  controls. [Boundary ADR](../docs/decisions/ADR-015-staging-boundaries.md)
- **P0 HOLD:** human faithfulness and hallucination evaluation is `null`; citations alone
  do not prove grounded claims.
- **P1:** cloud provider authentication, quota, billing and rate-limit behavior are not
  exercised because paid calls were not authorized.
- **P1:** privileged host/container monitoring profile and image scanning remain outside
  certification.

For SaaS, confirm the product requirement before designing tenant membership. Verify
enforcement at Express, FastAPI, tools and storage boundaries before accepting distinct
organizations in one deployment. [Scoped verdicts](GLM53_PRODUCTION_READINESS.md#staging-by-deployment-scope)
