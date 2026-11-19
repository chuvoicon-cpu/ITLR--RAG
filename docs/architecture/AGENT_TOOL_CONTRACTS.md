# Hợp đồng công cụ agent

Web nhận POST `/api/agent/tools` với JWT cookie, CSRF và JSON `{"tool":"…","args":{…}}`. Mỗi yêu cầu chọn một công cụ từ Zod discriminated union. Output riêng tư có `Cache-Control: private, no-store` và `X-Request-ID`. API không nhận user ID hay tenant ID trong arguments.

| Tool | Arguments | Hành vi |
|---|---|---|
| `search_knowledge` | `query` | Kết quả corpus công khai, chunk ID và excerpt khi có chunk. Chatbot có tool nội bộ Pydantic tương ứng cho evidence. |
| `recommend_learning_resources` | `query` | Tìm catalog curated theo type Khóa học. Có thể trả rỗng nếu corpus chỉ có tài liệu cho truy vấn. |
| `get_user_progress` | `{}` | Đọc tối đa 100 enrollment của principal hiện hành. |
| `get_course_details` | `item_id` | Đọc catalog curated, 404 khi thiếu. |
| `create_learning_plan` | `track` | Xem trước dựa trên rule và PostgreSQL catalog/progress; trả plan cùng hash. |
| `save_learning_plan` | `track`, `preview_hash`, `idempotency_key`, `confirm: true` | Hành động trực tiếp từ người dùng. Recompute preview trong transaction; 409 nếu dữ liệu đã đổi hoặc reuse key cho nội dung khác. Key và audit theo user, replay trả cùng thời điểm lưu. |
| `handoff_to_human` | `confirm: true`, `detail`, `idempotency_key` | Ghi yêu cầu hỗ trợ vào PostgreSQL. 202 với receipt, 409 nếu cùng key của owner nhưng khác nội dung. |

Nhân viên có role `admin` được xác minh từ PostgreSQL có thể xem 50 vé pending ở
`GET /api/agent/handoffs` và resolve bằng `POST /api/agent/handoffs/:id/resolve`.
Lần resolve đầu tiên ghi actor, thời điểm và request ID. Replay đọc kết quả đã lưu.
Ticket chỉ chứa nội dung người dùng xác nhận gửi. Vận hành tiếp nhận dùng hàng đợi trong ứng dụng.

Gọi tool với user giả trong input trả 400. CSRF thiếu trả 403. Search tool có timeout upstream 15s và hủy fetch khi browser disconnect. PostgreSQL write dùng statement timeout; ghi thành công trước khi HTTP reply vẫn replay an toàn. Tool registry này nằm ngoài quyền điều khiển của model và không mở truy cập shell, file, SQL tùy ý hoặc network tùy ý.
