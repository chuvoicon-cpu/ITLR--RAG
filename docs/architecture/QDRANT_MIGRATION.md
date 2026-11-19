# Migration FAISS sang Qdrant

## Phase A và phase B

Phase A triển khai `ITLR_VECTOR_BACKEND=qdrant` trong đường API hiện có. Store dùng vector tên `dense`, E5-base 768 chiều đã chuẩn hóa và `Dot` exact để tương ứng FAISS IndexFlatIP. BM25, RRF, threshold 84 và tie-break theo thứ tự artifact chạy trong `ChunkIndex`. FAISS tiếp tục là mặc định trong các cấu hình cũ. [Qdrant named vectors](https://qdrant.tech/documentation/manage-data/vectors/).

Phase B chạy qua `--native` sau parity A. Collection thí nghiệm có vector BM25 sparse, dense và sparse prefetch độc lập, RRF trong Qdrant. Trên 45 case, 41 thứ hạng đổi, Recall@5 tăng từ 82,43% lên 97,30% và negative trả rỗng giảm từ 8/8 xuống 4/8. Cấu hình này ở trong evaluator. [Qdrant hybrid queries](https://qdrant.tech/documentation/search/hybrid-queries/).

## Vòng đời và khôi phục

1. Build real-only ở staging, chạy probe và giữ đầy đủ artifact FAISS. Snapshot curated 118 trang có provenance. Importer từ chối catalog có origin synthetic, license trống, hash không hợp lệ, ID trùng, ownership sai hoặc vector không đúng E5-base.
2. Đặt `ITLR_QDRANT_URL`, `ITLR_QDRANT_WRITE_KEY` cho thao tác vận hành và `ITLR_QDRANT_API_KEY` cho đọc. `ITLR_QDRANT_NAMESPACE` phân biệt deployment. Collection vật lý có tên namespace và SHA256 manifest. Điểm ID tương ứng ordinal trong artifact. Payload chứa item/chunk ID, origin, source ID, language, license, document/chunk hash, approval state và version. Exact ID dùng filter keyword đã index. Tenant field sẽ cần principal đáng tin cậy khi có tenant thật.
3. Stage và so sánh ngoài request path. Verify đối chiếu count, schema, quyền sở hữu, payload và float32 từng vector. Tác vụ stage lặp trên bản hoàn chỉnh sẽ đọc lại và kiểm chứng. Nếu upload dừng giữa chừng, giữ collection lỗi ngoài alias và build revision mới. Một writer điều phối việc promote/rollback alias. [Qdrant payload](https://qdrant.tech/documentation/manage-data/payload/).
4. `promote --parity-report` kiểm fingerprint, corpus size, hash frozen qrels và parity theo case trước khi đổi alias nguyên tử. Sau đó đổi pointer phía artifacts bằng workflow hiện có và gọi reload. Engine chỉ nạp khi alias khớp pointer rồi pin collection vật lý. Request đang xử lý giữ version cũ. Replica đang chạy cần được rollout/reload có điều phối. [Qdrant collections and aliases](https://qdrant.tech/documentation/manage-data/collections/).
5. Lệnh `snapshot` tạo snapshot phía server. Chép snapshot, manifest, parity report và artifacts sang kho backup, lưu checksum và thử restore vào Qdrant cô lập. Rollback gồm promote bản cũ bằng report tương ứng, phục hồi pointer và reload. Đường khôi phục khác là dùng FAISS với artifacts đã kiểm chứng rồi restart. Update/delete dữ liệu thực được công bố qua revision mới. Các thao tác upsert/delete trực tiếp dùng cho staging.

```bash
python -m itlr.retrieval.qdrant_artifacts stage --artifacts /path/to/version
python -m eval.eval_qdrant_migration --artifacts /path/to/version --out /tmp/parity.json
python -m itlr.retrieval.qdrant_artifacts promote --artifacts /path/to/version --parity-report /tmp/parity.json
python -m itlr.retrieval.qdrant_artifacts snapshot --artifacts /path/to/version
```

Qdrant reader chỉ cần read-only key. Stage/probe là gate kỹ thuật và chất lượng. Rollback alias và persistence đã được thử. Snapshot fixture đã restore sang collection
cô lập và kiểm lại vector/payload. Khôi phục toàn bộ revision production theo quy trình
backup lưu trữ từ xa vẫn là gate phát hành. [Snapshot upload API](https://api.qdrant.tech/v-1-16-x/api-reference/snapshots/recover-from-uploaded-snapshot), [release readiness](../../reports/RELEASE_READINESS.md).


### Thử nghiệm phase B có dense floor chung

Giữ min_pct 84. Tính tập ID eligible từ dense exact rồi áp `has_id` trước khi cắt ứng viên
ở cả dense và sparse. Trên bộ frozen, 8/8 negative trả rỗng, Recall@5 bằng Phase A và
MRR@5 tăng. Human-reviewed cases và promotion còn mở. [Phân tích từng negative](../../reports/AGENT_HARDENING_2026-11-18.md).
