# ITLR–RAG

Nền tảng học CNTT tiếng Việt. Người học có thể tìm tài nguyên, hỏi đáp có trích dẫn,
xem lộ trình và theo dõi tiến độ. Express quản lý tài khoản và PostgreSQL. FastAPI
phục vụ tìm kiếm và hỏi đáp RAG.

**LOCAL READY · STAGING HOLD · PRODUCTION NO-GO**

[English](README.md) · [Kiến trúc](docs/ARCHITECTURE.md) · [Danh mục tài liệu](docs/README.md) · [Kết quả kiểm chứng](reports/REPOSITORY_CLEANUP.md)

## Bắt đầu nhanh (local)

Cần Docker Compose v2, hoặc Python 3.11+, Node.js 22 và PostgreSQL 16 nếu chạy trực tiếp.
Checkout mới cần chuẩn bị artifact đã qua probe, cache model embedding và catalog Web.
[Nạp dữ liệu](deploy/DEPLOY.md#nạp-dữ-liệu) · [Build, probe và activate](deploy/DEPLOY.md#build-probe-activate)

### Docker Compose

Từ thư mục gốc, tạo file cấu hình riêng và thay các placeholder trong template.

```bash
(umask 077; set -C; cat .env.docker.example > .env.docker)
docker compose --env-file .env.docker -f compose.local.yml config --quiet
```

Làm theo [hướng dẫn Compose](deploy/DEPLOY.md#docker-compose-local) để build image,
khởi động PostgreSQL, chạy migration và đồng bộ catalog trên database local. Khi
stack sẵn sàng, mở [giao diện Web](http://localhost:3000). Dùng Web `/ready` để kiểm
kết nối PostgreSQL và API `/health` trên cổng 8000 để xem fingerprint artifact đã nạp.

### Chạy trực tiếp

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
(cd web && npm ci)
```

Điền cấu hình từ các template [API](.env.example) và [Web](web/.env.example).
Kiểm tra database đích trước khi migrate hoặc sync. Hướng dẫn có lệnh khởi động API,
Web và cách dùng Ollama local. [Chạy API và Web](deploy/DEPLOY.md#chạy-api-và-web) · [Model local](deploy/LOCAL_MODELS.md)

## Phát triển và vận hành

- FAISS là mặc định. Qdrant Phase A bật theo cấu hình. Native hybrid chỉ dùng trong
  evaluator. Redis là tùy chọn cho quota, concurrency và cache truy hồi công khai.
  [Truy hồi và citation](docs/RAG.md) · [Qdrant và rollback](docs/architecture/QDRANT_MIGRATION.md)
- Chạy full suite trước khi bàn giao. Giữ nguyên qrels và test fixtures khi so sánh
  chất lượng truy hồi. [Kiểm thử](docs/TESTING.md) · [Đánh giá](docs/EVALUATION.md)
- Khi triển khai, kiểm tra trạng thái từng dịch vụ, xác nhận fingerprint sau reload,
  tập khôi phục vào môi trường cách ly. [Triển khai](docs/deployment/README.md) · [Monitoring và phục hồi](docs/operations/README.md)

## Giới hạn hiện tại

Single-tenant staging còn gate p95 generation 45 giây và human faithfulness độc lập.
Multi-tenant SaaS còn thiếu bằng chứng cô lập giữa các tổ chức. Phục hồi multi-host và
tải generation dài hạn chưa được xác nhận. [Release gates](reports/REPOSITORY_CLEANUP.md)
