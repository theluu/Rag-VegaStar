"""Chứng cứ cho câu trả lời.

Mỗi lần gọi tool tạo một chứng cứ có mã (E1, E2… đánh số liên tục trong hội thoại): tool nào, tham số gì,
đọc từ bảng/tài liệu nào và các giá trị gốc chính. LLM trích mã trong câu trả lời ([E1]); client hiển thị
chi tiết để người dùng tự kiểm chứng.
"""

import re

from ..tools import ToolResult

_LABELS = {
    "search_vessels": "Tìm tàu",
    "list_vessels": "Danh sách tàu",
    "get_vessel_details": "Hồ sơ tàu",
    "find_company_vessels": "Đội tàu của công ty",
    "get_position_at": "Vị trí theo thời điểm",
    "get_last_position": "Vị trí cuối cùng",
    "get_track": "Hành trình",
    "get_dark_gaps": "Mất tín hiệu AIS",
    "get_multi_tracks": "Nhiều hành trình",
    "search_knowledge": "Kho tri thức",
}

_SOURCES = {
    "search_vessels": ["vessels"],
    "list_vessels": ["vessels"],
    "get_vessel_details": ["vessels", "ownership", "ais_positions", "dark_gaps"],
    "find_company_vessels": ["ownership", "vessels"],
    "get_position_at": ["ais_positions", "dark_gaps"],
    "get_last_position": ["ais_positions"],
    "get_track": ["ais_positions"],
    "get_dark_gaps": ["dark_gaps", "ais_positions"],
    "get_multi_tracks": ["ownership", "vessels", "ais_positions"],
}

_ROLE_LABELS = {
    "registered_owner": "Chủ sở hữu đăng ký",
    "beneficial_owner": "Chủ sở hữu hưởng lợi",
    "operator": "Nhà khai thác",
    "commercial_manager": "Quản lý thương mại",
    "technical_manager": "Quản lý kỹ thuật",
    "ism_manager": "Quản lý ISM",
}

MAX_LIST = 15


def _fmt(v) -> str:
    if v is None:
        return "không có"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _point(p: dict | None) -> str:
    if not p:
        return "không có"
    text = f"{p['ts']} ({p['lat']}, {p['lon']})"
    if p.get("speed_knots") is not None:
        text += f", {p['speed_knots']} knot"
    if p.get("nav_status"):
        text += f", {p['nav_status']}"
    return text


def _latlon(p: dict | None) -> str:
    return "không có" if not p else f"({p['lat']}, {p['lon']})"


def _vessel_name(c: dict) -> str:
    v = c.get("vessel") or {}
    return v.get("name") or ""


def _facts(tool: str, c: dict) -> list[tuple[str, str]]:
    if tool == "get_vessel_details":
        v = c["vessel"]
        out = [
            ("Tàu", v["name"]), ("MMSI", _fmt(v["mmsi"])), ("IMO", _fmt(v["imo"])), ("Hô hiệu", _fmt(v["callsign"])),
            ("Cờ", _fmt(v["flag"])), ("Loại (AIS)", _fmt(v["ship_type_summary"])),
            ("Loại (đăng kiểm)", _fmt(v["ship_type_detail"])),
            ("Kích thước", f"{_fmt(v['length_m'])} × {_fmt(v['width_m'])} m"),
            ("DWT", _fmt(v["deadweight_tonnes"])), ("GT", _fmt(v["gross_tonnage"])), ("Năm đóng", _fmt(v["year_built"])),
        ]
        for co in c["companies"]:
            out.append((_ROLE_LABELS.get(co["role"], co["role"]), f"{co['company_name']} ({co['company_country']})"))
        if not c["companies"]:
            out.append(("Chủ sở hữu", "không có dữ liệu"))
        a = c["ais_summary"]
        out += [("Số điểm AIS", _fmt(a["position_count"])), ("AIS từ", _fmt(a["first_ts"])),
                ("AIS đến", _fmt(a["last_ts"])), ("Số lần mất tín hiệu", _fmt(a["dark_gap_count"]))]
        return out
    if tool == "find_company_vessels":
        names = [f"{v['name']} ({v['mmsi']})" for v in c["vessels"][:MAX_LIST]]
        return [
            ("Công ty", ", ".join(c["name_variants"])),
            ("Vai trò", _ROLE_LABELS.get(c["role_filter"], "mọi vai trò")),
            ("Số tàu", _fmt(c["vessel_count"])),
            ("Tàu", "; ".join(names) + (" …" if c["vessel_count"] > len(names) else "")),
        ]
    if tool == "get_position_at":
        out = [("Tàu", _vessel_name(c)), ("Thời điểm hỏi", c["requested_ts"]), ("Kết quả", c.get("method", c["status"]))]
        if c.get("position"):
            out.append(("Vị trí", f"{c['position']['lat']}, {c['position']['lon']}"))
        out += [
            ("Điểm trước", _point(c["before"]) + (f" · lệch {_fmt(c['before_offset_minutes'])} phút" if c["before"] else "")),
            ("Điểm sau", _point(c["after"]) + (f" · lệch {_fmt(c['after_offset_minutes'])} phút" if c["after"] else "")),
        ]
        if c.get("in_dark_gap"):
            g = c["in_dark_gap"]
            out.append(("Trong lần mất tín hiệu", f"{g['gap_start_ts']} → {g['gap_end_ts']}"))
        return out
    if tool == "get_last_position":
        return [("Tàu", _vessel_name(c)), ("Điểm cuối", _point(c.get("position")))]
    if tool == "get_track":
        if c.get("status") != "ok":
            return [("Tàu", _vessel_name(c)), ("Kết quả", c.get("message", c.get("status")))]
        tr = c["time_range"]
        return [
            ("Tàu", _vessel_name(c)), ("Khoảng thời gian", f"{tr['start']} → {tr['end']}"),
            ("Điểm AIS đọc được", _fmt(c["raw_point_count"])), ("Điểm nhiễu đã loại", _fmt(c["removed_noise_points"])),
            ("Số điểm dùng", _fmt(c["point_count"])),
            ("Điểm đầu", _point(c["start"])), ("Điểm cuối", _point(c["end"])),
            ("Quãng đường", f"{_fmt(c['distance_nm'])} hải lý (qua khe: {_fmt(c['gap_distance_nm'])})"),
            ("Thời lượng", f"{_fmt(c['duration_hours'])} giờ"),
            ("Tốc độ trung bình", f"{_fmt(c['avg_speed_knots'])} knot"),
            ("Khe không dữ liệu", _fmt(len(c["gaps"]))),
        ]
    if tool == "get_dark_gaps":
        out = [("Phạm vi", _vessel_name(c) or "toàn bộ đội tàu"), ("Số sự kiện khớp", _fmt(c["total_matching"]))]
        for g in c["gaps"][:5]:
            before = (g.get("speed_before_gap") or {}).get("speed_knots")
            out.append((
                f"Sự kiện {g['gap_id'][:8]}",
                f"{g['vessel']['name']}: {g['gap_start_ts']} → {g['gap_end_ts']} ({g['duration_text']}), "
                f"mất tại {_latlon(g['start_position'])}, có lại tại {_latlon(g['end_position'])}, "
                f"tốc độ trước khi mất {_fmt(before)} knot",
            ))
        return out
    if tool == "get_multi_tracks":
        f = c["filters"]
        out = [
            ("Bộ lọc", f"công ty={_fmt(f['company'])}, vai trò={_fmt(f['role'])}, loại={_fmt(f['ship_type_group'])}"),
            ("Khoảng thời gian", f"{f['start']} → {f['end']}"),
            ("Tàu khớp / có dữ liệu", f"{c['matched_vessels']} / {c['vessels_with_data']}"),
            ("Tổng số điểm", _fmt(c["total_points"])),
            ("Tổng quãng đường", f"{_fmt(c['total_distance_nm'])} hải lý"),
        ]
        for i, v in enumerate(c["top_by_distance"][:5], start=1):
            out.append((f"Xa thứ {i}", f"{v['name']} ({v['mmsi']}): {_fmt(v['distance_nm'])} hải lý"))
        return out
    if tool == "list_vessels":
        f = c["filters"]
        page = c["page"]
        names = [f"{v['name']} ({v['mmsi']})" for v in c["vessels"][:MAX_LIST]]
        return [
            ("Bộ lọc", f"loại={_fmt(f['ship_type_group'])}, cờ={_fmt(f['flag'])}, tên chứa={_fmt(f['name_contains'])}"),
            ("Tổng số tàu trong dữ liệu", _fmt(c["dataset_vessel_count"])),
            ("Số tàu khớp", _fmt(c["matching_vessel_count"])),
            ("Theo loại", ", ".join(f"{g['label_vi']} {g['count']}" for g in c["by_ship_type_group"])),
            ("Cờ nhiều nhất", ", ".join(f"{x['name']} {x['count']}" for x in c["top_flags"][:5])),
            (f"Tàu {page['offset'] + 1}–{page['offset'] + page['returned']}" if page["returned"] else "Tàu",
             "; ".join(names) + (" …" if page["returned"] > len(names) or c["has_more"] else "")),
        ]
    if tool == "search_vessels":
        return [("Số kết quả", _fmt(c["count"]))] + [
            (r["name"], f"MMSI {r['mmsi']}, {r['flag']}") for r in c["results"][:MAX_LIST]
        ]
    if tool == "search_knowledge":
        return [(r["citation"], r["text"][:240]) for r in c.get("results", [])]
    return []


def build_evidence(evidence_id: str, tool: str, args: dict | str, result: ToolResult) -> dict:
    c = result.content
    if "error" in c:
        facts = [("Lỗi", str(c["error"]))]
    elif c.get("status") in ("not_found", "ambiguous", "no_results") or (
        c.get("status") == "no_data" and tool not in ("get_track",)
    ):
        facts = [("Kết quả", c.get("message", c["status"]))]
        for cand in c.get("candidates", [])[:MAX_LIST]:
            name = cand.get("name") or cand.get("company")
            facts.append(("Ứng viên", f"{name} {cand.get('mmsi') or ''}".strip()))
    else:
        facts = _facts(tool, c)

    if tool == "search_knowledge":
        sources = sorted({r["citation"].split(" › ")[0] for r in c.get("results", [])}) or ["knowledge"]
        label = "Kho tri thức: " + c.get("query", "")
    else:
        sources = _SOURCES.get(tool, [])
        name = _vessel_name(c) if isinstance(c.get("vessel"), dict) else ""
        label = f"{_LABELS.get(tool, tool)} {name}".strip()

    return {
        "id": evidence_id,
        "tool": tool,
        "label": label,
        "ok": result.ok,
        "query": args,
        "sources": sources,
        "facts": [{"label": k, "value": v} for k, v in facts],
        "data_ids": [],
    }


_CITE = re.compile(r"\[(E\d+(?:\s*,\s*E\d+)*)\]")


def cited_ids(text: str) -> list[str]:
    out: list[str] = []
    for group in _CITE.findall(text):
        out.extend(x.strip() for x in group.split(","))
    return out
