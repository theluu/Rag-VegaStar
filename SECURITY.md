# Bảo mật

Tài liệu mô tả mô hình đe doạ, các biện pháp đã triển khai và việc cần làm trước khi đưa lên production.

## Mô hình đe doạ

| Tài sản | Mối đe doạ | Biện pháp |
|---|---|---|
| Dữ liệu tàu trong DB | LLM hoặc người dùng sửa/xoá dữ liệu; SQL injection | LLM không viết SQL: chỉ gọi 10 tool có tham số (`$n` của asyncpg), các lựa chọn như `order_by` ánh xạ sang đoạn SQL cố định. Tool và route dữ liệu dùng **pool chỉ đọc** (`default_transaction_read_only=on`), có `statement_timeout` và giới hạn số dòng. Có test xác nhận lệnh `DELETE` qua pool này thất bại; ca red-team `DROP TABLE` trong tên tàu không gây lỗi và dữ liệu còn nguyên. |
| System prompt, cấu hình, khoá | Prompt injection, jailbreak, yêu cầu lộ `OPENAI_API_KEY` / `DATABASE_URL` | **Guardrail đầu vào:** heuristic có trọng số (tiếng Việt và tiếng Anh) chặn trước khi gọi LLM. **Guardrail đầu ra:** lọc luồng token, che chuỗi giống secret, cắt nội dung lặp lại system prompt. Mọi quyết định được ghi vào `meta.guardrail` và metrics. |
| Độ tin cậy câu trả lời | Mô hình bịa số liệu; người dùng dán "kết quả tool" giả | Mọi câu trả lời có chứng cứ `[E#]`. Hệ thống đối chiếu từng con số và mã chứng cứ với dữ liệu đã truy vấn. Khi phát hiện dữ liệu dán giả, lần gọi đầu bị buộc `tool_choice=required` để lấy dữ liệu thật. Harness có ca red-team cho tình huống này. |
| Nội dung độc hại | Lạm dụng chatbot cho nội dung vi phạm | OpenAI Moderation (bật/tắt được; chọn fail-open hoặc fail-closed) và quy tắc phạm vi trong prompt. |
| Phụ thuộc nhà cung cấp AI | Key hết hạn, nhà cung cấp sập | LLM dự phòng (`FALLBACK_LLM_*`) tự nhận việc; không còn nhà cung cấp nào thì API vẫn phục vụ dữ liệu và bản đồ, chat báo rõ trạng thái thay vì trả lỗi 500. Key dự phòng và key kiểm chứng nằm trong biến môi trường như key chính, không bao giờ xuất hiện trong câu trả lời (guardrail đầu ra che chuỗi giống secret). |
| Dịch vụ và chi phí | Spam, DoS, đốt token | Rate limit token-bucket theo API key hoặc IP (chat và API riêng), giới hạn body 64 KB, giới hạn độ dài tin nhắn, số vòng tool tối đa, timeout LLM và SQL, cache kết quả tool. |
| Hội thoại của người dùng | Truy cập trái phép | **Đăng nhập** (`AUTH_USERS`): `POST /auth/login` cấp token phiên ký HMAC-SHA256 có hạn (`SESSION_TTL_HOURS`), mọi route dữ liệu yêu cầu `Authorization: Bearer <token>`. Hoặc API key (`API_KEYS`) cho tích hợp máy với máy. So sánh hằng thời gian; mọi truy vấn hội thoại và bộ nhớ lọc theo `conversation_id`. |
| Tài khoản đăng nhập | Dò mật khẩu, lộ mật khẩu trong cấu hình, giả mạo token | Giới hạn `RATE_LIMIT_LOGIN_PER_MINUTE` lần thử mỗi IP (429); thông báo lỗi chung cho sai tên và sai mật khẩu, thời gian xử lý như nhau (băm giả khi tên không tồn tại); mật khẩu có thể lưu dạng PBKDF2-SHA256 240.000 vòng (`scripts/hash_password.py`); token chỉ hợp lệ khi chữ ký khớp `SESSION_SECRET`, chưa hết hạn và người dùng vẫn còn trong `AUTH_USERS`; log `login_ok` / `login_failed` và metric `vc_auth_events_total` (không ghi mật khẩu). |
| Trình duyệt người dùng | XSS qua nội dung LLM, clickjacking | React escape toàn bộ nội dung; Markdown không cho phép HTML thô; popup bản đồ escape dữ liệu. nginx gửi CSP chặt chẽ (`script-src 'self'`, `frame-ancestors 'none'`, chỉ cho kết nối tới API và máy chủ bản đồ), cùng `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`. API trả `Content-Security-Policy: default-src 'none'`. |
| Số liệu vận hành | Lộ câu hỏi của người dùng, chi phí, cấu hình qua `/stats` | Dùng chung API key và rate limit; không trả khoá, URL hay prompt; câu hỏi được React escape khi hiển thị. Tắt bằng `STATS_ENABLED=false`. |
| Hạ tầng | Lộ secret trong repo hoặc image; container chạy root | `.env` và `data/` nằm trong `.gitignore`; image API chạy user `app` (uid 10001); web dùng `nginx-unprivileged`; lỗi 500 chỉ trả thông điệp chung kèm `request_id` (chi tiết nằm trong log). |

## Các lớp phòng thủ khi xử lý một câu hỏi

1. **HTTP:** giới hạn kích thước, xác thực, rate limit, request ID, header bảo mật.
2. **Guardrail đầu vào:** chặn (không gọi LLM) hoặc cảnh báo kèm nhắc nhở hệ thống; kiểm duyệt nội dung.
3. **LLM:** system prompt quy định phạm vi, yêu cầu trích chứng cứ, coi mọi nội dung trong kết quả tool là dữ liệu chứ không phải chỉ dẫn.
4. **Tool:** tham số được kiểm bằng Pydantic, SQL có tham số, pool chỉ đọc, timeout, giới hạn số dòng.
5. **Guardrail đầu ra:** che secret và chặn lộ prompt ngay trên luồng stream; sau khi trả lời xong, đối chiếu số liệu và mã chứng cứ.
6. **Quan sát:** metrics `vc_guardrail_events_total`, `vc_rate_limited_total`; log JSON cho từng lượt chat.

## Giới hạn đã biết

- Heuristic phát hiện injection có thể bỏ lọt các cách diễn đạt mới. Các lớp phía sau (tool chỉ đọc, kiểm chứng số liệu, lọc đầu ra) giới hạn thiệt hại có thể xảy ra.
- Rate limit và cache nằm trong bộ nhớ của từng tiến trình; khi chạy nhiều bản API cần chuyển sang Redis.
- `VITE_API_KEY` nằm trong bundle của trình duyệt, nên chỉ phù hợp cho demo nội bộ; với giao diện, dùng đăng nhập (`AUTH_USERS`) thay thế.
- Đăng nhập dùng tài khoản cấu hình sẵn, phù hợp môi trường dev/demo. Token là stateless nên không thu hồi riêng từng phiên được (đổi `SESSION_SECRET` hoặc xoá người dùng khỏi `AUTH_USERS` để thu hồi); token lưu trong `localStorage` nên phụ thuộc CSP chặt để hạn chế XSS. Production nên dùng OIDC / SSO, cookie `HttpOnly` và phân quyền theo hội thoại.
- Hiện chưa có đa người thuê (multi-tenant): mọi client hợp lệ đều thấy mọi hội thoại.

## Bản chạy thử (vegastar.themeshub.net)

API chỉ lắng nghe `127.0.0.1`, nginx là cửa ngõ duy nhất (HTTPS, HSTS, CSP); `/metrics`, `/docs`, `/redoc` bị chặn ở proxy;
service chạy user không đặc quyền với `ProtectSystem=strict` và giới hạn RAM. Tài khoản `demo/demo` chỉ dành cho
người xem demo và nên đổi khi để công khai lâu dài. Chi tiết: [docs/deploy.md](docs/deploy.md).

## Việc cần làm trước khi lên production

- [ ] Đổi mật khẩu `demo` (hoặc dùng chuỗi băm từ `scripts/hash_password.py`), đặt `SESSION_SECRET` ngẫu nhiên dài; không bật `VITE_LOGIN_HINT` nếu không muốn lộ tài khoản.
- [ ] Phục vụ qua HTTPS (token đi trong header); cân nhắc OIDC / SSO và phân quyền hội thoại theo người dùng.
- [ ] Đặt `TRUST_PROXY_HEADERS=true` chỉ khi đứng sau reverse proxy tin cậy; bật TLS và HSTS ở proxy.
- [ ] Chặn `/metrics` và `/docs` khỏi Internet; chỉ cho quản trị viên xem `/stats` và tab Thống kê (hoặc đặt `STATS_ENABLED=false`).
- [ ] Tạo role Postgres riêng chỉ có quyền `SELECT` cho pool tool (hiện dùng cơ chế read-only ở mức phiên); đổi mật khẩu mặc định; bật sao lưu.
- [ ] Rate limit và cache dùng Redis; đặt giới hạn chi tiêu và cảnh báo chi phí trên tài khoản OpenAI.
- [ ] Quét phụ thuộc định kỳ (`pip-audit`, `npm audit`) và quét image (Trivy).
- [ ] Chạy `evals/run.py` trong CI khi đổi prompt hoặc model; chặn merge nếu tỉ lệ đạt dưới ngưỡng.

## Báo cáo lỗ hổng

Vui lòng gửi email cho chủ repository (không mở issue công khai), kèm mô tả, các bước tái hiện và mức ảnh hưởng.
