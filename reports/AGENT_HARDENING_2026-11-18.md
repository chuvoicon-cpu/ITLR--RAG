# ITLR–RAG — Agent hardening và release readiness

Ngày 2026-11-18. **LOCAL READY** trong phạm vi đã kiểm. **STAGING HOLD**, **PRODUCTION NO-GO**.

Baseline là worktree có sẵn của checkpoint [LOCAL READY trước](RELEASE_READINESS.md), gồm
các thay đổi chưa commit trên HEAD `ce53b14`. Baseline chạy lại 548 Python và 168 Web test,
Web line coverage 51,90%. Hosted CI, hạ tầng nhiều host và reviewer độc lập nằm ngoài bằng
chứng lần này. Chỉ dùng DB/cache/artifact test cô lập. Qdrant Phase A chạy opt-in và FAISS
vẫn là mặc định. Native hybrid chưa mở trong đường phục vụ.

## 1. Retrieval correctness

45 truy vấn frozen, 37 positive và 8 negative, 118 tài liệu/1.576 chunk E5. Nhãn giữ nguyên
từ engineering qrels. Cùng query embeddings và threshold 0,84, reranker tắt.

| Biến thể | Recall@5 | MRR@5 | nDCG@5 | Negative rỗng | Core p95 |
|---|---:|---:|---:|---:|---:|
| Phase A Qdrant dense + BM25/RRF | 82,43% | 65,50% | 68,79% | 8/8 | 14,28 ms |
| Native RRF với hai nhánh độc lập | 97,30% | 85,90% | 88,33% | 4/8 | 69,96 ms |
| Native RRF với dense floor chung | 82,43% | 79,73% | 79,53% | 8/8 | 23,50 ms |

Phase A khớp **45/45** thứ tự chunk với FAISS. Native gated giữ số judged items @5 trên
từng positive so với A. MRR cải thiện trong lần chạy này. Native ungated có sai khác nhẹ
nDCG so với 88,54% ở checkpoint trước. Vị trí các điểm sát nhau có thể đổi trong fusion.
Metric trong bảng dùng chính các kết quả của lần chạy hiện hành.

| Frozen negative | Max dense | Ungated item đầu, cosine, BM25 | Top-K ungated → gated |
|---|---:|---|---|
| Mật khẩu tài khoản hiện tại (`none-private`) | 0,80198 | — | 0 → 0 |
| Nhiệt độ nhà hiện tại (`none-live`) | 0,78034 | — | 0 → 0 |
| Calo ngày mai (`confirmation-negative-0`) | 0,80049 | `5114:1`, 0,7674, 14,1268 | 5 → 0 |
| Kết quả xổ số (`confirmation-negative-1`) | 0,78548 | — | 0 → 0 |
| Mật khẩu riêng trên server (`confirmation-negative-2`) | 0,81765 | `5021:6`, 0,7539, 17,1025 | 5 → 0 |
| OTP cá nhân (`confirmation-negative-3`) | 0,80103 | `5023:7`, 0,8006, 6,5563 | 1 → 0 |
| Bóng đá đang diễn ra (`confirmation-negative-4`) | 0,75542 | `5013:3`, 0,6895, 15,4714 | 5 → 0 |
| Vé tàu ngày mai (`confirmation-negative-5`) | 0,76105 | — | 0 → 0 |

Ground truth frozen của tám dòng là danh sách judgments rỗng. Filter version/approval
vẫn áp dụng cho cả hai nhánh. Lỗi do nhánh sparse từng vào fusion độc lập với score dense.
Ứng viên có rank BM25 cao đứng đầu RRF dù cosine dưới ngưỡng. Gate mới
tính eligible IDs bằng dense exact rồi áp `has_id` cho cả hai nhánh trước khi cắt top-K.
Raw có top 5, excerpt, rank/score dense/sparse, score RRF và filters từng case.
[Raw retrieval](final-e2e-evidence/agent-hardening-2026-11-18/native-diagnostics.json).

**HOLD promotion.** Human faithfulness và human-reviewed native cases là `null`.
[Packet và protocol hiện có](release-readiness-evidence/HUMAN_REVIEW_PROTOCOL.md).

## 2. Agent, quota, gateway và jobs

- **Agent** chạy qua Web JWT/CSRF. Handoff cần xác nhận, có receipt, replay và xử lý xung
  đột theo owner. Support admin list/resolve, audit lưu actor/time/request ID. Test HTTP
  xác minh forged user, ticket và plan concurrent replay, progress isolation, support role
  và signed upstream. Search tool có timeout 15s và browser cancel. Web sync cancel chặn
  ghi update khi chưa gọi storage. Python sync code đang thực thi có thể tiếp tục cho tới
  deadline của transport. SSE đóng upstream và trả slot.
- **Redis** xác minh signed user nhận 12 yêu cầu rồi 429, user khác trên cùng IP tiếp tục
  200. Sáu process cạnh tranh, Redis chỉ cấp hai slot đã cấu hình và trả slot sau release.
  Tenant-level policy còn BLOCKED bởi schema hiện chưa có tenant membership. Lease sau
  process loss hết hạn, Redis restart có thể làm mất các lease ephemeral.
- **Gateway** có breaker dùng chung theo provider, Retry-After có giới hạn, RPM/TPM
  reservation, model override theo evidence/chat và metadata cache chỉ từ provider.
  Breaker test qua Redis thật với lỗi control-plane được tiêm, không sinh model call giả.
  Paid cost/savings và cache tokens Ollama không báo đều `null`.
- **Jobs** PostgreSQL lease, heartbeat, retry backoff, idempotent enqueue và dead-letter.
  Bốn worker đồng thời chỉ một claim thành công. Phục hồi lease và claim-token fencing
  đã kiểm. Worker thật thu 25 mục từ MDN feed vào stage riêng. Hai mẫu prefix 2/25 tài liệu
  fail TF-IDF pruning và được ghi dead-letter. Quét prefix xác nhận 80 tài liệu đủ đa
  dạng cho TF-IDF. Embedding worker thật tạo 1.129 chunks, probe PASS và giữ stage ngoài
  pointer. Kiểm theo job ID riêng vì ingest chạy song song cũng ghi bảng jobs.
  Worker thật bị SIGTERM ở attempt 1. Lần chạy ngay sau đó tôn trọng lease và worker sau
  hết lease hoàn thành attempt 2. [Embedding](final-e2e-evidence/agent-hardening-2026-11-18/jobs-completion.log) ·
  [Worker restart](final-e2e-evidence/agent-hardening-2026-11-18/jobs-restart.log).
- **Outage/restore** pause Redis cho 503, API phục hồi 200. Pause Qdrant giữ liveness 200
  và readiness/search 503, rồi trở lại 200. PostgreSQL dump/restore giữ 7 users, 1 handoff,
  2 saved plans và 6 jobs trong checkpoint backup.

[Agent HTTP E2E](final-e2e-evidence/agent-hardening-2026-11-18/agent-e2e.log) ·
[Quota](final-e2e-evidence/agent-hardening-2026-11-18/principal-quota.log) ·
[Worker](final-e2e-evidence/agent-hardening-2026-11-18/jobs-postgres.log) ·
[Failure/recovery](final-e2e-evidence/agent-hardening-2026-11-18/failure-recovery.log).

## 3. Performance, cache savings và capacity

Đo trên một host CPU dùng PostgreSQL, Qdrant, Redis và Ollama trong containers, API/Web
native. Worker embedding có chia CPU trong một phần các phép đo. Đây là bài tải ngắn
và không đối chiếu trực tiếp tốc độ host/stack với báo cáo trước.

| Search simultaneous | RPS | p50 ms | p95 ms | p99 ms | HTTP 200 |
|---:|---:|---:|---:|---:|---:|
| 1 | 3,31 | 292 | 438 | 452 | 23/23 |
| 2 | 4,55 | 424 | 624 | 646 | 23/23 |
| 4 | 5,73 | 667 | 884 | 892 | 23/23 |
| 8 | 7,48 | 1.055 | 1.283 | 1.291 | 23/23 |

Sau khi dừng batch và Ollama, bài search-only đạt **10,46 / 13,55 / 14,80 / 10,98 RPS**
ở 1/2/4/8 request đồng thời. P95 tương ứng **115 / 249 / 335 / 874 ms**, mỗi mức có
23/23 HTTP 200. [Raw idle search](final-e2e-evidence/agent-hardening-2026-11-18/search-idle-load.json).

5 cặp cache miss/hit với cùng search response cho p50 **215,23 → 12,28 ms**,
giảm **94,3%** (~203 ms/request) trong workload glossary thử. L1 được invalidate từng cặp
trong namespace test. Tenant cache savings và hóa đơn provider vẫn `null`.
[Raw search và cache](final-e2e-evidence/agent-hardening-2026-11-18/search-cache-load.json).

| Web SSE + Qwen2.5:3b CPU | RPS | Accepted | TTFT p50 | TTFT p95 | Tổng p95 |
|---:|---:|---:|---:|---:|---:|
| 1 | 0,025 | 1/1 | 40,16s | 40,16s | 40,23s |
| 2 | 0,051 | 2/2 | 20,87s | 37,34s | 37,38s |
| 4 | 0,030 | 4/4 | 100,57s | 133,59s | 133,62s |

7/7 đều qua Web auth, retrieval, generation Ollama thật, SSE final/done, citation validation
và ghi hội thoại. Ollama báo 7.278 prompt tokens và 83 completion tokens. Provider không báo
cache split. Trọng số model đã warm và một số prompt lặp giữa các mức. TTFT là text frame tới
client, gồm chờ model lựa chọn evidence. P95 mẫu 1/2/4 chỉ là mô tả, chưa dùng làm SLA.
[Raw model load](final-e2e-evidence/agent-hardening-2026-11-18/ollama-agent-load.json).

Capacity model sơ bộ dùng `RPS_required ≤ workers_independent × service_rate × utilization`.
Search tại 4 simultaneous có 5,73 RPS, p95 dưới 1s trong workload đo. Hệ số dự trữ 0,70
cho khoảng 4 RPS/host để lập pilot, cần soak và kiểm saturation. Model CPU sample đơn là
khoảng 0,025 RPS hoặc 0,0175 RPS với hệ số 0,70. Bốn request đồng thời vượt 45s, nên
giữ mức acceptance pilot tối đa một inference active mỗi model runner cùng hardware.
Nhiều API replica dùng chung một Ollama runner vẫn chia cùng capacity generation.
Cần tách tải batch, đo cold/warm, sao lưu và theo dõi tail latency trong soak.

## 4. Gates và P0/P1/P2

| Mức | Trạng thái | Cổng |
|---|---|---|
| P0 | Đóng trong phạm vi frozen | Dense eligibility áp cho cả hai nhánh, 8/8 negative và không giảm judged hits @5 vs A. |
| P0 | BLOCKED | Human-reviewed retrieval/citation, faithfulness và promotion. |
| P0 | HOLD | SLO 45s Agent + LLM tại concurrency 4, p95 133,62s trên CPU. |
| P1 | Đóng trong phạm vi local | JWT/CSRF, support role, replay, quota principal, distributed slot, provider breaker, outage/recovery. |
| P1 | BLOCKED | Tenant policy chưa có membership, multi-host/soak, release image và paid billing chưa xác minh. |
| P1 | BLOCKED | npm registry vẫn báo High liên quan picomatch 4.0.7. GitHub advisory đã withdrawn, registry chưa có bản vá xác thực để nâng. Cây production audit 0. |
| P2 | Đóng | Web coverage lines 51,90% → 55,43% (857/1.546), không đổi phạm vi tính. |
| P2 | Đóng trong phạm vi PG | Claim fencing, restart, retry/dead-letter và restore. Worker dùng stage storage cục bộ. |

**559 Python PASS / 0 skip**, **176 Web PASS / 34 files**. Typecheck, lint, build, compileall,
pip check và Bandit High qua. Python audit 0 trên package kiểm được, PyTorch CPU wheel
ngoài phép audit PyPI. Full npm audit ghi 12 mục High do dependency graph, runtime 0.
Không đổi lockfile dựa vào advisory bị withdrawn hoặc PR chưa phát hành.
[GitHub Advisory](https://github.com/advisories/GHSA-fc5q-39xc-vjpf) ·
[Upstream patch discussion](https://github.com/micromatch/picomatch/pull/235) ·
[Releases](https://github.com/micromatch/picomatch/releases).

Ponytail giữ pipeline hiện có và dùng PostgreSQL/Redis đang có. Graphify AST trả 262 file,
2.715 nodes và 7.460 edges. Agent Skills được dùng cho TDD, security, interface và review.
Superpowers engineering riêng không có, TokenEconomizer micro-skills đang tắt. Memory
ghi trong repository theo AGENTS.

[SHA256 cho bằng chứng chạy này](final-e2e-evidence/agent-hardening-2026-11-18/SHA256SUMS.txt).
