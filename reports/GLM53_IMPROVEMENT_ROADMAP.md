# Improvement roadmap

## P0 — before staging

1. For single-tenant staging, confirm one organization per deployment and retain coverage
   for cross-user access, role escalation and concurrent writes. For SaaS, confirm the
   product requirement before designing tenant membership. Verify both tenant data scopes
   across Web, API, tools and storage.
2. Assign the validated blind packet to two independent human reviewers. Publish agreement,
   claim support, citations and refusal results, then review fresh answers from the target
   staging configuration. [Handoff](GLM53_PRODUCTION_READINESS.md#independent-reviews)
3. Meet the ≤45 s generation SLO on approved staging hardware or provider. Measure total
   latency including abstentions, TTFT and accepted output at concurrency 4 with larger
   cold and warm samples.
4. Keep FAISS as the default and Qdrant Phase A opt-in. Gated native already passed 8/8
   negatives on holdout. Human review and promotion sign-off are pending for evaluator-only
   native. [Retrieval evidence](GLM53_PRODUCTION_READINESS.md#retrieval-evidence)

## P1 — staging hardening

5. Configure a real, budget-approved provider through secret management; measure TTFT,
   p50/p95/p99, tokens, cache hits, Retry-After and actual cost. Never place keys in reports.
6. Exercise two replicas across the target network, worker leases/retries/DLQ, restart,
   Redis outage, Qdrant outage and SSE cancellation under controlled soak/load.
7. Add runtime monitoring, alert thresholds, container image scanning and rollback drill.

## P2 — maintainability

8. Raise Web route/database coverage and investigate the connection-reset traceback.
9. Obtain a vendor/CVE review for CPU torch, which pip-audit cannot resolve from PyPI.
10. Keep architecture, ADR, PROJECT_MEMORY and release evidence synchronized after each gate.
