# ADR-014 · Pin collection Qdrant theo fingerprint artifact

Ngày 2026-11-18. Chấp nhận cho thử nghiệm local/staging.

Chọn adapter dense exact dùng cùng embedding/bộ phân hạng BM25 + RRF. Collection vật lý dựa trên SHA256 của artifact manifest, đổi alias nguyên tử sau frozen parity. Engine kiểm alias khi nạp và tiếp tục dùng tên vật lý cho vòng đời của nó. Nhờ vậy request đang chạy giữ kết hợp đúng giữa vector, metadata và labels trong khi rollout đổi pointer.

Native fusion cho recall cao hơn trong thử nghiệm nhưng trả kết quả ở bốn truy vấn negative trước đây rỗng. Duy trì chế độ B trong evaluator, giữ dense floor trong API. Vai trò writer tách khỏi API reader. Rủi ro còn lại là cluster control plane và app pointer không có transaction chung, cần rollout một writer có điều phối và giữ đường rollback FAISS. [Hướng dẫn migration](../architecture/QDRANT_MIGRATION.md).
