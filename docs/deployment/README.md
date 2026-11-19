# Deployment guide

| Profile | Intended use |
|---|---|
| Native | Backend or Web development with an explicitly selected PostgreSQL database |
| `compose.local.yml` | Local Web, API, PostgreSQL, and Ollama |
| `compose.local.yml` + `compose.agent.yml` | Opt-in Redis and Qdrant Phase A, with an optional worker and gated provider routing |
| `compose.local.yml` + `compose.monitoring.yml` | Loopback observability for a trusted development host |
| `compose.production.yml` | Proposed TLS and private-network topology pending the release gates |

Prepare artifacts and the catalog before starting the applications. Run schema and catalog
jobs explicitly, verify API fingerprint and Web readiness, then run the authenticated smoke
probe. Keep keys separate by role, including Qdrant reader/writer and the Web-to-API
principal key. [Setup and credentials](../../deploy/DEPLOY.md) · [Production topology](../../deploy/PRODUCTION.md)

The current test uses pinned fixture artifacts and prebuilt base images. Multi-host
network failover and fresh production image certification remain open.
[Release evidence](../../reports/cleanup/FINAL_VALIDATION.md)
