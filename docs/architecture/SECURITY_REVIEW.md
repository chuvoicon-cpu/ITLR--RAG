# Security review

| Boundary | Kiểm soát triển khai | Phạm vi kiểm chứng |
|---|---|---|
| Web browser → Express | JWT/CSRF hiện có, args strict, user ID của session, write xác nhận và idempotency PG | Unit và kiểm trực tiếp Compose cho request giả user, CSRF và hai tài khoản. |
| Retrieved evidence → model | Evidence-only path, Pydantic kiểm ownership, citation validation và refusal giữ nguyên | Test fixture đưa text instruction vào kết quả đọc. Human entailment và red-team độc lập còn thiếu. |
| Express → PostgreSQL | SQL parameterized, filter user ID, transaction và audit, timeout trên write | Plan/handoff concurrent replay và actor audit đã kiểm với PostgreSQL thật. |
| API → Qdrant | Reader key riêng, collection pin, filter version + approval, operator import chỉ vetted artifacts | Lifecycle test với real service và parity. Network overlay chỉ áp dụng môi trường nội bộ. |
| API → Redis | Dữ liệu public-only, key scope/version, quota fail closed | Shared fill và epoch isolation, fail-closed outage và Redis multi-process permit đã kiểm. |
| Gateway → provider | Explicit routing, timeout/backoff, key masking và usage metadata | Kết nối Qwen local thật và transport cancellation fixture đã kiểm. Paid provider cần quyền và credentials riêng. |

Tenant membership chưa có schema. Express và FastAPI từ chối tenant selector ở biên.
Lịch sử chat dùng một snapshot SQL cho kiểm owner và đọc message. Qdrant collection
và Redis cache chỉ chứa knowledge công khai. Reader/writer key và local env chỉ truyền
đến service cần dùng. [Staging readiness](../../reports/STAGING_READINESS.md).
