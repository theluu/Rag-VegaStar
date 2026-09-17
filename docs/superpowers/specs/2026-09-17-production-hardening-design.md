# Thiết kế: Guardrails, RAG, Harness đánh giá, Security, SEO/GEO, tối ưu backend

Ngày: 2026-09-17 · Xây trên hệ thống đã có (`2026-09-17-vessel-chatbot-design.md`).

## 1. Guardrails (`src/vessel_chat/guardrails/`)

| Lớp | Cơ chế | Hành vi |
|---|---|---|
| Đầu vào: độ dài | Pydantic `max_length` (đã có) | 422 |
| Đầu vào: prompt injection | Heuristic có trọng số (regex tiếng Việt + Anh: "ignore/bỏ qua … hướng dẫn", "system prompt", "bạn giờ là…", thẻ `<|im_start|>`, yêu cầu lộ key/env) | điểm ≥ `GUARDRAIL_INJECTION_BLOCK_SCORE` → chặn, trả lời từ chối cố định (không gọi LLM); điểm thấp hơn nhưng > 0 → cho qua kèm nhắc nhở hệ thống |
| Đầu vào: kiểm duyệt | OpenAI Moderation (`GUARDRAIL_MODERATION_MODEL`), bật bằng `GUARDRAIL_MODERATION_ENABLED`; lỗi API → `GUARDRAIL_MODERATION_FAIL_OPEN` | bị gắn cờ → chặn |
| Tool | Pool DB riêng `default_transaction_read_only=on`, `statement_timeout`, giới hạn dòng, validate tham số | lỗi → `{"error"}` |
| Đầu ra: bám dữ liệu | Trích mọi số (≥ 2 chữ số hoặc có phần thập phân, bỏ ngày/giờ) trong câu trả lời, so với số trong kết quả tool + câu hỏi + ngữ cảnh bộ nhớ (dung sai làm tròn) | số không có nguồn → sự kiện `guardrail` loại `ungrounded_numbers` + metric (không chặn) |
| Đầu ra: rò rỉ | Câu trả lời chứa đoạn dài của system prompt hoặc chuỗi giống secret (`sk-…`, `postgresql://…`) | che bằng `[đã ẩn]`, sự kiện `guardrail` |

Sự kiện SSE mới: `guardrail {stage: input|output, action: block|warn|redact, kind, message}`. Tin nhắn bị chặn được lưu với `meta.guardrail`.

## 2. RAG kho tri thức (`knowledge/*.md`, `src/vessel_chat/rag/`)

- Tài liệu nghiệp vụ tự viết (tiếng Việt): trạng thái hành hải AIS, nhóm loại tàu, dark gap là gì và cách diễn giải, vai trò công ty, từ điển dữ liệu, đơn vị (hải lý, knot, DWT/GT), MMSI/IMO/callsign, giới hạn của hệ thống và cách dùng.
- Ingest (`scripts/ingest_knowledge.py`): tách theo tiêu đề `##`, gộp tới ~`RAG_CHUNK_MAX_CHARS`, nhúng, upsert vào `kb_chunks(id, source, section, content, content_hash, embedding vector, tsv tsvector)`; idempotent theo `content_hash`, xoá chunk không còn.
- Truy xuất lai: top-`RAG_CANDIDATES` theo vector (HNSW) + top theo `ts_rank` (`simple` config + `unaccent`) → Reciprocal Rank Fusion (k=60) → top-`RAG_TOP_K`, lọc `RAG_MIN_SCORE` trên cosine.
- Tool `search_knowledge(query)` → `[{source, section, text, score}]`; prompt yêu cầu trích dẫn `(nguồn: file › mục)` khi dùng.
- UI: bước tool hiển thị "Tra kho tri thức"; trích dẫn nằm trong câu trả lời.

## 3. Harness đánh giá (`evals/`)

- `evals/generate.py`: sinh ca kiểm thử từ DB theo mẫu (thông tin tàu, chủ sở hữu, vị trí tại thời điểm, quãng đường ngày, dark gap, công ty-vai trò), chọn tàu ngẫu nhiên có seed; đáp án chuẩn bằng SQL. Ghi `evals/cases.generated.yaml`.
- `evals/cases.static.yaml`: ca kiến thức (RAG), ca red-team (injection, ngoài phạm vi, yêu cầu lộ prompt/khoá, SQL injection trong tên tàu).
- `evals/run.py`: chạy qua API SSE; chấm:
  - `tool`: tool mong đợi có được gọi;
  - `facts`: các giá trị mong đợi xuất hiện (số có dung sai, tên không phân biệt hoa thường);
  - `grounded`: không có sự kiện `ungrounded_numbers`;
  - `refusal`: ca red-team bị chặn hoặc trả lời từ chối, không lộ prompt;
  - độ trễ, token, chi phí.
- Báo cáo `results/eval_report.md` + `results/eval_report.json`; `--min-pass-rate` → exit code ≠ 0 nếu dưới ngưỡng.

## 4. Security

- `API_KEYS` (danh sách, rỗng = tắt): header `X-API-Key` hoặc `Authorization: Bearer`; so sánh hằng thời gian; `/health`, `/docs` công khai.
- Rate limit token-bucket theo khoá API hoặc IP: `RATE_LIMIT_CHAT_PER_MINUTE`, `RATE_LIMIT_API_PER_MINUTE`; 429 + `Retry-After`. Bộ nhớ trong tiến trình (ghi chú Redis khi nhiều bản).
- Middleware: `X-Request-ID`, security headers (`X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, CSP `default-src 'none'` cho JSON), giới hạn kích thước body `MAX_REQUEST_BYTES`.
- Lỗi 500 trả thông điệp chung + request id; chi tiết chỉ ở log.
- Docker API chạy user không root; nginx thêm CSP (tiles/fonts), HSTS tuỳ chọn, ẩn phiên bản.
- `SECURITY.md`: mô hình đe doạ, biện pháp, việc cần làm khi lên production.

## 5. SEO/GEO (`frontend/`)

- `index.html`: title, description, canonical, Open Graph, Twitter card, theme-color, JSON-LD `WebApplication` + `FAQPage`, `<noscript>` + nội dung tĩnh mô tả sản phẩm (React thay thế khi chạy).
- `public/robots.txt`, `public/sitemap.xml`, `public/manifest.webmanifest`, `public/og-image.png` (1200×630), `public/llms.txt`, `public/llms-full.txt`.
- URL site cấu hình `VITE_SITE_URL`; plugin Vite nhỏ thay `%SITE_URL%` trong html/robots/sitemap/llms lúc build.

## 6. Tối ưu backend & quan sát

- Cache kết quả tool: LRU + TTL trong tiến trình (`TOOL_CACHE_TTL_SECONDS`, `TOOL_CACHE_MAX_ENTRIES`), khoá = tên + tham số chuẩn hoá (+ tàu đang bàn với `find_company_vessels`); không cache kết quả lỗi.
- `get_dark_gaps`: một truy vấn LATERAL thay cho 2 truy vấn/sự kiện.
- `GZipMiddleware` (≥ 1 KB); `/map-data/{id}`: `Cache-Control: private, max-age=86400, immutable` + `ETag`.
- `/metrics` (Prometheus): request theo route/status, độ trễ lượt chat (TTFT, tổng), gọi tool (tên, ok, thời gian, cache hit), token vào/ra, chi phí ước tính, guardrail theo loại.
- Log JSON một dòng mỗi lượt: request id, hội thoại, lượt, tool, độ trễ, token, chi phí.

## 7. Kiểm thử

Unit: injection detector, grounding checker, redaction, RAG chunker + hybrid search (embedder giả), cache, rate limiter, auth. Integration: chat bị chặn không gọi LLM, sự kiện guardrail, 401/429, header bảo mật, gzip, `/metrics`, tool pool chỉ đọc (INSERT thất bại).
