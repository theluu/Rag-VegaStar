"""Chuẩn hoá tên tàu, tên công ty và nhóm loại tàu.

Dùng chung cho script nạp dữ liệu (ghi cột *_norm) và tầng truy vấn (chuẩn hoá câu hỏi),
để hai phía luôn so khớp trên cùng một dạng.
"""

import re

_NON_ALNUM = re.compile(r"[^0-9A-Z]+")

# Hậu tố pháp lý chỉ bị bỏ khi đứng ở CUỐI tên (lặp lại: "CO LTD" → bỏ cả hai)
LEGAL_SUFFIXES = {
    "CO", "COMPANY", "LTD", "LIMITED", "PTE", "PVT", "CORP", "CORPORATION", "INC",
    "INCORPORATED", "SA", "LLC", "GMBH", "AS", "ASA", "JSC", "BHD", "SDN", "PLC",
    "NV", "BV", "AG", "SPA", "SRL", "LTDA", "KK", "TBK", "LP", "LLP",
}


def _upper_tokens(s: str | None) -> list[str]:
    if not s:
        return []
    # Bỏ dấu chấm trước để "S.A." → "SA", "CORP." → "CORP"; các ký tự khác thành khoảng trắng
    s = s.upper().replace(".", "")
    return _NON_ALNUM.sub(" ", s).split()


def norm_name(s: str | None) -> str:
    return " ".join(_upper_tokens(s))


def norm_company(s: str | None) -> str:
    tokens = _upper_tokens(s)
    while len(tokens) > 1 and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


SHIP_TYPE_GROUPS = (
    "tanker", "cargo", "fishing", "tug", "passenger", "high_speed",
    "pleasure", "special", "other", "unknown",
)

_SPECIAL_KEYWORDS = (
    "dredg", "law enforcement", "pilot", "search and rescue", "offshore", "science",
    "research", "warship", "military", "medical", "port tender", "anti-pollution", "diving",
)


def ship_type_group(summary: str | None) -> str:
    """Gộp nhãn AIS (ITU-R M.1371) thành nhóm để người dùng hỏi bằng từ thông dụng."""
    s = (summary or "").strip().lower()
    if not s or s.startswith("not available") or s.startswith("reserved"):
        return "unknown"
    if s.startswith("tanker"):
        return "tanker"
    if s.startswith("cargo"):
        return "cargo"
    if s.startswith("fishing"):
        return "fishing"
    if s.startswith("tug") or s.startswith("towing"):
        return "tug"
    if s.startswith("passenger"):
        return "passenger"
    if s.startswith("hsc") or s.startswith("high speed"):
        return "high_speed"
    if s.startswith("pleasure") or s.startswith("sailing"):
        return "pleasure"
    if any(k in s for k in _SPECIAL_KEYWORDS):
        return "special"
    return "other"
