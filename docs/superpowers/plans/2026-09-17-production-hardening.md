# Production Hardening Implementation Plan

> Spec: `docs/superpowers/specs/2026-09-17-production-hardening-design.md`. Mỗi task: test trước → code → test xanh → commit.

- [ ] **Task 1 — Nền tảng security/ops:** middleware request id + security headers + body limit + gzip; API key tuỳ chọn; rate limiter token-bucket; `/metrics` (prometheus_client); log JSON mỗi lượt; pool tool chỉ đọc; Dockerfile user không root. Test: `tests/unit/test_security.py`, `tests/integration/test_security_api.py`.
- [ ] **Task 2 — Tối ưu:** cache kết quả tool (LRU+TTL), `get_dark_gaps` LATERAL, cache HTTP `/map-data`. Test: `tests/unit/test_tool_cache.py`, cập nhật test gaps.
- [ ] **Task 3 — Guardrails:** `guardrails/input.py` (injection, moderation), `guardrails/output.py` (grounding, redaction), tích hợp ChatService + sự kiện `guardrail`. Test: `tests/unit/test_guardrails.py`, integration chặn/cảnh báo.
- [ ] **Task 4 — RAG:** `knowledge/*.md`, schema `kb_chunks`, `rag/chunker.py`, `rag/store.py` (hybrid RRF), `scripts/ingest_knowledge.py`, tool `search_knowledge`, prompt trích dẫn. Test: `tests/unit/test_rag.py`.
- [ ] **Task 5 — Harness:** `evals/generate.py`, `evals/cases.static.yaml`, `evals/run.py`, báo cáo `results/eval_report.*`. Chạy thật với OpenAI.
- [ ] **Task 6 — Frontend + SEO/GEO:** hiển thị guardrail/trích dẫn, gửi API key; meta/OG/JSON-LD, robots, sitemap, manifest, og-image, llms.txt; nginx CSP.
- [ ] **Task 7 — Tài liệu:** `SECURITY.md`, cập nhật README, architecture, research, api, `.env.example`; clean-install Docker; push.
