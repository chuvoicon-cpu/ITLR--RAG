# Benchmark hiệu năng agent platform

Đo 2026-11-18 trên một Docker host CPU, E5-base, 118 nguồn và 1.576 chunks. CrossEncoder
tắt, generation chạy template/extractive, không có provider trả phí. Mẫu ngắn dùng để so
sánh trong cùng môi trường.

## Retrieval core

Cùng 45 query vector đã encode. Đo vòng tìm kiếm trong process FAISS hoặc qua Qdrant
loopback, gồm BM25/RRF ở phase A. Serial FAISS p50/p95/p99 là **1,75/2,69/3,12 ms**.
Serial Qdrant A **4,62/10,63/45,71 ms**. Lấy mẫu một lượt cho mỗi mức concurrency, không
trộn latency encode query. [Raw core benchmark](final-e2e-evidence/agent-platform-2026-11-18/qdrant-parity.json).

## HTTP Compose

23 truy vấn không nhằm hit exact cache ở mỗi mức. Đo elapsed client qua HTTP, gồm
embedding và response serialization, cùng một API replica. Peak active từ phía client.

| Concurrent | RPS | p50 ms | p95 ms | p99 ms | HTTP 200 | Timeout |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 7,72 | 125,58 | 156,93 | 161,66 | 23/23 | 0 |
| 2 | 10,77 | 178,28 | 229,85 | 237,05 | 23/23 | 0 |
| 4 | 11,09 | 361,88 | 440,70 | 505,44 | 23/23 | 0 |
| 8 | 11,71 | 640,31 | 807,17 | 848,90 | 23/23 | 0 |

15 request lặp từ glossary `Docker` có latency p50/p95/p99 **6,01/7,54/7,81 ms**.
Prometheus ở cả phiên smoke và benchmark ghi **21 L1 hits và 1 miss**. Tỷ lệ này chỉ
mô tả một workload lặp. Smoke riêng sau recreate ghi một miss và một hit cho từng layer embedding và retrieval. [HTTP evidence](final-e2e-evidence/agent-platform-2026-11-18/http-benchmark.json), [cache metrics](final-e2e-evidence/agent-platform-2026-11-18/cache-metrics.txt).

20 SSE template/extractive có TTFT p50/p95/p99 **221/329/494 ms**. Đây là frame text ứng
dụng. Cost/request, token latency, Qdrant/Redis/PG breakdown dưới tải và invalidation rate
production là `null`. Snapshot resource sau bài tải cho API 1,186 GiB, Qdrant 40,94 MiB,
Redis 5,83 MiB, PostgreSQL 33,32 MiB và Web 48,05 MiB. CPU của snapshot là tức thời sau
bài tải. [Resource snapshot](final-e2e-evidence/agent-platform-2026-11-18/compose-resource-snapshot.txt).
