"""AI kiểm chứng độc lập (tuỳ chọn).

Sau khi trả lời xong, một model thứ hai (có thể của nhà cung cấp khác) đọc lại câu hỏi, câu trả lời và
dữ liệu tool đã truy vấn, rồi nêu ý kiến: câu trả lời có bám dữ liệu không, có gì sai hoặc thiếu.

Đây là lớp bổ sung cho kiểm chứng xác định (đối chiếu từng con số). Không cấu hình thì bỏ qua; model lỗi
hoặc trả về sai định dạng cũng không làm hỏng lượt trả lời.
"""

import asyncio
import json
import logging
import re

from ..config import Settings
from ..llm.client import LLMClient, OpenAILLM
from ..observability import LLM_PROVIDER_EVENTS

log = logging.getLogger(__name__)

VERDICTS = {"ok", "sai", "thieu", "khong_ro"}

SYSTEM = """Bạn là người kiểm tra độc lập cho một trợ lý tra cứu tàu biển. Bạn nhận: câu hỏi của người dùng, \
dữ liệu hệ thống đã truy vấn được (JSON rút gọn) và câu trả lời của trợ lý.

Nhiệm vụ: đối chiếu câu trả lời với dữ liệu. Chỉ dựa vào dữ liệu được cung cấp, không dùng kiến thức bên ngoài.

Trả về DUY NHẤT một JSON:
{"verdict": "ok" | "sai" | "thieu" | "khong_ro", "issues": ["..."], "note": "một câu tiếng Việt"}
- ok: mọi khẳng định trong câu trả lời đều khớp dữ liệu.
- sai: có ít nhất một con số, tên hoặc thời điểm mâu thuẫn với dữ liệu.
- thieu: không sai nhưng bỏ sót thông tin quan trọng có trong dữ liệu (vd. cảnh báo thiếu dữ liệu, nội suy).
- khong_ro: dữ liệu không đủ để kết luận.
issues: tối đa 3 mục ngắn gọn; để rỗng nếu verdict là ok."""


def _json_object(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


class SecondOpinion:
    """Gọi model kiểm chứng; trả về None khi tắt hoặc khi có sự cố."""

    def __init__(self, settings: Settings, llm: LLMClient | None = None):
        self.settings = settings
        self.enabled = bool(llm) or settings.verifier_enabled
        self.llm = llm
        if self.llm is None and settings.verifier_enabled:
            self.llm = OpenAILLM(
                settings,
                api_key=settings.verifier_llm_api_key,
                base_url=settings.verifier_llm_base_url,
                model=settings.verifier_llm_model,
                name="verifier",
            )

    @property
    def model(self) -> str:
        return getattr(self.llm, "model", "") if self.enabled else ""

    async def review(self, question: str, answer: str, evidence: list[dict]) -> dict | None:
        if not self.enabled or not answer.strip() or self.llm is None:
            return None
        payload = json.dumps(
            [{"evidence_id": e["id"], "tool": e["tool"], "ok": e["ok"],
              "facts": {f["label"]: f["value"] for f in e["facts"]}} for e in evidence],
            ensure_ascii=False,
        )[: self.settings.verifier_max_evidence_chars]
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"# Câu hỏi\n{question}\n\n# Dữ liệu đã truy vấn\n{payload}\n\n"
                                        f"# Câu trả lời của trợ lý\n{answer}"},
        ]
        try:
            raw = await asyncio.wait_for(
                self.llm.complete(messages, max_tokens=300), timeout=self.settings.verifier_timeout_seconds
            )
        except (TimeoutError, asyncio.TimeoutError):
            LLM_PROVIDER_EVENTS.labels("verifier_timeout").inc()
            log.warning("AI kiểm chứng quá thời gian chờ")
            return None
        except Exception:  # noqa: BLE001 — kiểm chứng phụ không bao giờ làm hỏng lượt trả lời
            LLM_PROVIDER_EVENTS.labels("verifier_error").inc()
            log.exception("AI kiểm chứng lỗi")
            return None

        data = _json_object(raw)
        if data is None:
            LLM_PROVIDER_EVENTS.labels("verifier_unparsed").inc()
            return None
        verdict = str(data.get("verdict", "")).strip().lower()
        if verdict not in VERDICTS:
            verdict = "khong_ro"
        issues = [str(x)[:200] for x in (data.get("issues") or [])][:3]
        LLM_PROVIDER_EVENTS.labels(f"verifier_{verdict}").inc()
        return {
            "model": self.model,
            "verdict": verdict,
            "agrees": verdict == "ok",
            "issues": issues,
            "note": str(data.get("note", ""))[:300],
        }
