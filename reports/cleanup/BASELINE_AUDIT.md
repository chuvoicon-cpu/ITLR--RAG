# Baseline audit · 2026-11-19

The working branch was `main` at `ce53b1467c4ed14aa2a1ebf055a34869c2749dea`.
It already contained the uncommitted agent and staging work used as the baseline.
The index contained 949 paths, with 149 untracked files and 46,554 ignored entries.
The private scratch snapshot contains entry status, diff, full ignored inventory and hashes.
[Working-tree file inventory](FILE_INVENTORY.csv)

| Gate | Measured baseline |
|---|---|
| Python | 564 PASS, statement coverage 4,736/6,957 (68.08%). |
| Web | 177 PASS, 857/1,550 lines (55.29%). Typecheck, lint and build passed. |
| Security | Bandit High 0 in application code. Installed Python audit and npm dev/runtime reported zero known advisories. |
| Qdrant / Redis / PostgreSQL | Live fixture checks passed for alias rollback, snapshots, quotas, shared permits, cache isolation, and worker leases/dead-letter behavior. |
| Frozen holdout | Both paths 83.33% Recall@5, MRR@5, nDCG@5 and 8/8 empty negative/OOD. |
| Agent and release | The staging checkpoint supplies prior local model timings, SSE cancellation, and failure-recovery evidence. Tenant membership, human review, and the generation SLO remain open. |

The first Python attempt explicitly set `LLM_PROVIDER=none`. It failed 31 tests that
intentionally exercise automatic provider selection. The baseline above comes from
the normal suite with that selector and cloud credentials unset and local generation
disabled by `USE_OLLAMA=0`. No provider was called by the test suite.

## Findings and scope

- Package metadata omitted observability dependencies required by FastAPI and omitted
  the agent's JSON knowledge tables from wheels. The requirements file duplicated `httpx`.
- API startup and metrics each implemented provider selection in addition to the gateway.
  Startup missed secret-file configuration and could warm Ollama on a cloud-routed process.
- `make clean` removed the artifact and evidence trees. The Nodemon configuration had no
  caller in the supported build, dev, runtime, or CI paths. CI reran tests already exercised by
  the main pytest invocation.
- Historical evidence contains identical and empty generated logs. Report references,
  checksum manifests, and provenance justify keeping them in place. Legacy pickles,
  explicitly documented API-only Compose and external import candidates were retained.
  [Deletion decisions](DELETE_MANIFEST.md)
- Static Graphify extraction covered 157 Python/TypeScript/JavaScript source files.
  Dynamic handlers, deployment entry points, and serialization contracts were checked
  through direct source/reference review and probes. Its 1,713 nodes and 4,749 edges
  describe extraction scope, with external callers and runtime discovery outside that graph.

## Skills and tools

| Capability | Use |
|---|---|
| Agent Skills | Followed TDD, security and hardening, code review, and documentation workflows. |
| Ponytail | Reviewed obsolete configs, duplicate provider selection, and duplicated CI work. |
| Graphify | Extracted source graphs before and after with the installed AST extractor. |
| TokenEconomizer | Status verified from the installed launcher. Microskills and repomap were off. |
| Superpowers | No engineering skill/MCP discovered. The repository's historical Superpowers documents were retained and Agent Skills supplied the workflow. |
| Claude-Mem | Project search reached the local worker. The cleanup handoff was saved as observation #9 and in repository `PROJECT_MEMORY`. |

[Final validation](FINAL_VALIDATION.md) · [Staging checkpoint](../STAGING_READINESS.md)
