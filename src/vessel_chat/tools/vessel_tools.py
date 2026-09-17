from typing import Literal

from pydantic import BaseModel, Field

from ..repositories import gaps as gap_repo
from ..repositories import positions as pos_repo
from ..repositories import vessels as vessel_repo
from ..timeutil import iso
from .base import Tool, ToolContext, ToolResult, register
from .common import (
    VESSEL_ARG_DESC,
    Role,
    ShipTypeGroup,
    company_focus,
    resolve_company,
    resolve_vessel,
    vessel_brief,
    vessel_focus,
)


@register
class SearchVessels(Tool):
    name = "search_vessels"
    description = (
        "Tìm tàu theo tên (chịu sai chính tả), MMSI, IMO hoặc callsign. Dùng khi cần liệt kê các tàu khớp "
        "một tên chưa rõ ràng. Các tool khác đã tự tìm tàu nên không bắt buộc gọi tool này trước."
    )

    class Args(BaseModel):
        query: str = Field(description="Tên tàu, MMSI, IMO hoặc callsign")
        limit: int = Field(default=10, ge=1, le=30)

    async def run(self, ctx: ToolContext, args: Args) -> ToolResult:
        async with ctx.pool.acquire() as conn:
            rows = await vessel_repo.search_vessels(
                conn, args.query, limit=args.limit, threshold=ctx.settings.vessel_match_threshold
            )
        results = [
            {**vessel_brief(r), "flag": r["flag"], "ship_type": r["ship_type_summary"],
             "match": r["match"], "match_score": round(r["score"], 2)}
            for r in rows
        ]
        focus = vessel_focus(rows[0]) if len(rows) == 1 else {}
        return ToolResult(content={"count": len(results), "results": results}, focus=focus)


SHIP_GROUP_VI = {
    "cargo": "tàu hàng", "tanker": "tàu dầu/hoá chất/khí", "fishing": "tàu cá", "tug": "tàu kéo",
    "passenger": "tàu khách", "high_speed": "tàu cao tốc", "pleasure": "du thuyền/tàu buồm",
    "special": "tàu chuyên dụng", "other": "loại khác", "unknown": "chưa rõ loại",
}


@register
class ListVessels(Tool):
    name = "list_vessels"
    description = (
        "Đếm và liệt kê tàu trong bộ dữ liệu: tổng số tàu, số tàu theo nhóm loại và theo cờ, danh sách tên có phân "
        "trang. Lọc tuỳ chọn theo nhóm loại tàu, cờ, hoặc một phần tên. Dùng cho câu hỏi 'có bao nhiêu tàu', "
        "'liệt kê/kể tên các tàu', 'có những tàu cá nào', 'tàu treo cờ Panama'. Không vẽ bản đồ, không cần thời gian. "
        "Tàu của một công ty → dùng find_company_vessels."
    )

    class Args(BaseModel):
        ship_type_group: ShipTypeGroup | None = Field(default=None, description="Lọc theo nhóm loại tàu")
        flag: str | None = Field(default=None, description="Cờ: tên quốc gia tiếng Anh (vd. Panama, Singapore) "
                                                           "hoặc mã 2 chữ (PA, SG)")
        name_contains: str | None = Field(default=None, description="Một phần tên tàu (vd. 'EVER', 'MSC')")
        order_by: Literal["name", "dwt", "length", "year_built"] = Field(
            default="name", description="Sắp xếp: name = theo tên A→Z; dwt/length/year_built = lớn/mới nhất trước")
        limit: int = Field(default=20, ge=1, le=30, description="Số tàu mỗi trang (mặc định 20, tối đa 30)")
        offset: int = Field(default=0, ge=0, description="Bỏ qua bao nhiêu tàu (xem trang tiếp: dùng next_offset)")

    async def run(self, ctx: ToolContext, args: Args) -> ToolResult:
        flag = (args.flag or "").strip() or None
        name = (args.name_contains or "").strip() or None
        async with ctx.pool.acquire() as conn:
            total, rows = await vessel_repo.list_vessels(
                conn, args.ship_type_group, flag, name, args.order_by, args.limit, args.offset
            )
            breakdown = await vessel_repo.vessel_breakdown(conn, args.ship_type_group, flag, name, top_flags=10)

        filtered = any(x is not None for x in (args.ship_type_group, flag, name))
        next_offset = args.offset + len(rows)
        # Chỉ kèm thông số dùng để sắp xếp, giữ kết quả gọn cho LLM
        metric = {"dwt": "deadweight_tonnes", "length": "length_m", "year_built": "year_built"}.get(args.order_by)
        source = {"deadweight_tonnes": "dwt", "length_m": "length_m", "year_built": "year_built"}
        content = {
            "status": "ok" if total else "no_results",
            "filters": {"ship_type_group": args.ship_type_group, "flag": flag, "name_contains": name},
            "dataset_vessel_count": breakdown["dataset_total"],
            "matching_vessel_count": total,
            "unnamed_vessel_count": breakdown["unnamed"],
            "flag_count": breakdown["flag_count"],
            "by_ship_type_group": [
                {**g, "label_vi": SHIP_GROUP_VI.get(g["name"], g["name"])} for g in breakdown["by_ship_type_group"]
            ],
            "top_flags": breakdown["top_flags"],
            "order_by": args.order_by,
            "page": {
                "offset": args.offset,
                "returned": len(rows),
                "showing": f"{args.offset + 1}–{next_offset} / {total}" if rows else f"0 / {total}",
            },
            "vessels": [
                {"no": args.offset + i, **vessel_brief(r), "flag": r["flag"],
                 "type_vi": SHIP_GROUP_VI.get(r["ship_type_group"], r["ship_type_group"]),
                 **({metric: r[source[metric]]} if metric else {})}
                for i, r in enumerate(rows, start=1)
            ],
            "has_more": next_offset < total,
            "next_offset": next_offset if next_offset < total else None,
        }
        if not total:
            content["message"] = "Không có tàu nào khớp bộ lọc" if filtered else "Bộ dữ liệu chưa có tàu"
        return ToolResult(content=content)


@register
class GetVesselDetails(Tool):
    name = "get_vessel_details"
    description = (
        "Thông tin một tàu: mã nhận dạng (MMSI, IMO, callsign), cờ, loại tàu, kích thước, trọng tải, năm đóng, "
        "các công ty theo vai trò (registered_owner = chủ sở hữu đăng ký, beneficial_owner = chủ sở hữu hưởng lợi, "
        "operator = nhà khai thác, commercial_manager = quản lý thương mại, technical_manager = quản lý kỹ thuật, "
        "ism_manager = quản lý ISM) và tóm tắt dữ liệu AIS có sẵn."
    )

    class Args(BaseModel):
        vessel: str = Field(description=VESSEL_ARG_DESC)

    async def run(self, ctx: ToolContext, args: Args) -> ToolResult:
        async with ctx.pool.acquire() as conn:
            v, problem = await resolve_vessel(conn, ctx.settings, args.vessel)
            if problem:
                return ToolResult(content=problem)
            owners = await vessel_repo.get_ownership(conn, v["vessel_id"])
            ais = await pos_repo.vessel_ais_summary(conn, v["vessel_id"])
            gap_count = await gap_repo.count_gaps(conn, v["vessel_id"])

        vessel = {
            **vessel_brief(v),
            "callsign": v["callsign"],
            "flag_code": v["flag_code"],
            "flag": v["flag"],
            "ship_type_summary": v["ship_type_summary"],
            "ship_type_group": v["ship_type_group"],
            "ship_type_detail": v["ship_type_detail_name"],
            "length_m": v["length_m"],
            "width_m": v["width_m"],
            "deadweight_tonnes": v["dwt"],
            "gross_tonnage": v["grt"],
            "year_built": v["year_built"],
        }
        content = {
            "status": "ok",
            "vessel": vessel,
            "ownership_available": bool(owners),
            "companies": [
                {
                    "role": o["role"],
                    "company_name": o["company_name"],
                    "company_country": o["company_country"],
                    "start_date": o["start_date"].isoformat() if o["start_date"] else None,
                }
                for o in owners
            ],
            "ais_summary": {
                "position_count": ais["position_count"],
                "first_ts": iso(ais["first_ts"]),
                "last_ts": iso(ais["last_ts"]),
                "dark_gap_count": gap_count,
            },
        }
        if v.get("_matched_approximately"):
            content["note"] = f"Khớp gần đúng với truy vấn '{args.vessel}'; hãy nêu rõ tên tàu tìm được."

        focus = vessel_focus(v)
        registered = next((o for o in owners if o["role"] == "registered_owner"), None)
        if registered:
            focus["company"] = {"norm": registered["company_norm"], "name": registered["company_name"]}
        return ToolResult(content=content, focus=focus)


@register
class FindCompanyVessels(Tool):
    name = "find_company_vessels"
    description = (
        "Liệt kê các tàu có liên quan tới một công ty (tuỳ chọn lọc theo vai trò). Tên công ty được chuẩn hoá "
        "(bỏ hậu tố CO/LTD/PTE/CORP...) để gộp biến thể; các pháp nhân khác tên (vd. chi nhánh) KHÔNG bị gộp và "
        "được liệt kê ở similar_companies_not_included. Dùng exclude_vessel để bỏ tàu đang bàn khi hỏi 'tàu khác'."
    )

    class Args(BaseModel):
        company_name: str = Field(description="Tên công ty như trong dữ liệu hoặc người dùng nói")
        role: Role | None = Field(default=None, description="Chỉ lấy tàu mà công ty giữ vai trò này")
        exclude_vessel: str | None = Field(default=None, description="Tàu cần loại khỏi danh sách (vessel_id/tên/MMSI)")

    def cache_key(self, ctx: ToolContext, args: Args) -> str | None:
        # Kết quả đánh dấu tàu đang bàn → khoá phải gồm cả tàu đó
        current = (ctx.focus.get("vessel") or {}).get("vessel_id", "")
        return f"{super().cache_key(ctx, args)}|focus={current}"

    async def run(self, ctx: ToolContext, args: Args) -> ToolResult:
        max_rows = ctx.settings.tool_result_max_rows
        async with ctx.pool.acquire() as conn:
            company, others, problem = await resolve_company(conn, ctx.settings, args.company_name)
            if problem:
                return ToolResult(content=problem)
            exclude_id = None
            if args.exclude_vessel:
                ex, _ = await resolve_vessel(conn, ctx.settings, args.exclude_vessel)
                exclude_id = ex["vessel_id"] if ex else None
            rows = await vessel_repo.company_vessels(conn, [company["company_norm"]], args.role, exclude_id)

        current_id = (ctx.focus.get("vessel") or {}).get("vessel_id")
        vessels = [
            {**vessel_brief(r), "flag": r["flag"], "ship_type": r["ship_type_summary"],
             "roles": sorted({x["role"] for x in r["roles"]}),
             **({"is_vessel_under_discussion": True} if r["vessel_id"] == current_id else {})}
            for r in rows
        ]
        content = {
            "status": "ok",
            "company": company["company_norm"],
            "name_variants": company["variants"],
            "role_filter": args.role,
            "excluded_vessel_id": exclude_id,
            "vessel_count": len(vessels),
            "vessels": vessels[:max_rows],
            "list_truncated": len(vessels) > max_rows,
            "similar_companies_not_included": others,
        }
        if any(v.get("is_vessel_under_discussion") for v in vessels):
            content["note"] = (
                f"Danh sách có cả tàu đang được bàn ({ctx.focus['vessel'].get('name')}). Nếu người dùng hỏi "
                f"'tàu khác' thì không tính tàu này: còn {len(vessels) - 1} tàu khác."
            )
        return ToolResult(content=content, focus=company_focus(company))
