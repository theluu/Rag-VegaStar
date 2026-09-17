# Vessel Chatbot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chatbot LLM tra cứu tàu biển: API chat SSE, bộ nhớ dài hạn pgvector, tool truy vấn có tham số trên PostGIS, UI React + bản đồ MapLibre (một và nhiều hành trình).

**Architecture:** FastAPI + asyncpg trên một Postgres (PostGIS + pgvector + pg_trgm). Vòng lặp tool-calling tự viết trên OpenAI SDK phát sự kiện SSE có kiểu; GeoJSON lưu vào bảng `map_data` và chỉ gửi `data_id` qua stream. Bộ nhớ = focus_state + summary + vector recall + cửa sổ nguyên văn.

**Tech Stack:** Python 3.12+ (dev 3.13), FastAPI, asyncpg, pydantic-settings, sse-starlette, openai, pgvector (python), pytest/pytest-asyncio/httpx; Docker `postgis/postgis:16-3.4` + pgvector build; React 18 + Vite + TypeScript + maplibre-gl.

**Spec:** `docs/superpowers/specs/2026-09-17-vessel-chatbot-design.md`

## Global Constraints

- Không hardcode: API key, mật khẩu, host/URL, tên model, đường dẫn dữ liệu, ngưỡng bộ nhớ → `config.Settings` (env / `.env`).
- Không ghép chuỗi SQL từ nội dung người dùng; mọi giá trị qua `$n` của asyncpg.
- Không đưa CSV / kết quả lớn vào prompt; kết quả tool cắt theo `TOOL_RESULT_MAX_ROWS`.
- Không viết sẵn câu trả lời hay tên tàu của kịch bản trong mã hoặc prompt.
- Mọi thời gian là UTC ISO-8601.
- `data/` và `.docx` không bao giờ được commit.
- Commit sau mỗi task; message tiếng Anh dạng conventional commits, kết thúc bằng `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Lệnh test: `.venv/bin/pytest -q` (cần `docker compose up -d db`, DB test `vessel_test`).

## File Structure

```
docker-compose.yml, Dockerfile, db/Dockerfile (postgis + pgvector), pyproject.toml, .env.example, README.md
src/vessel_chat/
  config.py                 Settings
  db.py                     create_pool(), init_schema()
  schema.sql                DDL (idempotent)
  geo.py                    haversine_nm, filter_jumps, split_segments, interpolate, track_stats
  normalize.py              norm_name, norm_company, ship_type_group
  timeutil.py               parse_ts (naive → UTC)
  repositories/vessels.py   search_vessels, get_vessel, get_ownership, company_vessels, resolve_vessel
  repositories/positions.py positions_between, nearest_positions, last_position, last_before
  repositories/gaps.py      list_gaps
  repositories/conversations.py  CRUD + messages + focus/summary
  repositories/memory.py    add_chunk, search_chunks
  repositories/map_data.py  save_map_data, get_map_data
  tools/base.py             Tool, ToolContext, ToolResult, registry
  tools/vessel_tools.py     search_vessels, get_vessel_details, find_company_vessels
  tools/position_tools.py   get_position_at, get_last_position, get_track, get_multi_tracks
  tools/gap_tools.py        get_dark_gaps
  llm/client.py             LLMClient protocol, OpenAILLM, Embedder protocol, OpenAIEmbedder, stream deltas
  llm/prompts.py            SYSTEM_PROMPT, SUMMARY_PROMPT
  memory/manager.py         MemoryManager.build_context, compact
  chat/events.py            SSE event dataclasses
  chat/service.py           ChatService.run_turn (async generator)
  api/app.py, api/deps.py, api/routes_conversations.py, api/routes_chat.py, api/routes_map.py
scripts/load_data.py, stream_chat.sh, run_scenarios.py, verify_facts.py
tests/conftest.py, tests/fixtures/*.csv, tests/fakes.py, tests/unit/*, tests/integration/*
frontend/ (Vite React TS)
docs/research.md, docs/architecture.md, docs/api.md, results/
```

---

### Task 1: Scaffolding, config, Docker DB

**Files:** Create `pyproject.toml`, `docker-compose.yml`, `db/Dockerfile`, `db/init/01-extensions.sql`, `.env.example`, `src/vessel_chat/__init__.py`, `src/vessel_chat/config.py`, `tests/unit/test_config.py`

**Interfaces — Produces:** `get_settings() -> Settings` (lru_cache). Fields: `database_url`, `test_database_url`, `openai_api_key`, `openai_base_url`, `llm_model`, `llm_temperature`, `embedding_model`, `embedding_dim`, `data_dir`, `memory_window_turns`, `memory_window_max_tokens`, `memory_top_k`, `memory_min_score`, `memory_compaction_wait_seconds`, `debug_memory_events`, `max_tool_iterations`, `tool_result_max_rows`, `max_plausible_speed_knots`, `track_gap_split_hours`, `position_max_offset_minutes`, `interpolation_max_gap_minutes`, `vessel_match_threshold`, `company_match_threshold`, `multi_track_max_vessels`, `multi_track_max_points`, `max_tracks_per_page`, `db_statement_timeout_ms`, `llm_timeout_seconds`, `cors_origins`, `api_host`, `api_port`.

- [ ] Test: `Settings(_env_file=None, database_url=..., memory_window_turns=2)` giữ giá trị; env `MEMORY_WINDOW_TURNS=3` được đọc.
- [ ] Viết config, compose (service `db` build `db/`, volume, healthcheck; `api` build `.`; `web` build `frontend/`), `.env.example` giải thích từng biến.
- [ ] `python3.13 -m venv .venv && .venv/bin/pip install -e '.[dev]'`; `docker compose up -d db`; tạo DB `vessel_test`.
- [ ] `pytest tests/unit/test_config.py` PASS → commit `chore: scaffold project, config and database container`.

### Task 2: Pure helpers — geo, normalize, time

**Files:** `src/vessel_chat/geo.py`, `normalize.py`, `timeutil.py`; tests `tests/unit/test_geo.py`, `test_normalize.py`, `test_timeutil.py`

**Produces:**
- `haversine_nm(lat1, lon1, lat2, lon2) -> float`
- `Point` = dataclass(ts: datetime, lat, lon, speed: float|None, course, nav_status)
- `filter_jumps(points, max_speed_kn) -> tuple[list[Point], int]` (loại điểm mà tốc độ tới cả điểm trước và sau > ngưỡng; điểm đầu/cuối chỉ xét một phía và chỉ loại khi hàng xóm kế tiếp không bị nghi ngờ)
- `split_segments(points, gap_hours) -> list[list[Point]]`
- `track_stats(points, gap_hours) -> dict(point_count, distance_nm, gap_distance_nm, duration_hours, avg_speed_knots, gaps=[{from,to,hours,distance_nm}])`; avg = distance_nm / duration_hours
- `interpolate(p1, p2, ts) -> (lat, lon)` (tuyến tính theo thời gian, xử lý kinh tuyến không cần vì vùng 102–118E)
- `norm_name(s) -> str`, `norm_company(s) -> str`, `ship_type_group(summary) -> str`
- `parse_ts(str) -> datetime` (aware UTC; chấp nhận 'Z', offset, naive)

Test cases bắt buộc: haversine 1° kinh độ tại xích đạo ≈ 60.04 nm; điểm nhảy giữa bị loại, điểm bình thường giữ; khe 4h tách 2 đoạn và `gap_distance_nm` > 0; `norm_company('EVERGREEN MARINE CORP.') == norm_company('Evergreen Marine Corporation') == 'EVERGREEN MARINE'`; `norm_company('BW LPG HOLDING PTE LTD') == norm_company('BW LPG HOLDING LTD')`; `ship_type_group('Tanker(s), carrying DG...') == 'tanker'`, `'Cargo ships, no additional information' → 'cargo'`, `'Fishing vessel' → 'fishing'`, `'Not available' → 'unknown'`; parse_ts naive → UTC.

- [ ] Viết test → FAIL → implement → PASS → commit `feat: add geo, normalization and time helpers`.

### Task 3: Schema + data loader (R1)

**Files:** `src/vessel_chat/schema.sql`, `src/vessel_chat/db.py`, `scripts/load_data.py` (module `vessel_chat.loader` + CLI wrapper), `tests/fixtures/{vessels,ais_positions,dark_gaps,ownership}.csv`, `tests/conftest.py`, `tests/unit/test_loader.py`

**Produces:** `create_pool(dsn) -> asyncpg.Pool` (init: register pgvector, set statement_timeout, jsonb codec); `init_schema(conn)`; `load_all(conn, data_dir) -> dict[table,count]`. Fixture conftest: `pool` (session, test DB, schema + fixture data loaded once), `settings`.

Fixture data (tự tạo, tên hư cấu): 6 tàu — `ALPHA STAR` (cargo, 3 công ty, registered owner `OCEAN LINE CO LTD`), `ALPHA STAR II`, `BETA SEA` (tanker, registered owner `OCEAN LINE CO` — biến thể), `GAMMA` không có ownership, tàu tên rỗng, `DELTA FISH` (fishing). Vị trí: ALPHA STAR 10/09 00:00→11/09 có 1 điểm nhảy và khe 5h; dark_gaps: 2 sự kiện với độ dài khác nhau.

Test: chạy `load_all` hai lần → số dòng không đổi; `geom` không null; `ship_type_group`, `shipname_norm`, `company_norm` được điền.

- [ ] Test → FAIL → implement (COPY vào bảng `stg_*` TEMP, TRUNCATE + INSERT trong 1 transaction; `ANALYZE`) → PASS.
- [ ] Chạy trên dữ liệu thật: `.venv/bin/python scripts/load_data.py` — in số dòng (171073/1000/880/4127) và thời gian.
- [ ] Commit `feat: add schema and idempotent CSV loader`.

### Task 4: Query repositories (R1, R4)

**Files:** `src/vessel_chat/repositories/{__init__,vessels,positions,gaps}.py`; tests `tests/unit/test_repo_vessels.py`, `test_repo_positions.py`, `test_repo_gaps.py`

**Produces:**
- `search_vessels(conn, query, limit, threshold) -> list[dict]` — nếu query toàn số 9 chữ → mmsi; 7 chữ → imo (so khớp int); callsign chính xác; tên norm chính xác (score 1.0); trigram `similarity(shipname_norm, $1) >= threshold` + `shipname_norm LIKE $1 || '%'`; order score desc.
- `get_vessel(conn, vessel_id) -> dict|None`; `get_ownership(conn, vessel_id) -> list[dict]`
- `match_companies(conn, name, threshold, limit=10) -> list[{company_name, company_norm, score}]`
- `company_vessels(conn, company_norms: list[str], role: str|None, exclude_vessel_id=None) -> list[dict]`
- `vessels_by_filter(conn, company_norms|None, role|None, ship_type_group|None, limit) -> list[dict]`
- `positions_between(conn, vessel_id, start, end) -> list[Point]`
- `nearest_positions(conn, vessel_id, ts) -> (before: Point|None, after: Point|None)`
- `last_position(conn, vessel_id) -> Point|None`
- `positions_for_vessels(conn, vessel_ids, start, end) -> dict[vessel_id, list[Point]]`
- `list_gaps(conn, vessel_id|None, start|None, end|None, order_by: 'duration'|'start', limit) -> list[dict]`

Test: tên sai chính tả `alpa star` tìm ra ALPHA STAR; `ALPHA STAR` trả ALPHA STAR score 1 đứng đầu và ALPHA STAR II đi sau; MMSI; IMO; company `Ocean Line` khớp cả hai biến thể; company_vessels loại tàu hiện tại; nearest before/after đúng; list_gaps order duration desc.

- [ ] Test → FAIL → implement → PASS → commit `feat: add parameterized vessel, position and gap queries`.

### Task 5: Tool layer

**Files:** `src/vessel_chat/tools/{__init__,base,vessel_tools,position_tools,gap_tools}.py`, `src/vessel_chat/repositories/map_data.py`; tests `tests/unit/test_tools.py`

**Produces:**
```python
@dataclass
class ToolContext: pool; settings; conversation_id: UUID
@dataclass
class ToolResult: content: dict; map_data: list[MapPayload] = []; focus: dict = {}
@dataclass
class MapPayload: kind: str; geojson: dict; summary: dict; bbox: list[float]
class Tool: name; description; Args: type[BaseModel]; async def run(ctx, args) -> ToolResult
REGISTRY: dict[str, Tool]; def openai_tool_specs() -> list[dict]
async def execute_tool(ctx, name, raw_args: str) -> ToolResult  # validate, run, catch -> {"error": ...}
save_map_data(conn, conversation_id, payload) -> UUID; get_map_data(conn, id) -> dict|None
```
Mọi tool có trường `vessel` (tên/MMSI/IMO/vessel_id) → `resolve_vessel` : một kết quả rõ ràng (score ≥ 0.95 hoặc duy nhất) → dùng; nhiều → trả `{"status":"ambiguous","candidates":[...]}`; không có → `{"status":"not_found"}`.
Focus: tool trả `focus={"vessel": {...id,name,mmsi}, "company": ..., "time_range": ...}`.

Test (dùng fixture DB): get_track trả distance, removed_points=1, gaps 1, map payload LineString/MultiLineString; get_position_at trên khe → báo `no_data_near` khi lệch > ngưỡng; nội suy khi có 2 điểm gần; get_dark_gaps có `speed_before_gap_knots`; find_company_vessels role registered_owner; get_multi_tracks theo ship_type_group trả summary và feature collection không vượt `multi_track_max_points` (giảm mẫu đều); execute_tool với args sai → content có `error`.

- [ ] Test → FAIL → implement → PASS → commit `feat: add LLM tool layer with map payloads`.

### Task 6: Conversation + memory repositories, LLM client

**Files:** `repositories/conversations.py`, `repositories/memory.py`, `llm/client.py`, `llm/prompts.py`, `tests/fakes.py`, `tests/unit/test_repo_conversations.py`

**Produces:**
- `create_conversation(conn, title) -> dict`, `list_conversations`, `get_conversation`, `delete_conversation -> bool`, `add_message(conn, conv_id, turn_no, role, content, tool_calls=None, tool_call_id=None, tool_name=None) -> int`, `list_messages(conn, conv_id) -> list[dict]`, `next_turn_no(conn, conv_id) -> int`, `update_focus`, `update_summary(conn, conv_id, summary, upto_turn)`, `touch/rename`.
- `add_chunk(conn, conv_id, turn_no, text, embedding)`, `search_chunks(conn, conv_id, embedding, max_turn, k, min_score) -> list[{turn_no,text,score}]`
- `LLMClient` protocol: `stream_chat(messages, tools) -> AsyncIterator[LLMDelta]` với `LLMDelta(text: str|None, tool_calls: list[ToolCallReq]|None, finish: str|None)` (tool calls được gộp đầy đủ khi stream kết thúc); `complete(messages) -> str`. `Embedder.embed(texts) -> list[list[float]]`.
- `tests/fakes.py`: `ScriptedLLM(script)` (mỗi lượt gọi trả một bước: text hoặc tool call), `HashEmbedder(dim)` (embedding xác định theo bag-of-words để test truy xuất ngữ nghĩa đơn giản).

- [ ] Test repo (CRUD, cascade delete, search_chunks lọc conv + max_turn) → PASS → commit `feat: add conversation storage, vector memory store and LLM client`.

### Task 7: MemoryManager (R3)

**Files:** `memory/manager.py`, `tests/unit/test_memory.py`

**Produces:**
```python
class MemoryManager:
    def __init__(self, pool, llm, embedder, settings)
    async def build_context(conv_id, user_text) -> BuiltContext  # messages: list[dict], retrieved: list, summary_used: bool
    async def compact(conv_id) -> None   # nén các lượt < current_turn - window + 1 mà chưa nén
    def schedule_compaction(conv_id); async def wait_compaction(conv_id)
```
Lượt được nén: `turn_no <= last_turn - window`, `> summary_upto_turn`. Text chunk = "Lượt {n}\nNgười dùng: …\nTrợ lý: …" (bỏ nội dung tool). Summary prompt giữ nguyên mã/tên/yêu cầu ghi nhớ. Window messages: bỏ tool messages của các lượt trước lượt gần nhất quá dài (cắt content tool > 1500 ký tự) và luôn giữ cặp assistant tool_calls ↔ tool hợp lệ.

Test: window=2, 5 lượt → context chỉ chứa 2 lượt cuối nguyên văn, summary được dùng, chunk lượt 1 truy xuất được với câu hỏi chứa từ khoá của lượt 1; focus_state xuất hiện trong system context.

- [ ] Test → FAIL → implement → PASS → commit `feat: add hybrid conversation memory manager`.

### Task 8: ChatService + SSE API (R2)

**Files:** `chat/events.py`, `chat/service.py`, `api/app.py`, `api/deps.py`, `api/routes_conversations.py`, `api/routes_chat.py`, `api/routes_map.py`, `tests/integration/test_api.py`

**Produces:** `ChatService.run_turn(conv_id, text) -> AsyncIterator[Event]` với `Event(type, data)`; lock per conversation; lưu user message trước, assistant/tool messages khi xong (hoặc khi bị huỷ); cập nhật focus; schedule compaction; `create_app(settings, llm=None, embedder=None) -> FastAPI` (lifespan tạo pool, cho phép inject fake).
Routes: như spec §7, `/tracks` và `/vessels/{id}/dark-gaps` dùng lại tool/geo helpers.

Test (ScriptedLLM): chuỗi sự kiện `tool_call → tool_result → data → token… → done`; messages lưu đủ và GET trả lại; tool lỗi → `tool_result ok=false` rồi vẫn `done`; LLM ném lỗi → `error` và stream kết thúc; 2 hội thoại chạy `asyncio.gather` không lẫn nội dung; 404 khi hội thoại không tồn tại; `/map-data/{id}` trả GeoJSON; `/tracks` phân trang.

- [ ] Test → FAIL → implement → PASS; `scripts/stream_chat.sh` (curl -N) → commit `feat: add streaming chat API and conversation endpoints`.

### Task 9: Prompt tuning + scenario runner với OpenAI thật (R4, D3)

**Files:** `llm/prompts.py`, `scripts/run_scenarios.py`, `scripts/verify_facts.py`, `scenarios/*.yaml` (câu hỏi đề + biến thể), `results/`

- [ ] `verify_facts.py` in đáp án SQL cho các câu kịch bản (tham số hoá theo tên/MMSI nhận từ CLI).
- [ ] `run_scenarios.py --base-url` gọi API thật qua SSE, ghi `results/scenario_N.md` (câu hỏi, tool + args, trả lời, ký ức truy xuất) và `results/summary.md`.
- [ ] Chạy với `MEMORY_WINDOW_TURNS=2`; so với verify_facts; chỉnh prompt/tool description chung (không nhắc tên tàu) đến khi đúng; chạy biến thể đổi tên/thời điểm.
- [ ] Commit `feat: add scenario runner and results transcripts`.

### Task 10: Frontend N1 + N2

**Files:** `frontend/` (Vite React TS): `src/api.ts` (REST + SSE parser qua fetch ReadableStream), `src/App.tsx`, `src/components/{ConversationList,ChatPanel,MessageView,ToolCallCard,MapView}.tsx`, `src/styles.css`, `frontend/Dockerfile`, `frontend/.env.example`

- [ ] SSE parser unit-test bằng vitest (`src/sse.test.ts`: tách event qua nhiều chunk).
- [ ] UI 3 cột; streaming token; mở lại hội thoại cũ hiển thị lịch sử (+ tái hiện bản đồ qua map_data của hội thoại: `GET /conversations/{id}/map-data`).
- [ ] MapView: layer point/track/gaps, fitBounds, legend, nút xoá; follow-up thêm layer.
- [ ] `npm run build` PASS; kiểm tra trên trình duyệt với backend thật → commit `feat: add web chat UI with dynamic map`.

### Task 11: N3 multi-track rendering

- [ ] `get_multi_tracks` + `/tracks` đã có; frontend layer `tracks` màu theo vessel (`match` expression từ bảng màu), popup, bảng top quãng đường; kiểm tra "tất cả tàu cargo ngày 11/09" (~500 tàu, hàng chục nghìn điểm) mượt.
- [ ] Commit `feat: render multi-vessel tracks`.

### Task 12: Docs + delivery (D1, D2)

**Files:** `README.md`, `.env.example`, `docs/research.md`, `docs/architecture.md` (mermaid), `docs/api.md`, `Dockerfile`, `docker-compose.yml` hoàn chỉnh

- [ ] README: yêu cầu hệ thống, `cp .env.example .env`, `docker compose up -d`, `docker compose run --rm api python scripts/load_data.py`, chạy test, curl stream, bảng trạng thái R1…D3.
- [ ] research.md: so sánh LLM, embedding, vector DB, framework, 4 chiến lược bộ nhớ; architecture.md: sơ đồ, luồng, bộ nhớ, schema, tool, API, hạn chế, độ trễ/chi phí, mở rộng (partition theo ngày, TimescaleDB, tile vector, ClickHouse…).
- [ ] Clean-checkout test: `docker compose up --build` từ đầu → load → chat curl.
- [ ] Commit, tạo repo GitHub private, push.
