# GLM-5.3-Flash repository audit

## Scope and method

The audit inspected the Express/TypeScript web application, FastAPI service, shared
retrieval, agent tools, LLM client, storage adapters, compose/deployment files, tests,
and the existing cleanup and hardening evidence. No production source or evaluation
data was changed. Secrets and customer data were not sent externally.

The follow-up found `APIVN_API_KEY` absent. GLM-5.3-Flash access is **BLOCKED**.
The endpoint was untested and the independent score is `null`. The table retains
the original internal score and weights for a future comparison.

## Evidence-backed score

| Category | Weight | Score | Basis |
|---|---:|---:|---|
| Architecture & design | 15 | 12 | Shared retrieval and provider boundary; see `docs/ARCHITECTURE.md`, ADR-014/015 |
| Code quality | 15 | 11 | Focused modules and regression coverage; remaining duplication and low web route coverage |
| Functional correctness | 15 | 13 | 567 Python + 177 Web tests; frozen retrieval and E2E evidence |
| Security | 15 | 11 | Historical score. Auth/CSRF/tool controls tested and cross-tenant SaaS isolation remains unverified. |
| Testing & reliability | 15 | 12 | Full suites, restore/failure drills; human faithfulness not verified |
| Performance & scalability | 10 | 5 | Ollama CPU concurrency-4 total p95 90.96 s; sustained generation deferred |
| Database & data integrity | 5 | 4 | PostgreSQL/Qdrant restore and manifest checks passed; multi-tenant model incomplete |
| DevOps & deployment | 5 | 3 | Compose and CI checks present; image scanning/runtime monitoring outstanding |
| Documentation | 5 | 4 | English/Vietnamese docs, ADRs and runbooks; provider billing evidence absent |
| **Total** | **100** | **75** | High confidence only for tested local scope |

## Top findings

1. **P0:** independent human faithfulness scores are missing; existing labels are engineer-authored/rule-based.
2. **P0:** generation SLO fails on CPU Ollama at concurrency 4 (p95 90.96 s versus 45 s).
3. **P0 for multi-tenant SaaS.** There is no verified cross-tenant membership boundary. An education deployment with one organization uses the existing single-scope design.
4. **P1:** paid/cloud provider latency, token usage, cache-hit and cost remain unverified by policy.
5. **P1:** multi-host failover and sustained generation load are deferred; only same-host replicas were exercised.
6. **P1:** runtime monitoring and container image scanning are outstanding.
7. **P1.** The ungated experiment returned 4/8 empty negatives. Gated native returned 8/8 in hardening and again on the separate frozen holdout. It remains evaluator-only pending human review and promotion sign-off. [Reconciliation](GLM53_PRODUCTION_READINESS.md#retrieval-evidence)
8. **P2:** Web route/database coverage is materially below the Python suite (55.29% lines).
9. **P2:** torch is not auditable by pip-audit's PyPI feed and needs a pinned vendor/CVE review.
10. **P2.** The historical fixture connection reset did not reproduce in the fresh Python suite. [Test results](GLM53_TEST_RESULTS.md)

## Independent GLM review procedure

Once a key is available in the process environment and this provider review has
explicit spend authorization and a budget, query `https://apivn.vn/v1/models`
for `glm-5.3-flash`, then run a minimal Chat Completions probe. Record HTTP
outcome, returned model, wall latency, token usage and billed cost when the
provider reports it. Keep unavailable fields `null`. Stop on missing model,
authentication, quota or budget failure.

Use at most three review calls within the approved budget. Candidate inputs are
short excerpts from [evaluator gating](../eval/qdrant_native.py),
[chat ownership](../web/src/services/chat-history.ts) and
[artifact checks](../itlr/retrieval/qdrant_artifacts.py), plus an architecture
summary and aggregate test evidence. Review the exact outbound payload for
secrets, PII and customer content. Ask for the nine weighted scores above,
evidence for each deduction, gaps marked NOT VERIFIED, and P0/P1/P2 findings.
Withhold the internal score until after the model returns its own. Compare the
returned category scores and total to the original 75/100 and record differences
verbatim as model opinions.
