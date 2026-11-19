# Vận hành và mở rộng

Compose overlay kết hợp PostgreSQL, Web, FastAPI, Redis và Qdrant. Ollama dùng profile tùy chọn. Qdrant và Redis dùng mạng Docker riêng của project; API/Web/PG bind loopback theo compose gốc. API dùng reader key, tác vụ indexer riêng dùng writer key. Mặc định overlay dùng template/extractive `LLM_PROVIDER=none`. Đặt provider rõ ràng để bật generation. Redis rate limit và global provider quota áp dụng chung cho các API instance. `ITLR_CHAT_CONCURRENCY` giới hạn số chat active cho từng process, từ chối sớm khi bão hòa và trả slot sau cancel. PostgreSQL dùng pool hiện tại. Build, crawl, probe, eval và publish chạy ngoài request path, có thể gọi từ scheduler hiện hành.

Compose local có một Web và một API, với data mount local. Web rate limit và presence tiếp tục dùng bộ nhớ process. Sử dụng chung PostgreSQL, Redis và Qdrant cần cấu hình private networking, TLS/ACL, pool tổng, shared session/real-time semantics và rollout theo fingerprint trước khi chạy nhiều host. Redis cache có thể mất mà dữ liệu bền vững còn trong PostgreSQL và Qdrant. Docker health/readiness kiểm artifact, điểm Qdrant theo revision và PostgreSQL. Disable endpoint backend public khi đưa danh tính Web vào quota riêng mỗi user.

Trước production cần chứng minh capacity theo RPS, p95/p99, TTFT, timeout, CPU/RAM và saturation từng dependency. Các mức concurrency 1/2/4/8 đã thử ở mức như báo cáo benchmark. Concurrent requests, DAU và số tài khoản là đại lượng riêng. Model theo tác vụ, user chat quota, circuit breaker, shared concurrency và PostgreSQL job leases đã có. HA và multi-host cần kiểm chứng riêng. [Benchmark](../../reports/PERFORMANCE_BENCHMARK.md).

## Khởi chạy staging cách ly

Chuẩn bị E5 cache, artifacts staging và catalog bằng [DEPLOY](../../deploy/DEPLOY.md) và
[Qdrant migration](QDRANT_MIGRATION.md). Dùng `.env.docker.example` để tạo `.env.agent` riêng với PostgreSQL/Web secrets và hai
Qdrant keys. Đặt `ITLR_VECTOR_BACKEND=qdrant` khi đã có parity report và
`ITLR_QDRANT_NAMESPACE` riêng cho project. Lưu report dưới `var/qdrant-parity.json`
để indexer đọc. Khi xuất catalog sang đường dẫn staging, chỉ rõ `--snapshot` dưới staging.

```bash
compose_agent() {
  docker compose -p itlr-agent-staging --env-file .env.agent \
    -f compose.local.yml -f compose.agent.yml "$@"
}
compose_agent build api web
compose_agent up -d --wait postgres qdrant redis
compose_agent run --rm qdrant-indexer stage --artifacts /app/var/artifacts/versions/VERSION
compose_agent run --rm qdrant-indexer promote --artifacts /app/var/artifacts/versions/VERSION \
  --parity-report /app/var/qdrant-parity.json
# Sau promote, cập nhật CURRENT.json bằng workflow versioning trước khi start/reload API.
compose_agent run --rm --no-deps web node dist/db/migrate.js
compose_agent run --rm --no-deps web node dist/db/sync-courses.js
compose_agent up -d --wait api web
```


## Hàng đợi ingestion và embedding

Sau khi áp schema PostgreSQL, vận hành dùng `ITLR_JOB_DATABASE_URL` của role giới hạn vào
`agent_jobs` và sequence. Cấp thư mục hoặc volume riêng cho `ITLR_JOB_STAGING_ROOT` và
chuẩn bị cache E5 cho container worker. `ITLR_JOB_INGEST_SOURCES` có thể giới hạn nguồn
theo cấu hình crawler. Jobs chạy Python pipeline đã có, DB cấp lease và heartbeat. Mỗi
retry gắn claim token mới để chặn cập nhật từ worker cũ. Embedding luôn chạy
`--real-only --no-activate`. Thay đổi revision đang phục vụ vẫn qua workflow promote.

```bash
python -m itlr.agent_jobs enqueue ingest KEY_FOR_INGEST_123456
python -m itlr.agent_jobs enqueue embed KEY_FOR_EMBEDDING_123456
python -m itlr.agent_jobs worker
python -m itlr.agent_jobs dead-letter
```

Queue có at-least-once execution. SQLite upsert làm ingest retry được và staging builds
có thể để lại revision chưa promote. Không dùng PostgreSQL lease để suy ra exactly-once
cho thao tác ngoài database. Hạ tầng nhiều worker chỉ chia sẻ stage data khi dùng
chung volume có cơ chế khóa phù hợp. [PostgreSQL SKIP LOCKED](https://www.postgresql.org/docs/16/sql-select.html).
