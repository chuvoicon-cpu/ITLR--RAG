# ITLR–RAG repository cleanup

2026-11-19 · Working tree based on `ce53b1467c4ed14aa2a1ebf055a34869c2749dea`.

## Changes

| Action | Path and rationale |
|---|---|
| Delete | `reports/release-retrieval.log` was a clean, tracked zero-byte file. Only historical inventories named it. The result remains in [release-retrieval.json](release-retrieval.json), and Git retains the log at `ce53b14`. |
| Move | `web/vitest.config.ts` → `web/vitest.config.mjs`. The contents and fixture environment are identical. The ESM config loads on Node 22 with Vitest's native loader. |
| Simplify | `web/src/services/dataset-extract.ts` selects its sole PDF parser directly. The worker keeps the parser path, input and output limits, timeout and memory isolation. Added coverage for the existing two-worker limit and valid GIF recognition at the upload boundary. |
| Trim dependencies | Removed the direct declarations for `joblib` and `tqdm` from both Python manifests. Runtime declarations fell from 22 to 20 and setup requirements from 26 to 24. Scikit-learn and Sentence Transformers still resolve the two transitive dependencies. The offline pip dry run proposed no package changes. |
| Consolidate guides | The English and Vietnamese READMEs went from 192 and 447 lines to 86 and 57. Docker startup belongs in [deployment](../deploy/DEPLOY.md#docker-compose-local). Monitoring and restore belong in [operations](../docs/operations/README.md). [Testing](../docs/TESTING.md) points here for current measurements. |
| Ignore generated files | Added precise rules for `.env.local`, root Graphify output and CI JUnit XML. Tracked example environment files and audit evidence stay visible. |

The current release summary consolidates the findings and links to the
[GLM reconciliation](GLM53_PRODUCTION_READINESS.md), [previous cleanup](cleanup/FINAL_VALIDATION.md),
and [historical validation](VALIDATION.md). Prior reports retain their provenance
and original references. Identical copies appearing in separate checksum manifests
provide evidence for distinct runs. They remain in place with datasets, migrations,
compatibility shims and the existing uncommitted work.

## Repository layout

| Path | Responsibility |
|---|---|
| `itlr/`, `web/` | FastAPI, retrieval, generation, ingestion, Express and PostgreSQL-backed learning |
| `scripts/`, `eval/`, `tests/` | Operator tools, reproducible evaluation and Python regression tests. Web tests sit alongside Web source. |
| `data/`, `configs/`, `var/` | Versioned inputs and source policy. `var/` holds local model, artifact and catalog runtime data. |
| `deploy/`, `compose.*.yml`, `.github/` | Runbooks, deployment profiles and CI |
| `docs/`, `reports/` | Maintainer guides and decisions, current release summary and historical evidence |

Graphify extracted 265 source and test files locally, with 2,738 nodes and
7,567 edges. Eleven files yielded no symbols. Text reference and Git index checks
covered configuration, docs, scripts, package manifests and deletion candidates.
Ponytail and Agent Skills informed the single-parser reduction and the decision to
keep compatibility shims and checksummed evidence. Superpowers informed the final
verification. TokenEconomizer reported micro-skills disabled. Project memory
was updated in the repository. Claude-Mem saved the verification as observation 10.

## Test and quality evidence

| Check | Fresh baseline | Fresh final |
|---|---:|---:|
| Python full suite | 567 passed in 84.15 s | 567 passed in 81.53 s |
| Python statements on `itlr/` | 68.17% (4,733/6,943) | 68.17% (4,733/6,943) |
| Web full suite | 177 passed in 34 files | 179 passed in 34 files |
| Web lines | 55.29% (857/1,550) | 55.36% (857/1,548) |
| Web statements / branches / functions | 52.18% / 43.06% / 46.48% | 52.29% / 43.83% / 46.48% |

- **PASS:** Web typecheck, ESLint and build, Python compileall and pip check,
  and Compose config for local, agent and monitoring profiles. The agent config
  check used distinct fixture reader and writer keys.
- **PASS in scope:** Both npm audits returned zero findings. Bandit reported
  zero High findings. pip-audit reported zero findings for the packages it
  resolved and could not audit installed `torch 2.15.0+cpu` through PyPI.
  The credential-format scan found zero matches in the inspected additions.
- **PASS:** 636 local links and anchors in 122 Markdown files, 12 Mermaid
  renders in headless Chrome with Mermaid 11.12.0, 17 Bash syntax checks,
  `git diff --check`, and four recent SHA256 evidence manifests.

Python ran `coverage run --source=itlr -m pytest tests/ -o addopts='' -q -ra`
with local single-thread limits, cloud keys unset, Ollama disabled and reranker
disabled. Web ran `npm run typecheck && npm run lint && npm run build && npm test`.
The intermediate Python run caught links to the report before it existed.
After the report and anchors were in place, the full run passed. The first
parser pass reduced measured line coverage by 0.06 points. PDF concurrency and
GIF validation tests exercised existing behaviors and restored the baseline line
count with fewer instrumented lines.

The fresh frozen holdout used cached multilingual E5-base and a disposable
Qdrant v1.18.0 instance with 1,576 verified points. The fixture and artifact
fingerprints match the [previous replay](cleanup/holdout-after.json).
Phase A and gated native each retained **83.33% Recall@5, MRR@5 and nDCG@5** and
**8/8 negative/OOD cases empty** on the 20-case holdout. Item order was identical
on all cases. Phase A chunk order was identical and one native case changed its
chunk order within the same item order. Qrels are AI-drafted. The native experiment
remains evaluator-only. [Runner](../eval/eval_staging_holdout.py)

## Release gates

**LOCAL READY · STAGING HOLD · PRODUCTION NO-GO**

- **Generation SLO:** Prior real Qwen2.5:3b CPU Web SSE run reached 90.96 s
  total p95 at concurrency 4 against the 45 s gate, with 3/4 accepted.
  [Benchmark scope](cleanup/FINAL_VALIDATION.md#generation)
- **Human review:** Independent faithfulness scores remain `null`. The 20-case
  historical packet has no reviewer scores. [Review handoff](GLM53_PRODUCTION_READINESS.md#independent-reviews)
- **Tenant and operations:** Single-tenant staging uses one data boundary. SaaS
  requires verified cross-tenant membership and storage isolation. Same-host
  recovery has prior isolated evidence. Multi-host recovery, sustained generation
  load and production image certification remain open. [Gate matrix](GLM53_PRODUCTION_READINESS.md#gate-matrix)
- **External review:** GLM review and staging cloud measurements remain unverified.
  [Audit scope](GLM53_REPO_AUDIT.md)
