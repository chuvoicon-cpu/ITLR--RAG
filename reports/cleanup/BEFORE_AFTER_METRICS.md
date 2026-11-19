# Before and after · 2026-11-19

| Metric | Before | After | Evidence |
|---|---:|---:|---|
| Tracked paths in Git index | 949 | 949 | Worktree-only changes. 948 tracked paths remain on disk and the obsolete config is pending deletion. [Inventory](FILE_INVENTORY.csv) |
| Files safely deleted | 0 | 1 | [Deletion manifest](DELETE_MANIFEST.md) |
| Duplicate provider selection implementations | 3 | 1 | Python source inspection. Across the prewarm, metrics, and resolver functions, AST branch nodes decreased from 20 to 13 and function lines from 72 to 55. |
| Graphify source coverage | 157 files, 1,713 nodes, 4,749 edges | 157 files, 1,715 nodes, 4,755 edges | Static AST graph. A named resolver adds call edges. AST branch count does not include boolean operators. |
| Python requirements entries / unique | 27 / 26 | 26 / 26 | One repeated `httpx` line removed. |
| Python package direct runtime dependencies | 18 | 22 | Add four already-used observability libraries to package metadata. |
| npm production direct dependencies | 17 | 17 | No manifest or lockfile change. |
| Python tests | 564 pass | 567 pass | 3 new regression cases. |
| Web tests | 177 pass | 177 pass | 34 files. Typecheck, lint and build passed. |
| Python statement coverage | 68.08% (4,736/6,957) | 68.17% (4,733/6,943) | Coverage of the `itlr` package. |
| Web line coverage | 55.29% (857/1,550) | 55.29% (857/1,550) | Vitest coverage. |
| Bandit High | 0 | 0 | Same `itlr` scope. Final scan including `scripts` also returned 0 High. |
| Known dependency advisories | 0 | 0 | npm dev/runtime and pip audit. Previous Picomatch alert withdrawn, see [dependency audit](DEPENDENCY_AUDIT.md). |
| RAG quality | 83.33% Recall@5, MRR@5, nDCG@5; 8/8 negatives empty | Same | [Before](holdout-before.json), [after](holdout-after.json). [FAISS/Phase A parity](faiss-parity.json) on 45 frozen cases. |
| Retrieval p95 | Phase A 10.84 ms, native 27.19 ms | Phase A 13.06 ms, native 33.03 ms | Two single-thread probes on the same host. Treat timing differences as observations, with no throughput improvement established. |
| Agent generation p95 at concurrency 4 | 91.50 s, 3/4 accepted | 90.96 s, 3/4 accepted | [Prior benchmark](../STAGING_READINESS.md), [current benchmark](ollama.json). |
| Search-only two-replica soak | 120/120 HTTP 200, p95 15.94/16.03 ms | 120/120 HTTP 200, p95 16.04/14.81 ms | 120 seconds, 1 RPS aggregate, cached query. [Current soak](soak.json) |
| Documentation | Vietnamese overview and procedures in one 446-line README | English overview, Vietnamese setup and five topic guides, all reviewed local file links resolve | [Documentation index](../../docs/README.md) |
| Release blockers | Tenant isolation, independent human evaluation, generation SLO, cloud and multi-host scope | Same P0 blockers, fresh single-host integration evidence | [Release gates](RELEASE_READINESS.md) |

All 703 protected input and evidence files from the working-tree baseline retain their
original SHA256. Freeze manifests and source evaluations were kept in place.
