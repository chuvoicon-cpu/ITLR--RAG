# Security audit · 2026-11-19

| Boundary | Evidence and residual risk |
|---|---|
| Express → PostgreSQL | Authenticated disposable users exercised progress isolation, confirmation, concurrent idempotent plan saves and handoff, and role-gated support resolution. No membership schema exists for independent tenants. |
| Express → FastAPI | Strict signed principal mode rejected an invalid principal. The Web SSE template stream completed normally. Async transport cancellation and quota release have regression coverage. |
| Agent → retrieval and model | Typed tool inputs and bounded retrieval, approval metadata, and citation binding were reviewed. Tool output is data. There is no public shell, filesystem, or admin SQL tool. Independent faithfulness and red-team evaluation stay open. |
| FastAPI → storage | Fixture Qdrant reader/writer keys, approved/versioned filters, manifest checks, snapshot restore, and alias rollback. Redis tests covered shared limits, expiry and cache isolation. Artifact pickle remains trusted-build only. |
| Gateway → provider | The routing regression verifies secret-file configuration suppresses Ollama prewarm for a cloud-selected route. Staging requires explicit cloud authorization and positive shared quotas. Paid provider and billing remain unverified. |
| Observability | Compose config renders and monitoring YAML parses. The opt-in profile uses privileged container/host telemetry; keep it on a trusted host. Runtime monitoring certification and image scans remain outstanding. |

See [dependency audit](DEPENDENCY_AUDIT.md) and [validation](FINAL_VALIDATION.md) for scanner
scope and residual risks. Agent and retrieval controls are described in the
[staging ADR](../../docs/decisions/ADR-015-staging-boundaries.md).
