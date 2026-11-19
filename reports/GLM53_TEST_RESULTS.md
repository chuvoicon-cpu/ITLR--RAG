# GLM-5.3-Flash audit test results

Follow-up baseline on 2026-11-19, before edits, on working tree based on
`ce53b1467c4ed14aa2a1ebf055a34869c2749dea`. Python 3.12.16 and Node 22.22.1.

| Check | Result | Evidence |
|---|---|---|
| Python regression | **VERIFIED · PASS** | Exit 0. 567 passed, zero failed or skipped, 66.45 s. |
| Web regression | **VERIFIED · PASS** | Exit 0. 177 passed in 34 files, 8.90 s. Lines 55.29% (857/1,550), branches 42.97% (502/1,168), statements 52.18%, functions 46.48%. |
| Typecheck/lint/build | **REUSED · PASS** | Previous audit ran `npm run typecheck && npm run lint && npm run build`. |
| Compile/package and scanners | **REUSED · scoped PASS** | Previous `compileall`, `pip check`, `pip-audit`, Bandit High 0, and npm runtime/full audits returned exit 0. pip-audit excluded the installed CPU torch build. |
| Frozen retrieval | **REUSED · scoped PASS** | Gated native and Phase A both 8/8 empty negatives on holdout, with 83.33% for each ranking metric. [Reconciliation](GLM53_PRODUCTION_READINESS.md#retrieval-evidence) |
| Multi-replica/failure drills | **REUSED · scoped PASS** | Isolated same-host shared quota, cache, outage and restore drills. [Cleanup validation](cleanup/FINAL_VALIDATION.md) |
| GLM API models/inference | **BLOCKED** | `APIVN_API_KEY` absent. Zero API requests this turn. |

Fresh baseline commands:

```bash
env -u APIVN_API_KEY -u LLM_PROVIDER -u DEEPSEEK_API_KEY -u OPENAI_API_KEY \
  -u DEEPSEEK_API_KEY_FILE -u OPENAI_API_KEY_FILE \
  USE_OLLAMA=0 DISABLE_RERANKER=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  .venv/bin/python -m pytest tests/ -o addopts='' -q -ra
(cd web && npm test)
```

The earlier 239.98 s Python run emitted a non-failing fixture connection reset.
The fresh 66.45 s run did not emit it. The earlier unsupported Vitest flag was
an invocation error. The fresh Web run emitted a Vite config deprecation warning.
Python coverage was not measured in this run.

Post-edit checks:

- **VERIFIED · PASS.** Ten targeted Python regressions passed in 2.93 s, exit 0.
  The cases exercise native dense gating, staging scope, signed principals, and
  bounded agent tools.
- **VERIFIED · PASS.** The report regression check first failed on the stale 4/8
  promotion claim and passed after correction. It recounts negative outcomes,
  checks frozen fixture and annotation provenance, verifies that human ratings
  remain blank, and checks the retained 75/100 score and local report links.
- **VERIFIED · PASS.** SHA256 manifests in the agent-platform, hardening,
  staging-sprint and cleanup evidence sets matched. HEAD, tracked diff hash and
  untracked path inventory matched intake. The temporary Graphify cache was
  removed after extracting the seven relevant source files.

```bash
env -u APIVN_API_KEY -u LLM_PROVIDER -u DEEPSEEK_API_KEY -u OPENAI_API_KEY \
  -u DEEPSEEK_API_KEY_FILE -u OPENAI_API_KEY_FILE \
  USE_OLLAMA=0 DISABLE_RERANKER=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  .venv/bin/python -m pytest tests/test_native_dense_gate.py tests/test_staging_scope.py \
  tests/test_web_chat_principal.py tests/test_agent_tools.py -o addopts='' -q -ra
```
