# Final validation · 2026-11-19

## Verified

- Full Python and Web regressions, Web typecheck/lint/build, and Python compileall.
  The crawl-delay test's first post-refactor run caught host timing sensitivity. The
  test now controls elapsed time and validates the precise remaining delay.
- Qdrant snapshot round trip and alias rollback, Redis atomic quota, distributed permit
  and circuit expiry, PostgreSQL parallel job claims and fencing, and a PostgreSQL
  dump restored into a separate DB with two equivalent job rows.
- A disposable Compose stack using the local and agent profiles, prebuilt images,
  current code/build output, fixture Qdrant keys, and a copy of the probed artifacts.
  Schema migration, catalog sync of 118 resources, API readiness, Web readiness,
  authenticated progress, concurrent saves, support-role handoff resolution and SSE
  completed successfully. Two initial fixture starts failed on mount layout and the
  writable activation lock. The successful run uses a read-only model cache and
  a writable isolated artifact copy.
- Both frozen holdout runs used the same qrels, threshold 0.84 and artifact version.
  Exact FAISS versus Phase A parity was checked independently. Native experimental
  chunk IDs differed on two cases with identical item ranking and aggregate quality.
- Python package wheel includes the agent knowledge JSON and provider observability
  dependencies. No change to npm lockfile, approved data, migration history, or qrels.
- The 7 Mermaid diagrams in the entry points and architecture references rendered to
  SVG in Chrome with a pinned Mermaid bundle. Local file links in changed Markdown
  resolve, 5 new Bash snippets passed syntax checks, and Compose YAML parses.
- A scoped credential-format scan found no matches in added diff lines and cleanup
  files. Scope covers common provider, GitHub, AWS and private-key formats. Full-history
  secret scanning remains outside this evidence.

## Generation

Qwen2.5:3b ran locally with CPU limited to four cores. The authenticated Web SSE
workload used the same four fixed queries as the staging checkpoint, in batches of
1, 2 and 4, against the isolated Compose stack. The p95 gate remains **FAIL**.

| Concurrency | Accepted | First delivered text p50 / p95 / p99 (s) | Total p50 / p95 / p99 (s) |
|---:|---:|---|---|
| 1 | 1/1 | 37.52 / 37.52 / 37.52 | 37.56 / 37.56 / 37.56 |
| 2 | 2/2 | 19.49 / 35.59 / 37.03 | 19.51 / 35.62 / 37.05 |
| 4 | 3/4 | 41.50 / 43.26 / 43.42 | 42.51 / 90.96 / 97.66 |

Total includes the 99.34-second abstention. The first-text metric excludes it because
no text was delivered. These are small ordered batches. Ollama reported 7,278 prompt
tokens and 74 completion tokens. All seven requests lacked explicit provider cache
metadata. Measured cache hit, cloud spend and electricity cost remain unknown.
[Benchmark output](ollama.json) · [Workload](../../eval/bench_agent_gateway.py)

## Scope limits

The Compose smoke uses prebuilt base images. A rebuild from a fresh upstream base,
runtime monitoring-stack certification, signed SBOM, production image scan, network
failover across hosts, and hosted GitHub CI execution were outside the verified scope.
The current documentation separates observed capabilities from those release gates.

The private raw logs and environment snapshots stay in the local scratch directory.
The [metrics](BEFORE_AFTER_METRICS.md) report contains measured counts and links to
compact evidence. [Evidence checksums](SHA256SUMS.txt) · [Release disposition](RELEASE_READINESS.md)
