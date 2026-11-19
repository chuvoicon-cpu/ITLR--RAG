# Đánh giá agent và retrieval

Đo ngày 2026-11-18 trên **118 tài liệu curated**, **1.576 chunks** E5-base 768d. Model
download ở revision `d128750597153bb5987e10b1c3493a34e5a4502a`. Phase A và phase B dùng
cùng vector truy vấn, bộ 45 query frozen từ release + engineering confirmation, gồm VI/EN,
noise, multi-hop và 8 negative. Nhãn là engineer-authored. Threshold phase A giữ 84 và
CrossEncoder tắt trong phép so sánh.

| Retrieval | Recall@5 | MRR@5 | nDCG@5 | Negative trả rỗng |
|---|---:|---:|---:|---:|
| FAISS + BM25/RRF | 82,43% | 65,50% | 68,79% | 8/8 |
| Qdrant dense + BM25/RRF | 82,43% | 65,50% | 68,79% | 8/8 |
| Qdrant native độc lập | 97,30% | 85,90% | 88,54% | 4/8 |

Phase A khớp thứ tự chunk ở 45/45 case. Phase B đổi 41/45 thứ hạng và có thêm kết quả ở
bốn negative; thí nghiệm tiếp tục nằm ngoài serving. Exact chunk ID, payload filter, update
và delete đã kiểm riêng với Qdrant thật. [Raw parity](final-e2e-evidence/agent-platform-2026-11-18/qdrant-parity.json).

## Chat và security

HTTP SSE template/extractive trên 20 câu blind cố định gồm 12 positive và 8 negative.
Judged item xuất hiện trong sources ở 12/12 positive. 11/12 positive trả extractive với
citation status valid, 1 trả template. Rule-based refusal detector nhận 2/8 negative;
3 negative trả extractive và 3 template khác không khớp luật refusal. Citation status valid
kiểm ID và binding. `human_faithfulness`, semantic groundedness và hallucination rate ở mức
claim vẫn `null`. [Raw case outcomes](final-e2e-evidence/agent-platform-2026-11-18/http-benchmark.json).

Test đưa instruction vào excerpt, kiểm dữ liệu giữ nguyên và quyền tool do server kiểm soát.
Kiểm PostgreSQL trực tiếp ở Compose cho scope user, JWT/CSRF và lưu kế hoạch đồng thời.
Test SSE qua transport fixture giữ đặc tính cancel trước/sau delta và release chat permit.
