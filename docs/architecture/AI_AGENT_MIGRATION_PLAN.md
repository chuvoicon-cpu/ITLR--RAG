# Kế hoạch thực thi theo cổng kiểm chứng

1. Chạy regression gốc từ HEAD sạch, ghi môi trường và giới hạn. Dùng AST Graphify và trace các đường API, Web, ingestion và deployment.
2. Tách truy vấn dense khỏi BM25/RRF. Giữ điều kiện filter, vị trí tie-break và ngưỡng hiện hành. Đưa Qdrant dense exact vào qua cấu hình opt-in và pin collection từ artifact version. Kiểm thử cùng vector, cùng qrels và cùng chế độ reranker.
3. Diễn tập upload/probe bên ngoài request path. Publish alias sau kiểm số lượng, metadata, vector và version. Rollback dùng collection cũ đã pin và bản FAISS đã giữ. Không cập nhật collection đang phục vụ.
4. Sau phép so sánh frozen A, chạy B như thực nghiệm native dense/sparse với cùng qrels. So sánh theo case, tập tiếng Việt, negative và identifier trước khi cân nhắc đổi mặc định.
5. Giữ Web là authority của principal và PostgreSQL là nguồn bền vững. Runtime agent trước hết có công cụ read-only. Công cụ write/handoff cần authorization, idempotency bền vững và luồng phê duyệt có chủ sở hữu.
6. Cache exact chỉ cho dữ liệu công khai/deterministic đủ điều kiện. Cache retrieval namespace theo version và quyền. Giới hạn phân tán fail closed nếu Redis chịu trách nhiệm quota. Metadata provider thiếu được lưu `null`.
7. Chứng minh persistence, restart, rollback và staging e2e rồi tăng tải dần. Điều kiện production gồm SLO, human faithfulness, backup restore, security và ngân sách đã có số đo.

Gate A yêu cầu thứ tự chunk và quyết định empty/nonempty trùng trên bộ frozen ở cấu hình so sánh. Sai khác số học float32 được ghi kèm nhưng không nới threshold. Dừng promotion khi bất kỳ gate nào thất bại. Công việc chuẩn bị cho các phase độc lập có thể tiếp tục.
