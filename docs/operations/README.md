# Operations runbook

## Startup and monitoring

Check FastAPI `/live` for process reachability and `/health` for the loaded artifact and
vector store. Web `/ready` checks PostgreSQL connectivity. Verify the selected artifact
version and manifest hash on each replica. Use the monitoring overlay on a trusted host.

Set `GRAFANA_ADMIN_PASSWORD` and `ITLR_ADMIN_TOKEN` in the private Compose environment.
Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318` before starting the API
when traces are needed.

```bash
docker compose --env-file .env.docker -f compose.local.yml -f compose.monitoring.yml \
  --profile monitoring up -d
```

Grafana listens on loopback port 3001 by default. Open **ITLR RAG / LLM** to
check API rates and latency, TTFT, generation modes, SSE outcomes, citation
status, artifact fingerprint and store health. Prometheus exposes targets and
alerts on loopback port 9090. In Grafana Explore, use Tempo for `itlr-api` traces
and Loki for `{service="api"}` or `{service="web"}` logs. The overlay includes
host-level telemetry and Docker socket access. [Compose profile](../../compose.monitoring.yml)

## Troubleshooting

| Symptom | Check |
|---|---|
| API live, readiness 503 | Resolve the artifact pointer, manifest, model cache, and Qdrant alias/read access against the expected fingerprint. |
| Web ready, course detail missing | Check that the probed catalog and PostgreSQL sync used the same source version. |
| Search/chat admission 503 | Check Redis connectivity, quota storage, and shared namespace. |
| SSE stream ends early | Check the request ID, guard/abort counters, upstream health, and timeout. A partial response is provisional until the final event. |
| Agent reports insufficient evidence | Inspect the generation mode, retrieved candidates, and selected chunk IDs before changing corpus or routing. |
| Traces missing | Check `OTEL_EXPORTER_OTLP_ENDPOINT`, collector and Tempo readiness, then query Grafana by trace ID. |

## Backup and recovery

1. Record the API fingerprint and Qdrant alias. Persist the PostgreSQL dump, manifest and
   artifact inventory, and Qdrant snapshot in access-controlled storage.
2. Restore PostgreSQL to a fresh database and Qdrant to a separate collection. Verify
   expected counts, app readiness, snapshot checksum and restored vector payloads.
3. For artifact rollback, pin the old Qdrant collection and align its alias with the
   restored artifact version before reload. Restart/reload each replica and check its
   actual fingerprint. Rotate the shared cache epoch if invalidating cached data.
4. Recover failed work through the PostgreSQL lease/retry contract. Verify stale-worker
   fencing before retrying a job. Dead letters remain auditable.

[Qdrant rollback](../architecture/QDRANT_MIGRATION.md) ·
[Backup commands](../../deploy/PRODUCTION.md#6-backup-và-phục-hồi) ·
[Incident and rollback procedures](../../deploy/PRODUCTION.md)
