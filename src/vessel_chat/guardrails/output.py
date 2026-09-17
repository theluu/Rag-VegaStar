"""Guardrail đầu ra.

- OutputGuard: lọc luồng token trước khi tới client — che chuỗi giống secret và chặn việc lặp lại
  system prompt. Giữ lại một đoạn đuôi (HOLD ký tự) để bắt được mẫu nằm vắt qua nhiều token.
- find_ungrounded_numbers: sau khi trả lời xong, mọi con số "có nghĩa" trong câu trả lời phải truy được
  về kết quả tool / ngữ cảnh (cho phép làm tròn, hiệu/tổng/tỉ lệ và đổi đơn vị thường gặp).
"""

import json
import math
import re
from dataclasses import dataclass
from itertools import combinations

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"\b(?:postgres(?:ql)?|mysql|redis|mongodb(?:\+srv)?)://\S+"),
    re.compile(r"\b(?:OPENAI_API_KEY|POSTGRES_PASSWORD|API_KEYS)\s*=\s*\S+"),
]
REDACTED = "[đã ẩn]"
LEAK_NOTICE = "[đã ẩn nội dung cấu hình hệ thống]"
LEAK_WINDOW = 48


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


class OutputGuard:
    HOLD = 120
    MAX_PENDING = 2000

    def __init__(self, system_prompt: str):
        collapsed = _collapse(system_prompt)
        self._shingles = {collapsed[i:i + LEAK_WINDOW] for i in range(0, max(0, len(collapsed) - LEAK_WINDOW + 1))}
        self._pending = ""
        self.leaked = False
        self.events: list[dict] = []

    def _redact(self) -> None:
        for pattern in SECRET_PATTERNS:
            self._pending, n = pattern.subn(REDACTED, self._pending)
            if n:
                self.events.append({"kind": "secret", "count": n})

    def _leak_detected(self) -> bool:
        if not self._shingles:
            return False
        text = _collapse(self._pending)
        return any(text[i:i + LEAK_WINDOW] in self._shingles for i in range(0, len(text) - LEAK_WINDOW + 1))

    def _check(self) -> str | None:
        """Trả thông báo thay thế nếu phát hiện rò rỉ (và từ đó bỏ toàn bộ phần còn lại)."""
        self._redact()
        if self._leak_detected():
            self.leaked = True
            self._pending = ""
            self.events.append({"kind": "system_prompt_leak"})
            return LEAK_NOTICE
        return None

    def push(self, chunk: str) -> str:
        if self.leaked:
            return ""
        self._pending += chunk
        notice = self._check()
        if notice is not None:
            return notice
        safe = len(self._pending) - self.HOLD
        if safe <= 0:
            return ""
        cut = max(self._pending.rfind(" ", 0, safe), self._pending.rfind("\n", 0, safe)) + 1
        if cut <= 0:
            if len(self._pending) < self.MAX_PENDING:
                return ""
            cut = safe
        out, self._pending = self._pending[:cut], self._pending[cut:]
        return out

    def flush(self) -> str:
        if self.leaked:
            return ""
        notice = self._check()
        if notice is not None:
            return notice
        out, self._pending = self._pending, ""
        return out


# ------------------------------------------------------------------ kiểm tra số liệu

_DATE_TIME = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?Z?)?"
    r"|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"
    r"|\b\d{1,2}:\d{2}(?::\d{2})?\b"
)
_NUMBER_TOKEN = re.compile(r"(?<![\w\-])\d[\d.,]*\d(?![\w\-])|(?<![\w\-.,])\d(?![\w\-.,]|[.,]\d)")


@dataclass
class AnswerNumber:
    text: str
    values: list[tuple[float, int]]  # (giá trị, số chữ số thập phân) theo các cách hiểu có thể


def _interpret(token: str) -> list[tuple[float, int]]:
    """Các cách hiểu một chuỗi số kiểu Việt/Anh: 39,598 · 449,39 · 1.077,66 · 18.81."""
    if "," in token and "." in token:
        dec = "," if token.rfind(",") > token.rfind(".") else "."
        thou = "." if dec == "," else ","
        whole, frac = token.replace(thou, "").split(dec)
        return [(float(f"{whole}.{frac}"), len(frac))]
    for sep in (",", "."):
        if sep in token:
            parts = token.split(sep)
            out = []
            if len(parts) == 2:
                out.append((float(f"{parts[0]}.{parts[1]}"), len(parts[1])))
            if all(len(p) == 3 for p in parts[1:]) and 1 <= len(parts[0]) <= 3:
                out.append((float("".join(parts)), 0))
            return out
    return [(float(token), 0)]


def extract_answer_numbers(text: str) -> list[AnswerNumber]:
    cleaned = _DATE_TIME.sub(" ", text)
    out = []
    for m in _NUMBER_TOKEN.finditer(cleaned):
        token = m.group(0)
        values = _interpret(token)
        if not values:
            continue
        # Bỏ số nguyên nhỏ (1–99): số thứ tự, "3 ngày", "2 lần"… quá dễ trùng để có ý nghĩa kiểm tra
        if all(d == 0 and abs(v) < 100 for v, d in values):
            continue
        out.append(AnswerNumber(token, values))
    return out


_SOURCE_TOKEN = re.compile(r"\d[\d.,]*\d|\d")


def source_numbers(texts: list[str]) -> list[float]:
    """Mọi giá trị số trong nguồn (kết quả tool dạng JSON, câu hỏi, ngữ cảnh)."""
    values: set[float] = set()

    def walk(obj) -> None:
        if isinstance(obj, bool):
            return
        if isinstance(obj, (int, float)):
            values.add(float(obj))
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
        elif isinstance(obj, str):
            scan(obj)

    def scan(text: str) -> None:
        for token in _SOURCE_TOKEN.findall(text):
            for v, _ in _interpret(token):
                values.add(v)
            for part in re.split(r"[.,]", token):
                if part:
                    values.add(float(part))

    for text in texts:
        try:
            walk(json.loads(text))
        except (ValueError, TypeError):
            scan(text)
    return sorted(values)


# Đổi đơn vị thường gặp: hải lý↔km, knot↔km/h, giây↔phút↔giờ
_FACTORS = (1.0, 1.852, 1 / 1.852, 60.0, 1 / 60, 3600.0, 1 / 3600, 24.0, 1 / 24)
MAX_PAIR_SOURCES = 400


def _close(a: float, b: float, decimals: int, rel: float = 0.0) -> bool:
    return abs(a - b) <= max(0.5 * 10 ** -decimals + 1e-9, rel * abs(a))


def _grounded(values: list[tuple[float, int]], sources: list[float], pairs: list[float]) -> bool:
    for v, d in values:
        for s in sources:
            if _close(v, s, d):
                return True
            if any(_close(v, s * f, d, rel=0.002) for f in _FACTORS[1:]):
                return True
        if any(_close(v, p, d) for p in pairs):
            return True
    return False


def _derived(sources: list[float]) -> list[float]:
    base = [s for s in sources if abs(s) >= 1][:MAX_PAIR_SOURCES]
    out = []
    for a, b in combinations(base, 2):
        out.extend((a + b, abs(a - b)))
        if b:
            out.append(a / b * 100)
        if a:
            out.append(b / a * 100)
    return [x for x in out if math.isfinite(x)]


def find_ungrounded_numbers(answer: str, sources: list[float]) -> list[str]:
    numbers = extract_answer_numbers(answer)
    if not numbers:
        return []
    pairs: list[float] | None = None
    missing = []
    for n in numbers:
        if _grounded(n.values, sources, []):
            continue
        if pairs is None:
            pairs = _derived(sources)
        if not _grounded(n.values, [], pairs):
            missing.append(n.text)
    return missing
