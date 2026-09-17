# Nghiên cứu và lựa chọn công nghệ

Mục tiêu: chatbot trả lời **đúng số liệu** trên dữ liệu có cấu trúc (AIS, đăng kiểm, chủ sở hữu), stream theo token, nhớ được hội thoại dài, và vẽ được bản đồ. Vì vậy các tiêu chí đặt theo thứ tự ưu tiên: (1) khả năng gọi tool ổn định; (2) độ trễ và chi phí; (3) vận hành đơn giản để người chấm chạy lại được; (4) giải thích được từng phần.

## 1. LLM

| Lựa chọn | Tool calling | Tiếng Việt | Độ trễ / chi phí | Nhận xét |
|---|---|---|---|---|
| **OpenAI gpt-4o-mini** (đã chọn) | Tốt, hỗ trợ gọi nhiều tool song song, streaming tool call | Tốt | Nhanh; 0,15 / 0,60 USD cho 1 triệu token vào/ra | Đủ tốt cho việc định tuyến tới 9 tool có mô tả rõ; rẻ nên chạy kịch bản nhiều lần được. Đã có sẵn key. |
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

Phần tính quãng đường và lọc nhiễu được làm bằng Python trên tập điểm của từng tàu (tối đa vài trăm điểm mỗi tàu), để dễ test đơn vị. Kết quả đã được đối chiếu với `ST_Length(geography)` trong `scripts/verify_facts.py`, chênh lệch dưới 0,5%. Khi dữ liệu lớn, phần này có thể chuyển xuống SQL; xem [architecture.md §16](architecture.md#16-hướng-mở-rộng-khi-dữ-liệu-lên-vài-chục-triệu-điểmngày).

## 7. Guardrails

| Lựa chọn | Ưu | Nhược | Quyết định |
|---|---|---|---|
| **Heuristic có trọng số (regex VI/EN trên văn bản đã bỏ dấu)** | 0 ms, không tốn tiền, xác định, test được, chặn trước khi gọi LLM | Bỏ lọt cách diễn đạt mới | ✅ lớp đầu vào |
| Gọi LLM phân loại mỗi câu hỏi | Hiểu ngữ nghĩa tốt hơn | Thêm 0,5–1 s và chi phí mỗi lượt; bản thân cũng có thể bị injection | Không dùng; ghi thành hướng mở rộng |
| Model phân loại chuyên dụng (Llama Prompt Guard, Lakera) | Chính xác | Cần GPU hoặc dịch vụ ngoài | Hướng mở rộng |
| OpenAI Moderation | Miễn phí, đa ngôn ngữ | Thêm một request mạng (~200 ms) | ✅ bật mặc định, cấu hình fail-open/closed |
| NeMo Guardrails / Guardrails AI | Khung đầy đủ | Nặng, thêm DSL phải giải thích | Không dùng |

Ở đầu ra, cách hiệu quả nhất để chống bịa số liệu là **kiểm chứng xác định**: mọi con số trong câu trả lời phải truy được về kết quả tool. Cách này rẻ hơn và đáng tin hơn nhờ một LLM thứ hai chấm. Lọc secret và lặp prompt được làm **ngay trên luồng stream** (giữ lại một đoạn đuôi), vì lọc sau khi đã gửi token thì đã quá muộn.

Phòng thủ quan trọng nhất vẫn là kiến trúc: LLM không có quyền ghi, không viết SQL, chỉ gọi tool đọc có tham số trên pool chỉ đọc. Guardrail là lớp giảm rủi ro, không phải lớp duy nhất.

## 8. RAG cho kiến thức nghiệp vụ

- **Vì sao cần RAG** khi dữ liệu chính là bảng có cấu trúc: người phân tích còn hỏi "trạng thái này nghĩa là gì", "dark gap do đâu", "DWT khác GT thế nào". Để model tự trả lời thì dễ sai hoặc không nhất quán; kho tài liệu có kiểm soát cho câu trả lời có nguồn và kiểm chứng được.
- **Nội dung:** 8 tài liệu tiếng Việt tự biên soạn từ các chuẩn (ITU-R M.1371, SOLAS, Bộ luật ISM, Công ước đo dung tích 1969) và đặc điểm của bộ dữ liệu.
- **Chia đoạn theo tiêu đề** thay vì cắt theo số token cố định: mỗi đoạn là một ý trọn vẹn và trích dẫn được (`file › mục`).
- **Tìm kiếm lai (vector + từ khoá) + RRF:** embedding bắt được ý nghĩa ("tàu đang neo" ≈ "At anchor"), còn từ khoá bắt được mã và thuật ngữ chính xác (`511`, `IMO`, `ISM`). RRF gộp hai bảng xếp hạng mà không phải hiệu chỉnh thang điểm. Văn bản được bỏ dấu cho full-text để câu hỏi gõ không dấu vẫn khớp.
- **Vector DB:** vẫn là pgvector, nhưng với index HNSW (khác `memory_chunks`), vì kho tri thức dùng chung cho mọi hội thoại.
- **Không dùng reranker cross-encoder:** kho chỉ có 31 đoạn và top-4 đã chính xác; nên thêm khi kho lên hàng nghìn đoạn.

## 9. Đánh giá (harness)

- **Đáp án chuẩn lấy từ dữ liệu bằng SQL**, không viết tay, nên đổi seed là có bộ câu hỏi mới (chống "học thuộc" kịch bản).
- **Chấm xác định** (tool đã gọi, số liệu kèm dung sai, chuỗi, trích dẫn, từ chối) thay vì dùng LLM làm giám khảo: rẻ, lặp lại được, dễ debug. LLM-as-judge chỉ cần cho câu trả lời mô tả dài, và đã được ghi vào hướng mở rộng.
- **Red-team** được đưa vào cùng bộ đánh giá, để mọi thay đổi prompt đều được kiểm tra cả độ đúng lẫn độ an toàn.
- Harness chạy qua API thật, nên kiểm tra luôn cả middleware, guardrail, stream và chứng cứ, chứ không chỉ riêng LLM.

## 10. Các công nghệ đã cân nhắc nhưng không dùng

Nguyên tắc chung: chỉ thêm một hệ thống lưu trữ khi PostgreSQL không đáp ứng được nhu cầu cụ thể. Mỗi hệ thống thêm vào kéo theo một container, một đường đồng bộ dữ liệu, một bề mặt bảo mật, và người chấm phải dựng thêm dịch vụ.

### 10.1 Neo4j (graph database)

- **Nhu cầu thực tế:** bảng `ownership` chỉ nối tàu với công ty theo 6 vai trò (4.127 dòng). Mọi câu hỏi của đề đi 1–2 bước ("tàu này của ai" → "công ty đó còn tàu nào"), PostgreSQL xử lý bằng một phép JOIN có chỉ mục trong vài mili giây.
- **Phần nặng không phải đồ thị:** phần lớn câu hỏi là vị trí theo thời gian, hành trình, quãng đường, mất tín hiệu, là việc của PostGIS và chỉ mục thời gian.
- **Rủi ro:** để LLM tự sinh Cypher tương đương text-to-SQL, mở lại đúng rủi ro mà thiết kế công cụ có tham số đã tránh.
- **Khi nào nên dùng:** phân tích mạng lưới nhiều tầng, như chuỗi sở hữu hưởng lợi (tàu → công ty vỏ → công ty mẹ → cá nhân), khoảng cách tới thực thể bị trừng phạt, cụm công ty chung địa chỉ/giám đốc, cụm tàu từng gặp nhau trên biển. Dữ liệu hiện tại không có các quan hệ này.
- **Lộ trình:** thử `WITH RECURSIVE` hoặc extension Apache AGE ngay trên PostgreSQL trước; tách sang Neo4j khi đồ thị lớn và truy vấn thật sự sâu. Dù dùng hệ nào, LLM vẫn chỉ gọi công cụ có tham số.

### 10.2 Elasticsearch / OpenSearch

| Nhu cầu tìm kiếm | Cách đang làm | Quy mô |
|---|---|---|
| Tên tàu gõ sai chính tả | `pg_trgm` + chuẩn hoá tên | 1.000 tàu |
| Tên công ty có biến thể | chuẩn hoá hậu tố pháp lý + trigram | khoảng 960 công ty |
| Kho tri thức (RAG) | vector (pgvector HNSW) + full-text (tsvector, bỏ dấu), gộp RRF | 31 đoạn |
| MMSI, IMO, hô hiệu | chỉ mục B-tree, khớp chính xác | vài ms |

- **Kết quả hiện tại đã đủ:** truy vấn công cụ mất 1–80 ms, độ trễ chủ yếu nằm ở LLM (khoảng 4 giây); harness đạt 42/42, kể cả các ca tên sai chính tả và câu hỏi kiến thức.
- **Chi phí nếu thêm:** dịch vụ JVM khoảng 1–2 GB RAM, cấu hình bảo mật riêng, pipeline đồng bộ từ PostgreSQL và nguy cơ lệch dữ liệu giữa hai nơi.
- **Khi nào nên dùng:** tìm kiếm toàn văn trên khối tài liệu lớn (tin tức hàng hải, danh sách trừng phạt, báo cáo kiểm tra cảng, hồ sơ công ty; hàng triệu văn bản, nhiều ngôn ngữ), hoặc danh bạ tàu/công ty hàng triệu bản ghi cần gợi ý khi gõ, lọc nhiều tiêu chí và thống kê theo nhóm.
- **Lộ trình:** tối ưu PostgreSQL trước (`unaccent`, HNSW, reranker), rồi Meilisearch/Typesense nếu cần công cụ tìm kiếm nhẹ, cuối cùng mới OpenSearch/Elasticsearch, đồng bộ qua hàng đợi (CDC). Dữ liệu AIS theo thời gian hợp với TimescaleDB hoặc ClickHouse hơn là Elasticsearch.
- **Dùng cho log thì hợp lý:** log JSON một dòng mỗi lượt đã sẵn định dạng để đẩy vào ELK/Kibana hoặc Loki khi cần quan sát tập trung. Đây là công cụ vận hành, không nằm trong luồng trả lời của chatbot.

### 10.3 Tóm tắt

| Công nghệ | Quyết định | Điều kiện để xem xét lại |
|---|---|---|
| Neo4j | Không dùng | Quan hệ sở hữu nhiều tầng, phân tích mạng lưới trừng phạt |
| Elasticsearch / OpenSearch | Không dùng cho chatbot | Hàng triệu tài liệu văn bản cần full-text; log tập trung (ELK) |
| Vector DB riêng (Qdrant, Pinecone…) | Không dùng (xem mục 3) | Ký ức hoặc kho tri thức lên hàng chục triệu vector |
| LangChain / LangGraph | Không dùng (xem mục 4) | Luồng nhiều tác tử phức tạp, cần công cụ theo dõi sẵn có |
