# Refactor changelog · 2026-11-19

| Slice | Existing files | Change and verification |
|---|---|---|
| Provider routing | `itlr/api/server.py`, `itlr/chatbot/llm_client.py`, `tests/test_api_hardening.py` | Startup, metrics, and gateway share one selection helper. Startup now recognizes cloud credentials supplied by file. Metrics resolve the configured route without reading files or probing the provider. The focused test failed before the change and passed after it. |
| Python packaging | `pyproject.toml`, `requirements.txt`, `tests/test_scripts_and_configs.py` | Declare existing observability dependencies and include the agent JSON data in wheels. Remove the repeated requirement. Manifest/knowledge data regressions went red then green. Built wheel inspected. |
| Test reliability | `tests/test_http_layer.py` | Existing crawl-delay test became flaky while the host ran multiple fixtures. A scripted clock now asserts the exact remaining 4.75 seconds after 0.25 seconds elapsed. Runtime rate limiting is unchanged. |
| Developer and CI cleanup | `Makefile`, `.github/workflows/ci.yml`, `.env.example`, `.gitignore` | Retire recursive Make deletion and redundant CI test step. Document explicit routing and secret file settings, and ignore local environment and coverage variants. Verify dry run, focused/full tests and YAML. |
| Documentation | `README.md`, `CHANGELOG.md`, `docs/API.md`, `docs/PROJECT_MEMORY.md`, `docs/SECURITY.md`, `docs/TESTING.md` | English default and original Vietnamese instructions retained in the new `README.vi.md`. Add contribution and security policies, doc index, operational runbooks and release records. |
| File removal | `web/nodemon.json` | Tracked obsolete dev watcher config. [Deletion manifest](DELETE_MANIFEST.md). |

The prior README content is retained under `README.vi.md` with a language switch. Existing
deployment, architecture and evidence paths continue to resolve. No other path moved.

Revert individual change hunks relative to the recorded worktree baseline, which includes
pre-existing changes. For the unchanged deleted config use the Git revision in the manifest.
The cleanup performs no migrations against existing databases and changes no persisted
artifact format. [Validation](FINAL_VALIDATION.md)
