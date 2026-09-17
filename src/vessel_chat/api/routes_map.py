"""Dữ liệu bản đồ và truy vấn hành trình trực tiếp (không qua LLM)."""

import json
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import Settings
from ..repositories import map_data as map_repo
from ..repositories import positions as pos_repo
from ..repositories import vessels as vessel_repo
from ..tools import ToolContext, execute_tool
from ..tools.base import ToolInputError
from ..tools.common import Role, ShipTypeGroup, parse_range, resolve_company, resolve_vessel, time_range_json
from ..tracks import build_multi_tracks
from .deps import get_app_settings, get_pool

router = APIRouter(tags=["map"])


@router.get("/map-data/{data_id}")
async def get_map_data(data_id: UUID, pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        item = await map_repo.get_map_data(conn, str(data_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Không có dữ liệu bản đồ này")
    return item


@router.get("/vessels/search", tags=["vessels"])
async def search_vessels(
    q: Annotated[str, Query(min_length=1, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    pool: asyncpg.Pool = Depends(get_pool),
    settings: Settings = Depends(get_app_settings),
):
    async with pool.acquire() as conn:
        return await vessel_repo.search_vessels(conn, q, limit=limit, threshold=settings.vessel_match_threshold)


@router.get("/vessels/{vessel}/dark-gaps", tags=["vessels"])
async def vessel_dark_gaps(
    vessel: str,
    start: str | None = None,
    end: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
    pool: asyncpg.Pool = Depends(get_pool),
    settings: Settings = Depends(get_app_settings),
):
    """GeoJSON các lần mất tín hiệu của một tàu (vessel = vessel_id / tên / MMSI / IMO)."""
    args = {"vessel": vessel, "start": start, "end": end, "limit": limit}
    result = await execute_tool(ToolContext(pool=pool, settings=settings), "get_dark_gaps", json.dumps(args))
    content = result.content
    if "error" in content:
        raise HTTPException(status_code=400, detail=content)
    if content.get("status") in ("not_found", "ambiguous"):
        raise HTTPException(status_code=404 if content["status"] == "not_found" else 409, detail=content)
    geojson = result.map_data[0].geojson if result.map_data else {"type": "FeatureCollection", "features": []}
    return {**geojson, "summary": content}


@router.get("/tracks", tags=["vessels"])
async def get_tracks(
    start: str,
    end: str,
    vessel: Annotated[list[str] | None, Query(description="Lặp lại để lấy nhiều tàu (id/tên/MMSI/IMO)")] = None,
    company: str | None = None,
    role: Role | None = None,
    ship_type_group: ShipTypeGroup | None = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    pool: asyncpg.Pool = Depends(get_pool),
    settings: Settings = Depends(get_app_settings),
):
    """Nhiều hành trình dạng GeoJSON FeatureCollection, phân trang theo tàu (limit/offset)."""
    try:
        t0, t1 = parse_range(start, end)
    except ToolInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    page_size = min(limit or settings.max_tracks_per_page, settings.max_tracks_per_page)

    async with pool.acquire() as conn:
        if vessel:
            vessels, unresolved = [], []
            for q in vessel:
                v, problem = await resolve_vessel(conn, settings, q)
                if v:
                    vessels.append(v)
                else:
                    unresolved.append(problem)
            if unresolved:
                raise HTTPException(status_code=404, detail={"unresolved": unresolved})
        else:
            norms = None
            if company:
                chosen, _, problem = await resolve_company(conn, settings, company)
                if problem:
                    raise HTTPException(status_code=404 if problem["status"] == "not_found" else 409, detail=problem)
                norms = [chosen["company_norm"]]
            vessels = await vessel_repo.vessels_by_filter(
                conn, company_norms=norms, role=role, ship_type_group=ship_type_group,
                limit=settings.multi_track_max_vessels,
            )
        total = len(vessels)
        page = vessels[offset: offset + page_size]
        positions = await pos_repo.positions_for_vessels(conn, [v["vessel_id"] for v in page], t0, t1)

    fc, per_vessel, totals = build_multi_tracks(page, positions, settings, settings.multi_track_max_points)
    next_offset = offset + page_size if offset + page_size < total else None
    return {
        **fc,
        "summary": {**totals, "time_range": time_range_json(t0, t1), "vessels": per_vessel},
        "pagination": {"offset": offset, "limit": page_size, "total_vessels": total, "next_offset": next_offset},
    }
