# GLM-5.3-Flash production readiness

Follow-up on 2026-11-19 against working tree based on
`ce53b1467c4ed14aa2a1ebf055a34869c2749dea`. At intake Git showed 41 modified
tracked files, one tracked deletion, 59 untracked entries in normal status mode,
and an empty index diff. The baseline ran against that working tree.

**LOCAL READY** for the tested local scope. **STAGING HOLD** for single-tenant
education and multi-tenant SaaS. **PRODUCTION NO-GO** for both.

**VERIFIED** means checked during this follow-up. **REUSED** means earlier
execution evidence. **BLOCKED** means a prerequisite prevents verification.
**FAIL** means an observed result misses its gate.

## Gate matrix

| Gate | Status | Evidence / blocker |
|---|---|---|
| Full regression | **VERIFIED · PASS** | 567 Python and 177 Web. [Commands and coverage](GLM53_TEST_RESULTS.md) |
| Retrieval correctness | **REUSED · scoped PASS** | FAISS/Phase A chunk ordering matched 45/45. Phase A and gated native each passed 8/8 negatives on the 20-case holdout. Evidence reconciliation was **VERIFIED** this turn. |
| Native hybrid promotion | **BLOCKED** | Gated native remains evaluator-only pending independent human-reviewed native cases and promotion sign-off. FAISS serves by default and Phase A remains opt-in. |
| Cross-user/role isolation | **VERIFIED** regression, **REUSED** E2E | Scoped DB, ownership, signed principal, role and concurrent-write evidence. [Security review](GLM53_SECURITY_REVIEW.md) |
| Cross-tenant isolation | **BLOCKED (P0 for SaaS)** | Multiple tenant scopes and a verified membership boundary are absent. Out of scope for a deployment with one organization and one data boundary. |
| Human faithfulness | **BLOCKED (P0)** | 20 historical answers and a blank scoring sheet verified. 0 independent reviewers and human scores `null`. |
| Generation SLO ≤45 s | **REUSED · FAIL (P0)** | Authenticated Web SSE with Qwen2.5:3b Ollama CPU on four cores, concurrency 4, four attempts, 3/4 accepted. Total p95 90.96 s including abstention. [Cleanup benchmark](cleanup/FINAL_VALIDATION.md#generation) |
| Real staging cloud provider | **BLOCKED for cloud path** | A selected provider, scoped authorization and budget are needed to measure charges and provider cache use. [Staging policy](../docs/decisions/ADR-015-staging-boundaries.md) |
| Multi-replica, recovery and rollback | **REUSED · scoped PASS** | Same-host Redis/Qdrant/PostgreSQL drills and rollback passed within fixtures. Target-topology rehearsals and multi-host failover remain unverified. [Cleanup validation](cleanup/FINAL_VALIDATION.md) |
| Security/dependency scanners | **REUSED · scoped PASS** | Previous Bandit High and npm audits returned zero findings. The installed CPU torch build was outside that pip-audit feed. [Test scope](GLM53_TEST_RESULTS.md) |

## Retrieval evidence

| Recorded run | Variant | Empty negatives | Recall@5 / MRR@5 / nDCG@5 |
|---|---|---:|---|
| [Agent platform, 45 engineer-authored cases](final-e2e-evidence/agent-platform-2026-11-18/qdrant-parity.json) | Native, independent dense and sparse branches | 4/8 | 97.30% / 85.90% / 88.33% in the linked JSON |
| [Hardening, same query files and artifact](final-e2e-evidence/agent-hardening-2026-11-18/native-diagnostics.json) | Native, independent branches | 4/8 | 97.30% / 85.90% / 88.33% |
| [Hardening, same 45 cases](AGENT_HARDENING_2026-11-18.md) | Native, shared dense floor | 8/8 | 82.43% / 79.73% / 79.53% |
| [Staging holdout, 20 frozen cases](final-e2e-evidence/staging-sprint-2026-11-18/holdout.json) | Phase A and gated native, each | 8/8 | 83.33% / 83.33% / 83.33% |
| [Cleanup replay of that holdout](cleanup/holdout-after.json) | Phase A and gated native, each | 8/8 | 83.33% / 83.33% / 83.33% |

The ungated sparse branch could admit candidates below the dense floor. The
gated evaluator applies exact dense eligibility at 0.84 to both branches before
fusion. The 20-case holdout has 12 positive and eight negative/OOD cases, split
evenly across Vietnamese and English. It had zero exact normalized query overlaps
with the tuning files. Its judgments were AI-drafted and human review is
`null`. The same fixture and artifact hashes match across staging and cleanup.
The archived [agent evaluation](AGENT_EVALUATION.md) lists 88.54% ungated nDCG@5.
The linked raw JSON currently contains 88.33%, and the archive does not establish
which underlying run produced 88.54%. The table uses the linked raw data.
[Gate implementation](../eval/qdrant_native.py) · [Holdout runner](../eval/eval_staging_holdout.py)

## Staging by deployment scope

| Scope | Verdict | Conditions |
|---|---|---|
| Single-tenant education platform | **HOLD** | Confirm one organization per deployment, keep user ownership and role regression coverage, and rehearse rollback with the target stack. The failed generation SLO and missing independent faithfulness evidence apply. Cloud evidence is required if the rollout uses cloud generation. |
| Multi-tenant SaaS | **HOLD** | Same gates plus a confirmed product need, explicit tenant membership and isolation policy, and end-to-end negative tests across Web, API, tools and storage with two distinct tenant data scopes. |

## Independent reviews

GLM-5.3-Flash code review is **BLOCKED**. `APIVN_API_KEY` was absent from the
process environment. Model access, response model ID, latency, usage, provider
cost and rubric score are `null`. The prior internal score remains 75/100.
There is no score delta to compute. [Rubric and follow-up procedure](GLM53_REPO_AUDIT.md)

Human review is ready to assign. The [packet](final-e2e-evidence/staging-sprint-2026-11-18/annotation-packet.jsonl)
and [blank sheet](final-e2e-evidence/staging-sprint-2026-11-18/review-sheet.csv) have
the same 20 unique case IDs. All have a stored query and answer, 18 include at
least one excerpt, and two contain no retrieved sources. The [manifest](final-e2e-evidence/staging-sprint-2026-11-18/annotation-manifest.json)
links the historical 2026-10-31 capture by SHA256. Give two independent reviewers
separate copies of the sheet keyed by anonymous reviewer ID and hide expected
labels. Record claim counts and supporting excerpts in notes, and adjudicate
disagreements of two or more points with a third reviewer. Score abstention
using refusal appropriateness where applicable. Flag missing evidence explicitly
and report coverage and denominators with the scores. Review a fresh sample from
the chosen staging provider before closing the staging gate.
[Scoring protocol](release-readiness-evidence/HUMAN_REVIEW_PROTOCOL.md)
