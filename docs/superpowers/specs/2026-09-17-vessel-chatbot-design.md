# Thiết kế: Chatbot tra cứu tàu biển (VegaStar take-home)

Ngày: 2026-09-17 · Phạm vi: R1–R4, N1–N3, D1–D3.

## 1. Mục tiêu

Chatbot LLM đóng gói thành API streaming, trả lời câu hỏi tiếng Việt về 1.000 tàu (AIS 10–12/09/2026),
nhớ hội thoại dài vượt context window (pgvector), lấy mọi số liệu qua tool truy vấn có tham số,
kèm UI web có bản đồ động (một và nhiều hành trình).

## 2. Công nghệ

| Thành phần | Lựa chọn |
|---|---|
| Backend | Python 3.12, FastAPI, uvicorn, asyncpg, pydantic-settings, sse-starlette |
| LLM | OpenAI `gpt-4o-mini` (env `LLM_MODEL`), tool calling + streaming, vòng lặp tự viết |
| Embedding | OpenAI `text-embedding-3-small` (1536 chiều, env `EMBEDDING_MODEL`, `EMBEDDING_DIM`) |
| DB | Một container `postgis/postgis:16` + extension `vector` (pgvector), `pg_trgm` |
| Frontend | React + Vite + TypeScript + MapLibre GL |
| Test | pytest, pytest-asyncio, httpx; Postgres thật qua docker; LLM giả |

Lý do không dùng LangChain/LangGraph: cần kiểm soát chính xác sự kiện SSE, luồng dữ liệu bản đồ
đi vòng qua model và bộ nhớ tuỳ biến; vòng lặp tool ~150 dòng dễ giải thích.

## 3. Kiến trúc

```
React+Vite+MapLibre ──SSE──▶ FastAPI
                               ├─ /conversations CRUD
                               ├─ /conversations/{id}/chat (SSE) ─▶ ChatService
                               │        ├─ MemoryManager (focus + summary + vector + window)
                               │        ├─ LLM loop (streaming, tool calls, MAX_TOOL_ITERATIONS)
                               │        └─ ToolRegistry ─▶ repositories (SQL tham số)
                               ├─ /map-data/{data_id}, /tracks, /vessels/{id}/dark-gaps
                               └─ /health
                                        │
                     PostgreSQL 16 + PostGIS + pgvector + pg_trgm
```

Bố cục mã nguồn:

```
src/vessel_chat/
  config.py            # Settings (pydantic-settings), mọi ngưỡng/URL/model
  db.py                # asyncpg pool
  schema.sql           # DDL toàn bộ
  geo.py               # haversine, lọc GPS nhảy, tách đoạn, nội suy (thuần Python, test dễ)
  normalize.py         # chuẩn hoá tên tàu/công ty, nhóm loại tàu
  repositories/        # vessels.py, positions.py, gaps.py, companies.py, conversations.py, memory.py, map_data.py
  tools/               # registry.py + định nghĩa 8 tool (schema Pydantic → JSON schema)
  llm/                 # client.py (giao diện LLMClient + OpenAI impl), prompts.py
  memory/manager.py    # dựng ngữ cảnh + nén lượt cũ
  chat/service.py      # vòng lặp tool, phát sự kiện
  api/                 # app.py, routes_conversations.py, routes_chat.py, routes_map.py
scripts/  load_data.py, stream_chat.sh, run_scenarios.py, verify_facts.py
tests/    unit/, integration/, fixtures/
frontend/ React app
docs/     research.md, architecture.md, api.md
results/  transcript kịch bản
```

## 4. Schema DB

- `vessels(vessel_id uuid pk, mmsi, imo, shipname, shipname_norm, callsign, flag_code, flag,
  ship_type_summary, ship_type_group, ship_type_detail_name, length_m, width_m, dwt, grt, year_built)`;
  index trigram trên `shipname_norm`, btree trên `mmsi`, `imo`.
- `ais_positions(id bigserial, vessel_id, mmsi, event_ts timestamptz, lat, lon, geom geometry(Point,4326),
  speed_knots, course_deg, heading_deg, nav_status, reported_dest, draught_m)`;
  btree `(vessel_id, event_ts)`, GiST `geom`, btree `event_ts`.
- `dark_gaps(gap_id pk, vessel_id, mmsi, gap_start_ts, gap_end_ts, gap_duration_seconds, distance_nm,
  implied_speed_knots, start_lat, start_lon, end_lat, end_lon, start_geom, end_geom, path geometry(LineString,4326))`.
- `ownership(id, vessel_id, role, company_name, company_norm, company_country, start_date)`;
  trigram trên `company_norm`.
- `conversations(id uuid, title, created_at, updated_at, summary, summary_upto_turn int, focus_state jsonb)`.
- `messages(id bigserial, conversation_id fk on delete cascade, turn_no, role, content, tool_calls jsonb,
  tool_call_id, tool_name, created_at)`.
- `memory_chunks(id, conversation_id fk cascade, turn_no, text, embedding vector(EMBEDDING_DIM))`, HNSW cosine.
- `map_data(id uuid, conversation_id fk cascade, kind, geojson jsonb, summary jsonb, created_at)`.

Nạp: `scripts/load_data.py` — tạo schema (idempotent), `COPY` vào bảng staging, trong một transaction
`TRUNCATE` bảng dữ liệu tàu + `INSERT ... SELECT` có chuẩn hoá; không đụng bảng hội thoại. Chạy lại
không nhân đôi.

## 5. Tool

| Tool | Tham số | Kết quả cho LLM | Sự kiện `data` |
|---|---|---|---|
| `search_vessels` | `query`, `limit` | ứng viên + điểm khớp, cờ `ambiguous` | – |
| `get_vessel_details` | `vessel_id` | nhận dạng, cờ, loại, kích thước, công ty theo vai trò | – |
| `find_company_vessels` | `company_name`, `role?` | biến thể khớp + tàu theo vai trò | – |
| `get_position_at` | `vessel_id`, `timestamp` | điểm trước/sau, độ lệch, nội suy khi khe ≤ `INTERPOLATION_MAX_GAP_MINUTES`; báo không có dữ liệu nếu lệch > `POSITION_MAX_OFFSET_MINUTES` | point |
| `get_last_position` | `vessel_id` | điểm cuối | point |
| `get_track` | `vessel_id`, `start`, `end` | đầu/cuối, số điểm, điểm bị loại, quãng đường nm, tốc độ TB, khe lớn | track |
| `get_dark_gaps` | `vessel_id?`, `start?`, `end?`, `order_by`, `limit` | thời gian, độ dài, vị trí mất/lại, tốc độ trước khi mất | gaps |
| `get_multi_tracks` | `company_name?`, `role?`, `ship_type_group?`, `start`, `end`, `max_vessels` | tóm tắt: số tàu, số điểm, bbox, top quãng đường | tracks |

Quy tắc chung: tool nhận `vessel_id` sau khi đã `search_vessels` (hoặc chấp nhận `vessel` là tên/MMSI và
tự phân giải — nếu mơ hồ trả danh sách ứng viên). Kết quả trả LLM được cắt theo `TOOL_RESULT_MAX_ROWS`.
Thời gian nhận ISO-8601, coi là UTC nếu không có múi giờ.

Xử lý nhiễu:
- GPS nhảy: loại điểm có tốc độ suy ra tới cả điểm trước và sau > `MAX_PLAUSIBLE_SPEED_KNOTS` (50).
- Khe > `TRACK_GAP_SPLIT_HOURS` (3): `distance_nm` = tổng haversine mọi cặp điểm liên tiếp (kể cả khe,
  tính theo đường thẳng); báo riêng `gap_distance_nm` và danh sách khe để LLM nói rõ; hình học tách
  MultiLineString tại khe.
- Nhóm loại tàu: `tanker`, `cargo`, `fishing`, `tug`, `passenger`, `pleasure`, `high_speed`, `other`, `unknown`
  suy ra từ `ship_type_summary`.
- Tên công ty: `company_norm` = hoa, bỏ dấu câu, bỏ hậu tố pháp lý (CO, LTD, LIMITED, PTE, CORP,
  CORPORATION, INC, SA, LLC, GMBH, AS, JSC, BHD, SDN); so khớp chính xác theo norm trước, rồi trigram
  ≥ `COMPANY_MATCH_THRESHOLD`; trả danh sách biến thể dùng.
- Tên tàu: norm = hoa, bỏ ký tự không phải chữ/số; khớp chính xác → trigram ≥ `VESSEL_MATCH_THRESHOLD`.

## 6. Bộ nhớ

Prompt mỗi lượt: system → focus_state → summary (các lượt ≤ `summary_upto_turn`) → ký ức vector
(top `MEMORY_TOP_K`, `score ≥ MEMORY_MIN_SCORE`, chỉ lượt ngoài cửa sổ, cùng hội thoại) →
`MEMORY_WINDOW_TURNS` lượt gần nhất nguyên văn (giới hạn `MEMORY_WINDOW_MAX_TOKENS`, kết quả tool cũ rút gọn)
→ câu hỏi.

Một "lượt" = 1 tin user + mọi tin assistant/tool theo sau. Sau `done`, tác vụ nền nén các lượt vừa rơi khỏi
cửa sổ: nhúng "User: … / Assistant: …" vào `memory_chunks`; cập nhật summary bằng LLM với mẫu bắt buộc giữ
nguyên mã, tên, yêu cầu ghi nhớ. Lượt tiếp theo chờ tác vụ nền của hội thoại đó (tối đa
`MEMORY_COMPACTION_WAIT_SECONDS`). focus_state cập nhật từ tham số/kết quả tool (vessel, company, time range).

Sự kiện debug `memory` bật bởi `DEBUG_MEMORY_EVENTS`.

## 7. API và SSE

- `POST /conversations` `{title?}` · `GET /conversations` · `GET /conversations/{id}/messages` ·
  `DELETE /conversations/{id}` · `POST /conversations/{id}/chat` `{message}` (SSE).
- Sự kiện: `token{text}`, `tool_call{id,name,args}`, `tool_result{id,name,ok,summary}`,
  `data{data_id,kind,bbox,summary}`, `memory{summary_used,retrieved[]}`, `error{code,message}`,
  `done{message_id}`.
- `GET /map-data/{data_id}` → GeoJSON. `GET /tracks?vessel_ids&company&role&ship_type_group&start&end&limit&offset`
  → FeatureCollection phân trang (`MAX_TRACKS_PER_PAGE`). `GET /vessels/{id}/dark-gaps` → GeoJSON. `GET /health`.
- Lỗi: tool exception → kết quả `{error}` cho model + sự kiện `tool_result ok=false`; LLM lỗi → `error` rồi đóng;
  client ngắt → huỷ và lưu phần đã sinh. `statement_timeout` từ `DB_STATEMENT_TIMEOUT_MS`.
- Song song: một lock mỗi hội thoại (nối tiếp trong cùng hội thoại), khác hội thoại chạy song song.

## 8. Frontend

Ba cột: danh sách hội thoại · chat (token streaming, thẻ tool call thu gọn) · bản đồ MapLibre.
Sự kiện `data` → fetch `/map-data/{id}` → thêm layer (không xoá cũ; có nút xoá), fitBounds.
Nhiều hành trình: layer `line` màu theo `vessel_id`, popup tên tàu. Style nền từ `VITE_MAP_STYLE_URL`,
API từ `VITE_API_BASE_URL`.

## 9. Test

- Unit: geo, normalize, repositories (Postgres thật, fixture nhỏ tự tạo), tools, memory manager (LLM/embedding giả).
- Integration: API chat với LLM giả kịch bản hoá (thứ tự sự kiện, lưu tin nhắn, lỗi tool, hai hội thoại song song,
  nén bộ nhớ và truy xuất).
- `scripts/run_scenarios.py`: 5 kịch bản + biến thể đổi tên/thời điểm với OpenAI thật → `results/`.
- `scripts/verify_facts.py`: tính đáp án bằng SQL trực tiếp để đối chiếu.

## 10. Ngoài phạm vi

Xác thực người dùng, đa người thuê, triển khai cloud, text-to-SQL tự do.
