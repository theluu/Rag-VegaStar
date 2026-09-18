# API

- **Base URL:** `http://localhost:8000` (cổng đổi được qua `API_HOST_PORT`).
- **Schema OpenAPI:** [openapi.json](openapi.json), hoặc giao diện tương tác tại `/docs` khi server đang chạy (bản triển khai: <https://vegastar.themeshub.net/api/docs>).
- **Sau reverse proxy:** đặt `ROOT_PATH` bằng tiền tố (vd. `/api`) để trang `/docs` và mục `servers` của OpenAPI trỏ đúng.
- **Xác thực:** khi server bật `AUTH_USERS`, đăng nhập qua `POST /auth/login` rồi gửi `Authorization: Bearer <token>`; khi bật `API_KEYS`, gửi `X-API-Key: <khoá>` hoặc `Authorization: Bearer <khoá>`. Thiếu hoặc sai → 401. `/health`, `/auth/login`, `/metrics`, `/docs` luôn công khai.
- **Giới hạn:** vượt `RATE_LIMIT_API_PER_MINUTE` / `RATE_LIMIT_CHAT_PER_MINUTE` → 429 kèm `Retry-After`; body > `MAX_REQUEST_BYTES` → 413.
- **Header:** mọi response có `X-Request-ID` (gửi kèm để nối log), cùng các header bảo mật. Response JSON lớn được nén gzip; SSE không nén.
- **Lỗi 500:** chỉ trả `{"detail": "Lỗi hệ thống", "request_id": "…"}`; chi tiết nằm trong log.
- **Định dạng:** mọi thời gian là UTC ISO-8601 (`2026-09-11T21:00:00Z`); tham số thời gian không có múi giờ được hiểu là UTC. Toạ độ GeoJSON theo thứ tự `[lon, lat]`.

## Đăng nhập

### `POST /auth/login`

```bash
curl -s -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
  -d '{"username": "demo", "password": "demo"}'
```

```json
{"username": "demo", "expires_at": "2026-09-17T22:30:00Z", "token": "v1.eyJ1Ijoi…", "token_type": "Bearer"}
```

| Mã | Khi nào |
|---|---|
| 200 | Đúng tài khoản; token hết hạn sau `SESSION_TTL_HOURS` |
| 401 | Sai tên đăng nhập hoặc mật khẩu (thông báo chung) |
| 404 | Server không bật đăng nhập (`AUTH_USERS` trống) |
| 422 | Thiếu trường hoặc quá dài |
| 429 | Vượt `RATE_LIMIT_LOGIN_PER_MINUTE` lần thử mỗi IP (có `Retry-After`) |

Dùng token cho mọi yêu cầu khác: `-H "Authorization: Bearer $TOKEN"`. Token không hợp lệ, hết hạn hoặc ký bằng khoá khác → 401.

### `GET /auth/me`

Trả `{"username": "demo", "expires_at": "…"}` của token hiện tại (404 nếu đang dùng API key).

## Hội thoại

### `POST /conversations` → 201

```bash
curl -s -X POST localhost:8000/conversations -H 'Content-Type: application/json' -d '{"title": "Theo dõi HS-2026-117"}'
```

`title` là tuỳ chọn. Nếu bỏ trống, hội thoại tự lấy tiêu đề từ câu hỏi đầu tiên.

```json
{"id": "3e809ebf-d71b-4eec-b108-7745dbc1eccf", "title": "Theo dõi HS-2026-117",
 "created_at": "2026-09-17T03:44:52Z", "updated_at": "2026-09-17T03:44:52Z", "message_count": 0}
```

### `GET /conversations`

Trả danh sách hội thoại, mới cập nhật đứng trước, kèm `message_count` và `turn_count`.

### `GET /conversations/{id}`

Trả chi tiết hội thoại, gồm `summary`, `summary_upto_turn` và `focus_state` (đối tượng đang bàn: tàu, công ty, thời điểm).

### `GET /conversations/{id}/messages`

Trả toàn bộ tin nhắn theo thứ tự. Mỗi tin nhắn có:

| Trường | Ý nghĩa |
|---|---|
| `turn_no` | Số thứ tự lượt |
| `role` | `user` / `assistant` / `tool` |
| `content` | Nội dung |
| `tool_calls` | Ở tin nhắn assistant có gọi tool |
| `tool_call_id`, `tool_name` | Ở tin nhắn tool |
| `meta` | Ở tin nhắn assistant cuối lượt: `data_ids`, `usage`, `evidence`, `verification`, `guardrail`, `error`, `interrupted` |

### `GET /conversations/{id}/map-data`

Danh sách các lớp bản đồ đã sinh trong hội thoại (`id`, `kind`, `summary`, `bbox`), dùng để vẽ lại bản đồ khi mở lại hội thoại.

### `DELETE /conversations/{id}` → 204

Xoá hội thoại, kéo theo tin nhắn, ký ức vector và dữ liệu bản đồ. Trả 404 nếu hội thoại không tồn tại.

## Chat (SSE)

### `POST /conversations/{id}/chat`

- **Body:** `{"message": "…"}` (1–4000 ký tự).
- **Response:** `text/event-stream`.
- **Lỗi trước khi stream:** 404 (hội thoại không tồn tại), 422 (tin nhắn không hợp lệ).
- **Tuần tự trong một hội thoại:** hai request vào *cùng* hội thoại được xử lý lần lượt; các hội thoại khác nhau chạy song song.

```bash
curl -N -X POST localhost:8000/conversations/$CID/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "Lúc 21:00 ngày 11/09/2026 (UTC) tàu KOTA GAYA đang ở đâu?"}'
```

Hoặc dùng script có sẵn: `scripts/stream_chat.sh "<câu hỏi>" [conversation_id]`.

| Sự kiện | Dữ liệu | Khi nào |
|---|---|---|
| `guardrail` | `{stage: input\|output, action: block\|warn\|redact, kind, message, reasons?, numbers?, citations?}` | Guardrail chặn (lượt kết thúc ngay, không gọi LLM), cảnh báo, hoặc che nội dung |
| `memory` | `{window_turns, summary_used, retrieved:[{turn_no, score, text}]}` | Đầu lượt (bật/tắt bằng `DEBUG_MEMORY_EVENTS`) |
| `tool_call` | `{id, name, args}` | LLM yêu cầu gọi tool |
| `data` | `{data_id, kind, bbox, summary, tool_call_id}` | Tool có dữ liệu bản đồ; tải qua `GET /map-data/{data_id}` |
| `tool_result` | `{id, name, ok, summary, evidence_id}` | Tool chạy xong; `ok=false` kèm `summary.error` |
| `evidence` | `{id, tool, label, ok, query, sources, facts:[{label, value}], data_ids}` | Chứng cứ của lần gọi tool vừa rồi (mã `E#` liên tục trong hội thoại) |
| `token` | `{text}` | Từng mảnh câu trả lời |
| `verification` | `{numbers_checked, ungrounded_numbers, citations, unknown_citations, evidence_count, auto_cited, grounded}` | Sau câu trả lời: kết quả đối chiếu số liệu và mã chứng cứ |
| `error` | `{code, message}` | `llm_rate_limited`, `llm_unavailable`, `llm_error`, `internal_error`; stream vẫn kết thúc bằng `done` |
| `done` | `{message_id, turn, usage, data_ids}` | Kết thúc lượt |

Ví dụ một lượt (đã rút gọn):

```
event: memory
data: {"window_turns": [2, 3], "summary_used": false, "retrieved": [{"turn_no": 1, "score": 0.526, "text": "Lượt 1\nNgười dùng: Cho tôi thông tin về tàu KOTA GAYA.…"}]}

event: tool_call
data: {"id": "call_x1", "name": "get_position_at", "args": {"vessel": "KOTA GAYA", "timestamp": "2026-09-11T21:00:00Z"}}

event: data
data: {"data_id": "b0da4228-…", "kind": "position", "bbox": [113.88425, 21.63939, 114.08408, 21.79336], "summary": {"vessel": {"name": "KOTA GAYA", …}, "requested_ts": "2026-09-11T21:00:00Z", "status": "ok"}, "tool_call_id": "call_x1"}

event: tool_result
data: {"id": "call_x1", "name": "get_position_at", "ok": true, "summary": {"status": "ok", "method": "interpolated", "nearest_offset_minutes": 33.1, "vessel": "KOTA GAYA"}, "evidence_id": "E4"}

event: evidence
data: {"id": "E4", "tool": "get_position_at", "label": "Vị trí theo thời điểm KOTA GAYA", "ok": true, "query": {"vessel": "KOTA GAYA", "timestamp": "2026-09-11T21:00:00Z"}, "sources": ["ais_positions", "dark_gaps"], "facts": [{"label": "Kết quả", "value": "interpolated"}, {"label": "Vị trí", "value": "21.74504, 114.02137"}, {"label": "Điểm trước", "value": "2026-09-11T19:47:42Z (21.63939, 113.88425), 8.4 knot, Under way · lệch 72.3 phút"}, …], "data_ids": ["b0da4228-…"]}

event: token
data: {"text": "Lúc 21:00 ngày 11/09/2026 (UTC), tàu KOTA GAYA ở vĩ độ 21.74504, "}
…
event: verification
data: {"numbers_checked": 4, "ungrounded_numbers": [], "citations": ["E4"], "unknown_citations": [], "evidence_count": 1, "auto_cited": false, "grounded": true}

event: done
data: {"message_id": 17, "turn": 4, "usage": {"prompt_tokens": 11675, "completion_tokens": 223}, "data_ids": ["b0da4228-…"]}
```

Server gửi comment `: ping` mỗi 15 giây để giữ kết nối qua proxy. Guardrail đầu ra giữ lại khoảng 120 ký tự cuối trước khi gửi (để che secret vắt qua nhiều token), nên câu trả lời rất ngắn có thể đến trong một sự kiện `token`.

Ví dụ yêu cầu bị chặn:

```
event: guardrail
data: {"stage": "input", "action": "block", "kind": "prompt_injection", "message": "Yêu cầu bị chặn bởi guardrail đầu vào.", "reasons": ["yêu cầu bỏ qua chỉ dẫn (VI)", "nhắc tới prompt hệ thống"]}

event: token
data: {"text": "Mình không thể thực hiện yêu cầu này. …"}

event: done
data: {"message_id": 58, "turn": 4, "usage": {"prompt_tokens": 0, "completion_tokens": 0}, "data_ids": []}
```

## Bản đồ và hành trình

### `GET /map-data/{data_id}`

```json
{"id": "…", "conversation_id": "…", "kind": "track",
 "summary": {"vessel": {…}, "distance_nm": 449.39, "point_count": 107},
 "bbox": [106.98844, 6.80919, 111.21471, 12.9847],
 "geojson": {"type": "FeatureCollection", "features": [
   {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[106.98844, 6.80919], …]},
    "properties": {"kind": "track", "name": "EVER VIVA", "distance_nm": 449.39}},
   {"type": "Feature", "geometry": {"type": "Point", …}, "properties": {"kind": "track_start", "ts": "…"}},
   {"type": "Feature", "geometry": {"type": "Point", …}, "properties": {"kind": "track_end", "ts": "…"}}]}}
```

Các giá trị `kind` của lớp và `properties.kind` của feature bên trong:

| `kind` của lớp | `properties.kind` |
|---|---|
| `position` | `position` (vị trí trả lời), `reference` (điểm AIS trước/sau) |
| `track` | `track` (LineString, hoặc MultiLineString khi có khe), `track_start`, `track_end` |
| `gaps` | `gap_start`, `gap_end`, `gap_link` (đoạn nối mất → có lại) |
| `tracks` | `track` với `vessel_id`, `name`, `mmsi`, `distance_nm`, `point_count`, `avg_speed_knots`, `color_index` |

### `GET /tracks`: nhiều hành trình (N3)

| Tham số | Ý nghĩa |
|---|---|
| `start`, `end` (bắt buộc) | Khoảng thời gian; `end` chỉ ghi ngày nghĩa là hết ngày đó |
| `vessel` (lặp lại được) | Tên, MMSI, IMO hoặc vessel_id |
| `company` + `role` | Lọc theo công ty; `role` là `registered_owner`, `beneficial_owner`, `operator`, `commercial_manager`, `technical_manager` hoặc `ism_manager` |
| `ship_type_group` | `tanker`, `cargo`, `fishing`, `tug`, `passenger`, `high_speed`, `pleasure`, `special`, `other` hoặc `unknown` |
| `limit` (≤ `MAX_TRACKS_PER_PAGE`), `offset` | Phân trang **theo tàu** |

```bash
curl -s "localhost:8000/tracks?start=2026-09-11&end=2026-09-11&company=Evergreen%20Marine%20Corp&role=operator&limit=2"
```

```json
{
  "type": "FeatureCollection",
  "features": [
    {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[114.39017, 22.53555], …]},
     "properties": {"vessel_id": "01822507-…", "name": "EVER ATOP", "mmsi": 563166100, "ship_type_group": "cargo",
                    "point_count": 74, "distance_nm": 225.81, "avg_speed_knots": 16.7, "gap_count": 0,
                    "kind": "track", "color_index": 0}},
    …
  ],
  "summary": {"vessels_with_data": 2, "total_points": 218, "rendered_points": 218, "removed_noise_points": 0,
              "downsampled": false, "bbox": [112.74679, 19.3633, 114.5548, 22.53555], "total_distance_nm": 230.2,
              "time_range": {"start": "2026-09-11T00:00:00Z", "end": "2026-09-11T23:59:59Z"}, "vessels": […]},
  "pagination": {"offset": 0, "limit": 2, "total_vessels": 27, "next_offset": 2}
}
```

Khi tổng số điểm vượt `MULTI_TRACK_MAX_POINTS`, hệ thống giảm mẫu đều theo từng tàu (giữ điểm đầu và điểm cuối), và đặt `downsampled: true`. Thống kê quãng đường luôn tính trên toàn bộ điểm.

Mã lỗi:

| Mã | Khi nào |
|---|---|
| 422 | Thời gian sai định dạng hoặc `end` ≤ `start` |
| 404 | Không tìm thấy tàu hoặc công ty |
| 409 | Tên công ty mơ hồ; `detail.candidates` liệt kê các lựa chọn |

```json
{"detail": {"status": "ambiguous", "query": "evergreen", "candidates": [
  {"company": "EVERGREEN MARINE", "name_variants": ["EVERGREEN MARINE CORP"], "vessel_count": 31, …},
  {"company": "EVERGREEN MARINE ASIA", "name_variants": ["EVERGREEN MARINE ASIA PTE LTD"], "vessel_count": 14, …}]}}
```

### `GET /vessels/search?q=…&limit=10`

Tìm tàu theo tên (chịu sai chính tả), MMSI, IMO hoặc callsign. Mỗi kết quả có `score` và `match` (`name`, `mmsi`, `imo`, `callsign`, `id`).

### `GET /vessels/{vessel}/dark-gaps?start=&end=&limit=`

Trả FeatureCollection các lần mất tín hiệu, kèm `summary` (cùng nội dung với kết quả tool `get_dark_gaps`).

## Hệ thống

### `GET /health`

```json
{"status": "ok", "vessels": 1000, "knowledge_chunks": 31, "model": "gpt-4o-mini", "memory_window_turns": 6, "auth_required": true, "login_enabled": true}
```

`login_enabled` cho giao diện biết có cần hiện form đăng nhập hay không.

### `GET /stats?range=7d`

Số liệu vận hành cho trang Thống kê. `range`: `24h`, `7d` (mặc định), `30d`, `all`. Dùng chung API key và rate limit với các route khác; tắt bằng `STATS_ENABLED=false`.

```bash
curl -s 'localhost:8000/stats?range=24h' | jq '.overview, .latency'
```

| Khối | Nội dung |
|---|---|
| `overview` | `turns`, `conversations`, `outcomes` (`ok`/`blocked`/`error`/`cancelled`), `success_rate`, token, `cost_usd`, `cost_per_turn_usd`, `tool_calls`, thời điểm lượt đầu/cuối |
| `latency` | `ttft_p50`, `ttft_p95`, `duration_p50`, `duration_p95` (giây), `measured_turns` |
| `daily` | Mỗi ngày (theo `STATS_TIMEZONE`): `turns`, `blocked`, `errors`, `cost_usd` |
| `tools` | Mỗi tool: `calls`, `ok`, `success_rate`, `cache_hit_rate`, `ms_p50`, `ms_p95` |
| `cache` | Tỉ lệ trúng cache và số mục đang cache |
| `quality` | Câu trả lời đã kiểm chứng, khớp dữ liệu, có trích chứng cứ, số con số đã đối chiếu, số câu tự gắn chứng cứ |
| `guardrails` | Đếm theo `stage`, `action`, `kind` |
| `rag` | Lượt tra kho tri thức, số tài liệu/đoạn, ký ức vector, hội thoại đã tóm tắt |
| `recent_turns` | 12 lượt gần nhất: câu hỏi, công cụ, kết quả, chứng cứ, độ trễ, token, chi phí |
| `data` | Quy mô dữ liệu nguồn (tàu, điểm AIS, dark gap, công ty, nhóm loại tàu); cache `STATS_INVENTORY_TTL_SECONDS` |
| `evaluation` | Tóm tắt `EVAL_REPORT_PATH` (tỉ lệ đạt theo nhóm, chi phí, độ trễ) hoặc `null` |
| `runtime` | Mô hình, embedding, cửa sổ bộ nhớ, guardrail, xác thực, rate limit, giá token, thời điểm khởi động |

Chi phí tính từ token đã lưu theo `PRICE_INPUT_PER_M` / `PRICE_OUTPUT_PER_M`.

### `GET /metrics`

Định dạng Prometheus. Các chỉ số chính: `vc_http_requests_total{method,route,status}`, `vc_http_request_seconds`, `vc_chat_turns_total{outcome}`, `vc_chat_first_token_seconds`, `vc_chat_turn_seconds`, `vc_llm_tokens_total{kind}`, `vc_llm_cost_usd_total`, `vc_tool_calls_total{tool,ok,cache}`, `vc_tool_seconds{tool}`, `vc_guardrail_events_total{stage,kind,action}`, `vc_rate_limited_total{limiter}`, `vc_auth_events_total{event}` (`login_ok`, `login_failed`, `rejected`), `vc_rag_queries_total{hits}`.
