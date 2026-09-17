from pydantic import BaseModel, Field

from ..repositories import gaps as gap_repo
from ..repositories import positions as pos_repo
from ..repositories import vessels as vessel_repo
from ..timeutil import iso
from .base import Tool, ToolContext, ToolResult, register
from .common import (
    VESSEL_ARG_DESC,
    Role,
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
            "dwt": v["dwt"],
            "grt": v["grt"],
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

        vessels = [
            {**vessel_brief(r), "flag": r["flag"], "ship_type": r["ship_type_summary"],
             "roles": sorted({x["role"] for x in r["roles"]})}
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
        return ToolResult(content=content, focus=company_focus(company))
