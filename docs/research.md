# Nghiên cứu và lựa chọn công nghệ

Mục tiêu: chatbot trả lời **đúng số liệu** trên dữ liệu có cấu trúc (AIS, đăng kiểm, chủ sở hữu), stream theo token, nhớ được hội thoại dài, và vẽ được bản đồ. Vì vậy các tiêu chí đặt theo thứ tự ưu tiên: (1) khả năng gọi tool ổn định; (2) độ trễ và chi phí; (3) vận hành đơn giản để người chấm chạy lại được; (4) giải thích được từng phần.

## 1. LLM

| Lựa chọn | Tool calling | Tiếng Việt | Độ trễ / chi phí | Nhận xét |
|---|---|---|---|---|
| **OpenAI gpt-4o-mini** (đã chọn) | Tốt, hỗ trợ gọi nhiều tool song song, streaming tool call | Tốt | Nhanh; 0,15 / 0,60 USD cho 1 triệu token vào/ra | Đủ tốt cho việc định tuyến tới 8 tool có mô tả rõ; rẻ nên chạy kịch bản nhiều lần được. Đã có sẵn key. |
| GPT-4o / GPT-4.1 | Rất tốt | Rất tốt | Đắt hơn khoảng 15 lần | Nên dùng nếu cần suy luận nhiều bước hoặc cần truyền đạt đủ mọi cảnh báo. Đổi chỉ bằng `LLM_MODEL`. |
| Claude (Anthropic), Gemini | Rất tốt | Tốt | Tương đương | Cần viết thêm một lớp `LLMClient`; kiến trúc đã tách sẵn giao diện. |
| Model mở (Qwen2.5-7B/14B, Llama 3.1 qua Ollama/vLLM) | Khá; dễ sinh JSON sai hoặc gọi sai tool | Qwen khá tốt | Không tốn phí API, nhưng cần GPU | Dùng được qua `OPENAI_BASE_URL` (API tương thích OpenAI). Cần prompt chặt hơn và kiểm tra tham số kỹ hơn (tầng tool đã có validation bằng Pydantic). |

**Quyết định:** dùng `gpt-4o-mini`, nhiệt độ 0,1. Tên model, URL và timeout đều cấu hình được. Điểm yếu đã thấy khi chạy kịch bản: đôi lúc bỏ sót cảnh báo hoặc giữ nhầm bộ lọc ở câu nối tiếp. Cách khắc phục đã áp dụng là để tool sinh sẵn `explanation` / `coverage_warnings` từ dữ liệu và bổ sung quy tắc về phạm vi câu nối tiếp. Sau khi sửa, cả hai lỗi đều không còn xuất hiện trong transcript.

## 2. Embedding

| Lựa chọn | Số chiều | Tiếng Việt | Ghi chú |
|---|---|---|---|
| **text-embedding-3-small** (đã chọn) | 1536 (có thể giảm) | Tốt | 0,02 USD / 1 triệu token; dùng chung key; hỗ trợ tham số `dimensions` |
| text-embedding-3-large | 3072 | Tốt hơn | Đắt gấp 6,5 lần; không cần thiết khi chỉ tìm trong một hội thoại |
| bge-m3, multilingual-e5 (tự host) | 1024 | Tốt | Không tốn phí API nhưng cần thêm service/GPU |

Nội dung cần nhúng là các lượt hội thoại ngắn, chứa nhiều mã và tên riêng (HS-2026-117, MSC MANYA). Kết quả thực tế: câu hỏi "Hồ sơ tôi nhắc từ đầu…" truy xuất đúng lượt 1 với cosine 0,585, cao hơn hẳn các lượt khác (≤ 0,41). `EMBEDDING_MODEL` và `EMBEDDING_DIM` đều cấu hình được.

## 3. Vector DB

| Lựa chọn | Ưu điểm | Nhược điểm |
|---|---|---|
| **pgvector trong cùng PostgreSQL** (đã chọn) | Một container duy nhất; transaction và xoá cascade cùng hội thoại; lọc theo `conversation_id` bằng SQL thường; sao lưu chung | Không phải engine chuyên dụng; ANN kèm bộ lọc cần chú ý |
| Qdrant | Lọc theo payload rất tốt, hiệu năng cao | Thêm một service phải vận hành và đồng bộ khi xoá hội thoại |
| Chroma | Dễ dùng khi làm prototype | Kém phù hợp chạy nhiều tiến trình / production |
| Milvus | Quy mô rất lớn | Quá nặng cho bài toán này |

Truy xuất luôn nằm trong phạm vi một hội thoại, nên pgvector với quét chính xác trên tập đã lọc vừa đúng vừa đủ nhanh (xem [architecture.md §3](architecture.md#3-thiết-kế-bộ-nhớ)). Dữ liệu tàu cũng nằm trong Postgres (PostGIS, pg_trgm), nên cả hệ thống chỉ cần một database.

## 4. Framework

| Lựa chọn | Nhận xét |
|---|---|
| **Tự viết vòng lặp tool trên OpenAI SDK + FastAPI** (đã chọn) | Khoảng 150 dòng (`chat/service.py`). Kiểm soát trọn vẹn: sự kiện SSE có kiểu, GeoJSON đi thẳng tới client (không qua model), lưu tin nhắn đúng cặp `tool_calls` ↔ `tool`, xử lý huỷ và lỗi. Dễ giải thích và dễ test bằng LLM giả. |
| LangChain / LangGraph | Có sẵn agent, checkpointer và bộ nhớ. Tuy nhiên `astream_events` khó ép theo đúng định dạng sự kiện đề yêu cầu; muốn tách dữ liệu bản đồ khỏi model và bộ nhớ kết hợp theo ý mình thì vẫn phải viết node riêng, lại thêm một lớp trừu tượng phải giải thích. |
| LlamaIndex | Mạnh về RAG trên tài liệu; bài toán này là truy vấn dữ liệu có cấu trúc qua tool, nên ít lợi ích. |
| Text-to-SQL (LangChain SQL agent, Vanna) | Linh hoạt, nhưng model nhỏ dễ viết SQL sai với dữ liệu nhiễu (tên biến thể, loại tàu tiếng Anh, khe dữ liệu), và phải thêm lớp kiểm duyệt câu lệnh. Tool có tham số cho kết quả ổn định và kiểm thử được. |

Các thư viện khác: **FastAPI** (async, OpenAPI tự sinh), **sse-starlette** (SSE có ping, xử lý ngắt kết nối), **asyncpg** (nhanh, COPY dạng binary, tham số `$n`), **pydantic-settings** (cấu hình). Frontend dùng **React + Vite**, bản đồ dùng **MapLibre GL** (WebGL, vẽ mượt hàng chục nghìn điểm, không cần key; bản đồ nền từ OpenFreeMap).

## 5. So sánh chiến lược bộ nhớ

| Chiến lược | Cách làm | Ưu | Nhược | Hợp với |
|---|---|---|---|---|
| Cửa sổ trượt | Giữ N lượt gần nhất | Đơn giản, chính xác cho câu nối tiếp gần | Quên hẳn thông tin cũ (kịch bản 3 sai) | Hội thoại ngắn |
| Tóm tắt | LLM nén các lượt cũ thành một đoạn | Giữ được ý chính, kích thước ổn định | Mất chi tiết, có thể "tóm sai"; tốn một lần gọi LLM mỗi lần nén | Hội thoại dài, ít chi tiết |
| Truy xuất vector | Nhúng từng lượt, tìm theo ngữ nghĩa | Nhớ được chi tiết cũ khi được hỏi đúng; mở rộng tốt | Phụ thuộc chất lượng truy vấn; câu hỏi dạng đại từ ("nó") khó tìm; có thể kéo về nội dung nhiễu | Tra cứu dữ kiện cũ |
| **Kết hợp** (đã chọn) | Trạng thái đối tượng + tóm tắt + vector + cửa sổ | Mỗi lớp bù cho điểm yếu của lớp khác | Phức tạp hơn; tốn thêm một lần nhúng mỗi lượt và một lần tóm tắt mỗi khi có lượt rời cửa sổ | Bài toán này |

**Vì sao cần cả bốn lớp**

- **Cửa sổ nguyên văn** giữ độ chính xác cho câu nối tiếp ngay sau đó ("Trong số đó tàu nào đi xa nhất?" cần bảng xếp hạng đầy đủ của lượt trước).
- **Trạng thái đối tượng** (tàu, công ty, thời gian đang bàn) do code cập nhật từ kết quả tool, nên không phụ thuộc vào việc model nhớ. Nhờ đó "tàu đó", "công ty đó", "ngày hôm sau" vẫn được hiểu đúng sau nhiều lượt. Vector search khó làm được việc này, vì câu hỏi dạng đại từ không chứa từ khoá.
- **Tóm tắt** giữ các điều người dùng nhờ nhớ, theo mẫu bắt buộc giữ nguyên văn mã và tên.
- **Vector** là lưới an toàn cho chi tiết bị tóm tắt bỏ sót, và cho các lượt chưa kịp tóm tắt (tóm tắt chạy nền).

**Tham số:** `MEMORY_WINDOW_TURNS` (mặc định 6; đặt 2 khi kiểm tra), `MEMORY_WINDOW_MAX_TOKENS`, `MEMORY_TOOL_RESULT_MAX_CHARS`, `MEMORY_TOP_K`, `MEMORY_MIN_SCORE`, `SUMMARY_MAX_TOKENS`, `MEMORY_COMPACTION_WAIT_SECONDS`.

## 6. Cơ sở dữ liệu không gian

**PostgreSQL + PostGIS**, đúng như đề gợi ý:

- Cột `geometry(Point, 4326)` với chỉ mục GiST; dark gap có thêm `LineString`.
- B-tree `(vessel_id, event_ts)` cho các truy vấn "điểm gần nhất trước/sau" (LIMIT 1 theo index) và "hành trình trong khoảng".
- `pg_trgm` cho tìm tên tàu và công ty chịu sai chính tả.

Phần tính quãng đường và lọc nhiễu được làm bằng Python trên tập điểm của từng tàu (tối đa vài trăm điểm mỗi tàu), để dễ test đơn vị. Kết quả đã được đối chiếu với `ST_Length(geography)` trong `scripts/verify_facts.py`, chênh lệch dưới 0,5%. Khi dữ liệu lớn, phần này có thể chuyển xuống SQL; xem [architecture.md §10](architecture.md#10-hướng-mở-rộng-khi-dữ-liệu-lên-vài-chục-triệu-điểmngày).
