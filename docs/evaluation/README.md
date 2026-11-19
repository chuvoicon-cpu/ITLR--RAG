# Evaluation guide

- [Ranking and ground-truth design](../EVALUATION.md)
- [Retrieval, provider, and citation semantics](../RAG.md)
- [Qdrant parity, snapshot, and rollback](../architecture/QDRANT_MIGRATION.md)
- [Independent-review procedure](../../reports/release-readiness-evidence/HUMAN_REVIEW_PROTOCOL.md)

Compare Phase A and native gated on unchanged inputs with a disposable Qdrant service
and the exact version of the artifact used in service. The output JSON records the
fixture hash and ranked chunks. `--artifacts` takes the probed version directory.

```bash
.venv/bin/python -m eval.eval_staging_holdout --artifacts "$VERIFIED_ARTIFACT_DIR" --out "$EVIDENCE_DIR/holdout.json"
```

Record real SSE completion, time to first delivered text, end-to-end latency, and
acceptance by workload. Validate citation identity separately from semantic support.
Human scores require independent reviewers and preserve abstentions in the denominator.
