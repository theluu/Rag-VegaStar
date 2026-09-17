"""Chạy các kịch bản hội thoại qua API thật (SSE) và ghi transcript vào results/.

    python scripts/run_scenarios.py                       # mọi kịch bản
    python scripts/run_scenarios.py --only s3_long_memory
    python scripts/run_scenarios.py --api-url http://localhost:8000

Mỗi lượt ghi lại: câu hỏi, tool đã gọi (tên + tham số), tóm tắt kết quả tool, dữ liệu bản đồ,
ký ức được truy xuất, câu trả lời, độ trễ (token đầu tiên / toàn bộ) và số token.
"""

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from vessel_chat.client_auth import add_auth_arguments, auth_headers

ROOT = Path(__file__).resolve().parent.parent


async def stream_turn(client: httpx.AsyncClient, conv_id: str, message: str) -> dict:
    record = {"question": message, "tool_calls": [], "tool_results": [], "data": [], "memory": None,
              "errors": [], "answer": "", "usage": None}
    started = time.perf_counter()
    first_token = None
    event, data_lines = None, []

    def handle(name: str, payload: dict) -> None:
        nonlocal first_token
        if name == "token":
            if first_token is None:
                first_token = time.perf_counter() - started
            record["answer"] += payload["text"]
        elif name == "tool_call":
            record["tool_calls"].append(payload)
        elif name == "tool_result":
            record["tool_results"].append(payload)
        elif name == "data":
            record["data"].append(payload)
        elif name == "memory":
            record["memory"] = payload
        elif name == "error":
            record["errors"].append(payload)
        elif name == "done":
            record["usage"] = payload.get("usage")

    async with client.stream("POST", f"/conversations/{conv_id}/chat", json={"message": message}) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
            elif not line.strip():
                if event and data_lines:
                    handle(event, json.loads("\n".join(data_lines)))
                event, data_lines = None, []
    record["first_token_s"] = round(first_token, 2) if first_token is not None else None
    record["total_s"] = round(time.perf_counter() - started, 2)
    return record


def render_markdown(scenario: dict, conv_id: str, health: dict, turns: list[dict]) -> str:
    out = [
        f"# {scenario['title']}",
        "",
        f"- Nguồn: `{scenario['source']}` · id: `{scenario['id']}` · conversation: `{conv_id}`",
        f"- Model: `{health.get('model')}` · MEMORY_WINDOW_TURNS = `{health.get('memory_window_turns')}`",
        f"- Chạy lúc: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "",
    ]
    for i, t in enumerate(turns, start=1):
        out += [f"## Lượt {i}", "", f"**Người dùng:** {t['question']}", ""]
        mem = t.get("memory") or {}
        if mem.get("retrieved") or mem.get("summary_used"):
            got = ", ".join(f"lượt {r['turn_no']} ({r['score']})" for r in mem.get("retrieved", [])) or "—"
            out += [f"*Bộ nhớ:* cửa sổ nguyên văn = lượt {mem.get('window_turns')}, "
                    f"dùng tóm tắt = {mem.get('summary_used')}, ký ức vector = {got}", ""]
        if t["tool_calls"]:
            out.append("**Tool đã gọi:**")
            results = {r["id"]: r for r in t["tool_results"]}
            for c in t["tool_calls"]:
                r = results.get(c["id"], {})
                status = "ok" if r.get("ok") else "LỖI"
                out.append(f"- `{c['name']}({json.dumps(c['args'], ensure_ascii=False)})` → {status} "
                           f"`{json.dumps(r.get('summary', {}), ensure_ascii=False)}`")
            out.append("")
        for d in t["data"]:
            summ = {k: v for k, v in d["summary"].items() if k in ("vessels_with_data", "total_points",
                    "rendered_points", "distance_nm", "point_count", "count", "status")}
            out.append(f"*Bản đồ:* `{d['kind']}` data_id=`{d['data_id']}` bbox={d['bbox']} {json.dumps(summ, ensure_ascii=False)}")
        if t["data"]:
            out.append("")
        for e in t["errors"]:
            out.append(f"> ⚠️ error `{e.get('code')}`: {e.get('message')}")
        out += ["**Trợ lý:**", "", t["answer"].strip() or "_(trống)_", ""]
        usage = t.get("usage") or {}
        out += [f"<sub>token đầu tiên {t['first_token_s']}s · tổng {t['total_s']}s · "
                f"prompt {usage.get('prompt_tokens')} / completion {usage.get('completion_tokens')} token</sub>", ""]
    return "\n".join(out)


async def run(args) -> None:
    scenarios = yaml.safe_load((ROOT / "scenarios" / "scenarios.yaml").read_text(encoding="utf-8"))
    if args.only:
        scenarios = [s for s in scenarios if s["id"] in args.only]
    out_dir = ROOT / "results"
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)

    rows = []
    headers = await auth_headers(args.api_url, args.api_key, args.username, args.password)
    async with httpx.AsyncClient(base_url=args.api_url, headers=headers, timeout=httpx.Timeout(180, connect=10)) as client:
        health = (await client.get("/health")).raise_for_status().json()
        for sc in scenarios:
            conv = (await client.post("/conversations", json={"title": sc["title"]})).raise_for_status().json()
            turns = []
            for q in sc["turns"]:
                print(f"[{sc['id']}] {q}", flush=True)
                turns.append(await stream_turn(client, conv["id"], q))
            (out_dir / f"{sc['id']}.md").write_text(render_markdown(sc, conv["id"], health, turns), encoding="utf-8")
            with (out_dir / "raw" / f"{sc['id']}.jsonl").open("w", encoding="utf-8") as f:
                for t in turns:
                    f.write(json.dumps(t, ensure_ascii=False) + "\n")
            prompt = sum((t["usage"] or {}).get("prompt_tokens") or 0 for t in turns)
            completion = sum((t["usage"] or {}).get("completion_tokens") or 0 for t in turns)
            rows.append({
                "id": sc["id"], "title": sc["title"], "turns": len(turns),
                "tools": sum(len(t["tool_calls"]) for t in turns),
                "errors": sum(len(t["errors"]) for t in turns),
                "avg_first": round(sum(t["first_token_s"] or 0 for t in turns) / len(turns), 2),
                "avg_total": round(sum(t["total_s"] for t in turns) / len(turns), 2),
                "prompt": prompt, "completion": completion,
                "cost": prompt / 1e6 * args.price_in + completion / 1e6 * args.price_out,
            })

    if not args.only:
        lines = [
            "# Kết quả chạy kịch bản",
            "",
            f"Model `{health.get('model')}`, MEMORY_WINDOW_TURNS = `{health.get('memory_window_turns')}`. "
            f"Chi phí ước tính theo giá ${args.price_in}/1M token vào, ${args.price_out}/1M token ra.",
            "",
            "| Kịch bản | Lượt | Tool call | Lỗi | TTFT TB (s) | Thời gian TB (s) | Token vào | Token ra | Chi phí (USD) |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for r in rows:
            lines.append(f"| [{r['title']}]({r['id']}.md) | {r['turns']} | {r['tools']} | {r['errors']} | "
                         f"{r['avg_first']} | {r['avg_total']} | {r['prompt']:,} | {r['completion']:,} | {r['cost']:.4f} |")
        lines += ["", "Transcript đầy đủ từng sự kiện: `results/raw/*.jsonl`. Đáp án đối chiếu bằng SQL: "
                  "[facts.md](facts.md)."]
        (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Đã ghi transcript vào", out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-url", default=os.environ.get("API_URL", "http://localhost:8000"))
    parser.add_argument("--only", nargs="*", help="Chỉ chạy các id kịch bản này")
    add_auth_arguments(parser)
    parser.add_argument("--price-in", type=float, default=float(os.environ.get("PRICE_INPUT_PER_M", "0.15")),
                        help="USD / 1M token vào (mặc định giá gpt-4o-mini)")
    parser.add_argument("--price-out", type=float, default=float(os.environ.get("PRICE_OUTPUT_PER_M", "0.60")),
                        help="USD / 1M token ra")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
