# Redis và provider prompt cache

L1 cache response của search deterministic tại những cụm từ chính xác nằm trong glossary công khai. L2 cache vector E5 và kết quả chunk retrieval khi query đủ điều kiện và reranker tắt cho kết quả. Đường cache chỉ được cấu hình khi API nạp Qdrant corpus đã probe. Tìm kiếm cá nhân, user progress, học liệu riêng, conversation, prompt, history và write actions nằm ngoài cache. Không có tenant thật trong schema hiện hành.

Key hash gồm namespace, scope public, policy version, collection fingerprint, model, epoch, layer và tham số retrieval/response. Dùng Redis TTL 300s. Tăng `ITLR_CACHE_EPOCH` trên các replica để invalidate chủ động. Phiên bản knowledge đổi tạo namespace mới. Redis lease có owner ngẫu nhiên, TTL 10s, và Lua publish/release nguyên tử. Requests chờ fill tối đa 2s. Khi Redis vẫn hoạt động và lease chưa kết thúc, request quá
hạn trả 503 với Retry-After ở search. Redis outage cho cache bypass. Lease cũ không ghi
đè fill mới vì Lua kiểm owner trước khi publish. [Redis cache-aside và lock](https://redis.io/docs/latest/develop/use-cases/cache-aside/java-lettuce/).

Bộ đếm rate limit nếu bật `ITLR_REDIS_RATE_LIMIT=1` dùng fixed window 60 giây theo deployment, endpoint và IP đã được socket/proxy xác định. Redis outage trả 503 cho quota. Provider quota toàn cục đếm mỗi lần gọi/retry và có thể giữ trước ngân sách theo UTF-8 bytes cộng trần output. Cấu hình `ITLR_LLM_MAX_RPM` / `ITLR_LLM_MAX_TPM` cho mỗi provider chung theo namespace. Đây là reservation, usage thực đến từ provider. [Redis atomic rate limiting](https://redis.io/docs/latest/develop/use-cases/rate-limiter/).

OpenAI và DeepSeek có native prompt cache. Prompt hiện hành đã đặt policy tĩnh trước evidence biến động, history và query. Transport đọc counters thật trong sync và stream. `cached_input_tokens` và `uncached_input_tokens` là `null` khi provider không trả breakdown. Ollama hiện không có breakdown đó. Metrics cung cấp cache metadata availability và token counts theo provider. `ITLR_LLM_PRICE_JSON` có thể định giá theo `provider/model` với keys `input`, `cached`, `output` tính bằng USD/triệu token. Giá hiện hành và tiết kiệm chỉ có số khi cấu hình bảng giá, response có counters và model khớp. Không có phép đo paid provider trong đợt này. [OpenAI Chat Completions prompt caching](https://developers.openai.com/cookbook/examples/prompt_caching101), [DeepSeek usage](https://api-docs.deepseek.com/api/create-chat-completion/).


Khi Web và API chia sẻ `ITLR_CHAT_PRINCIPAL_KEY`, Web ký ID đã xác thực, thời điểm và
đường dẫn sync/SSE. `ITLR_REQUIRE_WEB_CHAT=1` buộc chat có chữ ký còn hạn. Browser không
gửi user ID vào credential này. Quota signed chat theo user với mặc định 12 request/phút.
Search và chat standalone còn dùng socket IP. Schema hiện chưa có tenant membership.

API kết hợp slot local và lease ZSET toàn cluster qua Redis server time. Mỗi lease có
900s để thu hồi khi process chết. ASGI SSE có deadline 300s và hoàn slot khi stream kết
thúc hoặc client hủy. Sau Redis restart, trạng thái ephemeral có thể mất. Redis unavailable
chặn admission mới khi quota/cluster slot được bật.
