# ITLR–RAG agent platform · Release readiness

Ngày 2026-11-18. **LOCAL READY** và Compose single-host đã kiểm trong phạm vi dưới đây. **PRODUCTION NO-GO**. Baseline lấy ở HEAD `ce53b146` khi working tree sạch. Không có cloud generation trong lần chạy này. Dữ liệu bền vững phục vụ test nằm trong project Compose và thư mục artifacts cách ly.

## Before → After

| Hạng mục | Before | After |
|---|---|---|
| Dense retrieval | FAISS IndexFlatIP trong process | FAISS mặc định và Qdrant opt-in với 1.576 điểm E5-base. Parity 45/45, negative rỗng 8/8. |
| Hybrid | BM25/RRF gated tại app | Phase A giữ hành vi. Phase B có native dense/sparse trong evaluator, Recall@5 97,30% nhưng chỉ 4/8 negative rỗng. |
| Chat | Intent, evidence và generation | Bounded knowledge tool Pydantic, vẫn giữ fast paths và evidence validation. |
| Công cụ riêng tư | Web learning/catalog routes | Web agent tools đọc progress, catalog, preview và save được xác nhận. Hai concurrent saves cùng key trả một kết quả. Handoff trả 501. |
| Cache và quota | RAM limiter, số liệu provider hạn chế | Public L1/L2, quota Redis, per-process chat backpressure, global provider reservation và usage ghi theo metadata. |
| Vận hành | Một Web/API với local artifacts | Compose có internal Qdrant/Redis, indexer tách credentials, stage, frozen parity, promote, snapshot và rollback. |
| Release | Production NO-GO | Production NO-GO. SLO 45s, human faithfulness, npm audit dev và rollout/capacity nhiều host còn mở. |

## Theo phase

| Phase | Tệp và quyết định | Bằng chứng, hạn chế và bước kế tiếp |
|---|---|---|
| 0 | [Audit](../docs/architecture/AI_AGENT_AUDIT.md), [plan](../docs/architecture/AI_AGENT_MIGRATION_PLAN.md), [graph](../docs/architecture/AI_AGENT_DEPENDENCY_GRAPH.md) | Baseline 534 Python, 166 Web. Typecheck, lint, build Web pass. Repo không có môi trường ban đầu, đã dựng Python 3.12 và chạy lại trước sửa code. |
| 1 | [Adapters](../itlr/retrieval/vector_store.py), [migration tool](../itlr/retrieval/qdrant_artifacts.py), [ADR](../docs/decisions/ADR-014-versioned-qdrant.md) | Count, ownership, provenance, exact ID, two-revision staging, update/delete, alias rollback và snapshot restore đã thử. Compose nạp revision thật từ reader key. Cần thêm nhiều corpus/revision cho rollout. |
| 2 | [Knowledge tool](../itlr/chatbot/agent_tools.py), [Web tools](../web/src/routes/agent.routes.ts), [SQL](../web/src/db/schema.sql) | Input/output, user spoof, CSRF, scope, save idempotency và SSE completion/cancel đã thử. Runtime LLM dùng đọc tri thức, tool write chỉ nhận yêu cầu trực tiếp của người dùng. Cần workflow tiếp nhận handoff. |
| 3 | [Cache](../itlr/retrieval/cache.py), [provider client](../itlr/chatbot/llm_client.py), [thiết kế](../docs/architecture/REDIS_CACHE_DESIGN.md) | Redis coalescing, revision scope và timeout/outage behavior đã kiểm. Compose ghi L1/L2 hit thật. Provider cache fixture phân biệt zero và missing. Hit rate/cost/savings cloud chưa đo. |
| 4 | [Compose](../compose.agent.yml), [limits](../itlr/api/ratelimit.py), [provider quota](../itlr/chatbot/provider_budget.py) | Search 1/2/4/8 và staging restart đã chạy. Idempotent indexer là job một lần; pipeline ingest hiện có chạy bên ngoài request. Cần hoàn tất quota theo authenticated user, task-based routing, circuit breaker, durable distributed jobs và multi-host tests. |
| 5 | [Evaluation](AGENT_EVALUATION.md), [benchmark](PERFORMANCE_BENCHMARK.md), [evidence](final-e2e-evidence/agent-platform-2026-11-18/SHA256SUMS.txt) | Full regression và Compose E2E chạy riêng. CI đã thêm lệnh live Qdrant/Redis; hosted workflow chưa chạy. Bandit High 0. npm audit full High do chuỗi công cụ dev. Python audit môi trường nâng dependencies báo 0 advisory ở packages quét được, Torch CPU wheel nằm ngoài PyPI audit. |
| 6 | [Architecture](../docs/architecture/AI_AGENT_ARCHITECTURE.md), [Qdrant](../docs/architecture/QDRANT_MIGRATION.md), [Tools](../docs/architecture/AGENT_TOOL_CONTRACTS.md), [Cache](../docs/architecture/REDIS_CACHE_DESIGN.md), [Scalability](../docs/architecture/SCALABILITY_PLAN.md), [Security](../docs/architecture/SECURITY_REVIEW.md) | README, AGENTS, CHANGELOG, ADR và memory cập nhật. Evidence mới lưu cùng checksum. |

## Skills và công cụ thực tế

Graphify AST được chạy trước/sau, giới hạn ở source để không gọi semantic provider. Ponytail
được dùng để giữ BM25/RRF và các contract cũ, dùng HTTPX có sẵn cho Qdrant và reuse PostgreSQL
transaction. Agent Skills đã dùng gồm interface design, TDD, incremental implementation,
security, code review, source-driven development và Git workflow qua kiểm diff. TokenEconomizer
launcher trả micro-skills đang tắt cho repo; áp dụng chọn lọc path/output trực tiếp. Engineering
Superpowers riêng **UNAVAILABLE**, thay bằng Agent Skills. Repo yêu cầu lưu memory tại chỗ.
Không sử dụng Claude-Mem MCP.

## Gates đã chạy

| Kiểm tra | Kết quả |
|---|---|
| Python pytest | **548 PASS / 0 skip**, 88,13s, gồm fixture provider/stream và các contract mới |
| Web | **168 PASS / 33 file**, coverage lines 51,90% (777/1.497), typecheck/lint/build PASS. Baseline lines 52,41% (759/1.448). |
| compileall, pip check và Bandit | PASS, Bandit **0 High** |
| Qdrant/Redis live | PASS trên container thật. Redis stop cho quota 503, cache bypass và search hồi phục 200 sau restart. |
| Compose E2E | PASS trong phạm vi test, xác minh reader-only, user isolation, idempotency và SSE. |
| Persistence và backup | Qdrant/API recreate giữ revision; PostgreSQL restore sang database test cùng số users/courses/plans. Snapshot Qdrant fixture restore và kiểm lại vector/payload. |
| Dependency audit | Python 0 trên package audit được sau nâng phiên bản local; Torch CPU wheel chưa audit. npm runtime 0, full dev gate FAIL. |

[Python log](final-e2e-evidence/agent-platform-2026-11-18/python-final.log) ·
[Web log](final-e2e-evidence/agent-platform-2026-11-18/web-final.log) ·
[Compose E2E](final-e2e-evidence/agent-platform-2026-11-18/compose-e2e.log) ·
[Redis outage](final-e2e-evidence/agent-platform-2026-11-18/redis-outage.log) ·
[Persistence](final-e2e-evidence/agent-platform-2026-11-18/compose-persistence.log).

## Cổng phát hành còn mở

- **P0** Human faithfulness, semantic groundedness và evaluator độc lập vẫn `null`. Blind suite
  template/extractive cho thấy hạn chế refusal, cần người chấm trước production.
- **P0** Bằng chứng cũ CPU uncached vượt 45s. Benchmark mới đo pipeline không cloud và
  gồm retrieval, nên chưa xác lập SLO generation. Provider cost, pricing savings và TTFT model
  chưa đo do thiếu quyền chạy API tính phí.
- **P1** npm audit full báo 12 mục High lan từ một advisory `picomatch` ở cây dev. npm audit runtime trả 0. Không tìm
  được version đã vá trong registry lúc chạy. [Advisory](https://github.com/advisories/GHSA-fc5q-39xc-vjpf).
- **P1** Multi-host/HA, tenant membership thật, quota theo user xuyên các services, authorization
  review toàn hệ thống và soak dài chưa có bằng chứng. Xem [security](../docs/architecture/SECURITY_REVIEW.md).
- Bản staging chỉ dùng các project/collections disposable. Khi export catalog, script mặc định
  cũng ghi snapshot tracked; file đã được khôi phục về bytes HEAD và frozen qrels cũng đã đối chiếu.

Không thay đổi ngưỡng, golden set hoặc production runtime. Không commit, push hay deploy.
