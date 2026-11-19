# ADR-015 · Staging đơn tenant và quyền bật cloud

Ngày 2026-11-18. Áp dụng cho staging với một phạm vi dữ liệu.

Express xác thực JWT và trạng thái user từ PostgreSQL. Đọc lịch sử dùng một câu SQL
ràng buộc owner và tải message trong cùng snapshot. Ghi chat vẫn khóa conversation và
thực hiện trong transaction. Agent knowledge dùng catalog công khai. Các tool riêng tư
và handoff chạy ở Web theo user hoặc role đã xác minh. Chữ ký Web chuyển user đến
FastAPI cho admission. Chữ ký không cấp quyền đọc cơ sở dữ liệu.

Schema chưa chứa tenant membership. Web và FastAPI từ chối tenant selector được
hỗ trợ nhận diện ở biên HTTP. Qdrant giữ collection công khai chỉ đọc trên đường API,
Redis giữ cache công khai và quota user. Phân quyền giữa hai tenant thực tế vẫn BLOCKED.

Overlay agent mặc định provider `none`. Bật DeepSeek/OpenAI ở staging cần provider rõ
ràng, quyền vận hành `ITLR_CLOUD_AUTHORIZED=1`, Redis, RPM/TPM dương và credential
từ environment hoặc file mount. Giữ project-level billing budget và giới hạn thời lượng
benchmark bên provider/outside gateway. RPM/TPM là giới hạn lưu lượng. Bằng chứng billing
đến từ hóa đơn provider, kết hợp usage metadata và thời gian quan sát thực tế.

[Staging gates](../../reports/STAGING_READINESS.md).
