# Vessel Chat: chatbot tra cứu tàu biển

Chatbot LLM trả lời câu hỏi tiếng Việt về 1.000 tàu (AIS 10–12/09/2026): tàu của ai, đang ở đâu, đã đi những đâu, có tắt AIS không.

- **API chat streaming (SSE).** Các sự kiện gồm `token`, `tool_call`, `tool_result`, `data`, `memory`, `error`, `done`.
- **Truy vấn có tham số.** LLM lấy số liệu qua 8 tool truy vấn PostgreSQL + PostGIS; không đưa CSV vào prompt, không để LLM tự viết SQL.
- **Bộ nhớ dài hạn.** Kết hợp trạng thái hội thoại, tóm tắt cuốn chiếu, truy xuất vector (pgvector) và cửa sổ nguyên văn cấu hình được.
- **Giao diện web.** Có danh sách hội thoại, câu trả lời hiện dần theo stream, và bản đồ MapLibre tự vẽ vị trí, hành trình, các lần mất tín hiệu và nhiều hành trình cùng lúc (hàng chục nghìn điểm).

| Tài liệu | Nội dung |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Kiến trúc, luồng xử lý, bộ nhớ, schema, tool, hạn chế, chi phí, hướng mở rộng |
| [docs/research.md](docs/research.md) | Lựa chọn LLM, embedding, vector DB, framework; so sánh các chiến lược bộ nhớ |
| [docs/api.md](docs/api.md) · [docs/openapi.json](docs/openapi.json) | Các endpoint và sự kiện SSE, kèm ví dụ `curl` |
| [results/](results/README.md) | Transcript chạy 5 kịch bản của đề và 4 biến thể; đáp án đối chiếu bằng SQL |

## Trạng thái yêu cầu

| Mã | Trạng thái | Ghi chú |
|---|---|---|
| R1 | ✅ | Script nạp chạy lại được nhiều lần (COPY → TRUNCATE + INSERT trong một transaction, ~8 giây); có chỉ mục GiST/B-tree/trigram. Tool dùng SQL có tham số. Tìm tàu theo tên (chịu sai chính tả), MMSI, IMO, callsign; nhiều kết quả thì hỏi lại. |
| R2 | ✅ | CRUD hội thoại; `POST /conversations/{id}/chat` stream SSE theo token; lỗi được báo qua sự kiện `error`, stream vẫn kết thúc bằng `done`. Các hội thoại chạy song song độc lập; có lệnh `curl` xem stream. |
| R3 | ✅ | Toàn bộ tin nhắn lưu trong Postgres. Giữ trạng thái đối tượng đang bàn để hiểu "nó", "tàu đó", "công ty đó". Tóm tắt + pgvector; `MEMORY_WINDOW_TURNS` cấu hình được. Kịch bản 3 chạy với cửa sổ 2 lượt. |
| R4 | ✅ | a) thông tin tàu và công ty theo vai trò, các tàu khác cùng chủ; b) vị trí gần nhất kèm độ lệch và **nội suy**; c) hành trình, quãng đường, tốc độ, GeoJSON; d) dark gap kèm tốc độ trước/sau khi mất. |
| N1 | ✅ | React + Vite: danh sách hội thoại, tạo mới/mở lại/xoá, hiển thị stream, nhật ký các lần gọi tool. |
| N2 | ✅ | Sự kiện `data` mang `data_id`; client tải GeoJSON từ `/map-data/{id}`. Câu nối tiếp "hiện thêm các lần tắt AIS của nó" thêm lớp mới lên bản đồ. |
| N3 | ✅ | `GET /tracks` trả FeatureCollection nhiều tàu, có phân trang. Hỏi qua chat ("hành trình tất cả tàu do X khai thác", "toàn bộ tàu cargo ngày 11/09"): 484 tàu, 35,7 nghìn điểm vẽ bằng WebGL. LLM chỉ nhận bản tóm tắt. |
| D1 | ✅ | README này, `.env.example` giải thích mọi biến, ví dụ `curl`. |
| D2 | ✅ | `docs/research.md`, `docs/architecture.md`. |
| D3 | ✅ | 112 test pytest (unit tầng truy vấn/tool/bộ nhớ và tích hợp API) + 6 test frontend; `results/` chứa transcript và đáp án SQL. |

## Yêu cầu hệ thống

- Docker 24+ và Docker Compose v2 (bắt buộc)
- Để chạy ngoài Docker và chạy test: Python 3.12+ và Node 20+
- OpenAI API key (mặc định dùng `gpt-4o-mini` và `text-embedding-3-small`). Có thể thay bằng endpoint tương thích OpenAI qua `OPENAI_BASE_URL`.
- 4 file CSV của đề đặt trong thư mục `data/`. Dữ liệu **không** nằm trong repo.

## Chạy nhanh bằng Docker

```bash
cp .env.example .env            # điền OPENAI_API_KEY, đổi POSTGRES_PASSWORD (và DATABASE_URL tương ứng)
# đặt vessels.csv, ais_positions.csv, dark_gaps.csv, ownership.csv vào ./data
docker compose up -d --build    # db (PostGIS + pgvector), api, web
docker compose run --rm api python scripts/load_data.py   # tạo schema + nạp dữ liệu (chạy lại không nhân đôi)
```

- Giao diện: http://localhost:5173
- API: http://localhost:8000 (tài liệu tương tác tại `/docs`)

Nếu cổng bị chiếm, đổi `DB_HOST_PORT`, `API_HOST_PORT`, `WEB_HOST_PORT` trong `.env`. Khi đổi cổng API, sửa luôn `VITE_API_BASE_URL` và `CORS_ORIGINS` rồi build lại `web`.

Để kiểm tra bộ nhớ dài hạn nhanh hơn, đặt `MEMORY_WINDOW_TURNS=2` trong `.env`, rồi chạy `docker compose up -d api`.

## Chạy ngoài Docker (phát triển)

```bash
docker compose up -d db
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python scripts/load_data.py
.venv/bin/uvicorn vessel_chat.api.app:app --reload --port 8000

cd frontend && npm ci
cp .env.example .env.local      # VITE_API_BASE_URL trỏ tới API
npm run dev                     # http://localhost:5173
```

## Xem stream trong terminal

```bash
scripts/stream_chat.sh "Cho tôi thông tin về tàu KOTA GAYA."                 # tạo hội thoại mới, in conversation_id
scripts/stream_chat.sh "Chủ sở hữu của tàu này là ai?" <conversation_id>     # hỏi tiếp
```

Hoặc dùng `curl` trực tiếp:

```bash
CID=$(curl -s -X POST localhost:8000/conversations -H 'Content-Type: application/json' -d '{}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -N -X POST localhost:8000/conversations/$CID/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "Tàu có MMSI 563240200 đã đi từ đâu đến đâu trong ngày 11/09/2026?"}'
```

Kết quả nhận được có dạng:

```
event: memory
data: {"window_turns": [], "summary_used": false, "retrieved": []}

event: tool_call
data: {"id": "call_…", "name": "get_track", "args": {"vessel": "563240200", "start": "2026-09-11T00:00:00Z", "end": "2026-09-11T23:59:59Z"}}

event: data
data: {"data_id": "7806b8ea-…", "kind": "track", "bbox": [106.98, 6.80, 111.21, 12.98], …}

event: tool_result
data: {"id": "call_…", "name": "get_track", "ok": true, "summary": {"status": "ok", "point_count": 107, "distance_nm": 449.39, "vessel": "EVER VIVA"}}

event: token
data: {"text": "Trong"}
…
event: done
data: {"message_id": 42, "turn": 1, "usage": {…}, "data_ids": ["7806b8ea-…"]}
```

Xem thêm ví dụ trong [docs/api.md](docs/api.md).

## Chạy test

Test dùng PostgreSQL thật: database `vessel_test` được container DB tạo sẵn ở lần khởi tạo đầu tiên. Dữ liệu test là một bộ nhỏ tự sinh trong `tests/fixtures`. LLM và embedding trong test là bản giả, nên **không gọi OpenAI**.

```bash
docker compose up -d db
.venv/bin/pytest -q              # 112 test: tầng truy vấn, tool, bộ nhớ, API/SSE
cd frontend && npm test          # bộ đọc SSE, dựng transcript
```

## Chạy lại kịch bản và đối chiếu đáp án

```bash
# API đang chạy (nên đặt MEMORY_WINDOW_TURNS=2)
.venv/bin/python scripts/run_scenarios.py --api-url http://localhost:8000     # → results/*.md, results/raw/*.jsonl
.venv/bin/python scripts/verify_facts.py                                     # → results/facts.md (SQL trực tiếp)
```

Các kịch bản nằm trong `scenarios/scenarios.yaml`. Để thử cách diễn đạt khác, chỉ cần thêm vào file này; code và prompt không chứa tên tàu hay đáp án nào.

## Cấu trúc

```
src/vessel_chat/
  config.py              cấu hình (env)
  loader.py, schema.sql  nạp dữ liệu và schema
  normalize.py, geo.py   chuẩn hoá tên, nhóm loại tàu; hình học hành trình
  repositories/          SQL có tham số (tàu, vị trí, dark gap, hội thoại, bộ nhớ, dữ liệu bản đồ)
  tools/                 8 tool cho LLM (schema Pydantic → JSON schema)
  llm/                   client OpenAI và prompt
  memory/manager.py      bộ nhớ kết hợp
  chat/service.py        vòng lặp LLM ↔ tool, phát sự kiện
  api/                   FastAPI
scripts/                 load_data.py, stream_chat.sh, run_scenarios.py, verify_facts.py
tests/                   unit + integration (+ fixtures)
frontend/                React + Vite + MapLibre
docs/                    research.md, architecture.md, api.md, openapi.json
results/                 transcript kịch bản, đáp án SQL
```

> Dữ liệu chỉ dùng cho bài test. `data/` và file đề đã nằm trong `.gitignore`.
