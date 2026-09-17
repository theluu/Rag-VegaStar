# Bảo mật

Tài liệu mô tả mô hình đe doạ, các biện pháp đã triển khai và việc cần làm trước khi đưa lên production.

## Mô hình đe doạ

| Tài sản | Mối đe doạ | Biện pháp |
|---|---|---|
| Dữ liệu tàu trong DB | LLM hoặc người dùng sửa/xoá dữ liệu; SQL injection | LLM không viết SQL: chỉ gọi 9 tool có tham số (`$n` của asyncpg), các lựa chọn như `order_by` ánh xạ sang đoạn SQL cố định. Tool và route dữ liệu dùng **pool chỉ đọc** (`default_transaction_read_only=on`), có `statement_timeout` và giới hạn số dòng. Có test xác nhận lệnh `DELETE` qua pool này thất bại; ca red-team `DROP TABLE` trong tên tàu không gây lỗi và dữ liệu còn nguyên. |
| System prompt, cấu hình, khoá | Prompt injection, jailbreak, yêu cầu lộ `OPENAI_API_KEY` / `DATABASE_URL` | **Guardrail đầu vào:** heuristic có trọng số (tiếng Việt và tiếng Anh) chặn trước khi gọi LLM. **Guardrail đầu ra:** lọc luồng token, che chuỗi giống secret, cắt nội dung lặp lại system prompt. Mọi quyết định được ghi vào `meta.guardrail` và metrics. |
| Độ tin cậy câu trả lời | Mô hình bịa số liệu; người dùng dán "kết quả tool" giả | Mọi câu trả lời có chứng cứ `[E#]`. Hệ thống đối chiếu từng con số và mã chứng cứ với dữ liệu đã truy vấn. Khi phát hiện dữ liệu dán giả, lần gọi đầu bị buộc `tool_choice=required` để lấy dữ liệu thật. Harness có ca red-team cho tình huống này. |
| Nội dung độc hại | Lạm dụng chatbot cho nội dung vi phạm | OpenAI Moderation (bật/tắt được; chọn fail-open hoặc fail-closed) và quy tắc phạm vi trong prompt. |
| Dịch vụ và chi phí | Spam, DoS, đốt token | Rate limit token-bucket theo API key hoặc IP (chat và API riêng), giới hạn body 64 KB, giới hạn độ dài tin nhắn, số vòng tool tối đa, timeout LLM và SQL, cache kết quả tool. |
| Hội thoại của người dùng | Truy cập trái phép | API key tuỳ chọn (`API_KEYS`, so sánh hằng thời gian qua `X-API-Key` hoặc `Authorization: Bearer`). Mọi truy vấn hội thoại và bộ nhớ đều lọc theo `conversation_id`. |
| Trình duyệt người dùng | XSS qua nội dung LLM, clickjacking | React escape toàn bộ nội dung; Markdown không cho phép HTML thô; popup bản đồ escape dữ liệu. nginx gửi CSP chặt chẽ (`script-src 'self'`, `frame-ancestors 'none'`, chỉ cho kết nối tới API và máy chủ bản đồ), cùng `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`. API trả `Content-Security-Policy: default-src 'none'`. |
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
- `VITE_API_KEY` nằm trong bundle của trình duyệt, nên chỉ phù hợp cho demo nội bộ. Production cần xác thực người dùng (OIDC) và phân quyền theo hội thoại.
- Hiện chưa có đa người thuê (multi-tenant): mọi client hợp lệ đều thấy mọi hội thoại.

## Việc cần làm trước khi lên production

- [ ] Bật `API_KEYS` hoặc đặt API sau gateway có xác thực; phân quyền hội thoại theo người dùng.
- [ ] Đặt `TRUST_PROXY_HEADERS=true` chỉ khi đứng sau reverse proxy tin cậy; bật TLS và HSTS ở proxy.
- [ ] Chặn `/metrics` và `/docs` khỏi Internet.
- [ ] Tạo role Postgres riêng chỉ có quyền `SELECT` cho pool tool (hiện dùng cơ chế read-only ở mức phiên); đổi mật khẩu mặc định; bật sao lưu.
- [ ] Rate limit và cache dùng Redis; đặt giới hạn chi tiêu và cảnh báo chi phí trên tài khoản OpenAI.
- [ ] Quét phụ thuộc định kỳ (`pip-audit`, `npm audit`) và quét image (Trivy).
- [ ] Chạy `evals/run.py` trong CI khi đổi prompt hoặc model; chặn merge nếu tỉ lệ đạt dưới ngưỡng.

## Báo cáo lỗ hổng

Vui lòng gửi email cho chủ repository (không mở issue công khai), kèm mô tả, các bước tái hiện và mức ảnh hưởng.
