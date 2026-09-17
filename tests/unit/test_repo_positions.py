from datetime import datetime, timezone

from vessel_chat.repositories import gaps as gaps_repo
from vessel_chat.repositories import positions as repo

ALPHA = "00000000-0000-7000-8000-000000000001"
BETA = "00000000-0000-7000-8000-000000000003"
DELTA = "00000000-0000-7000-8000-000000000006"


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


async def test_positions_between_ordered(pool):
    async with pool.acquire() as conn:
        pts = await repo.positions_between(conn, BETA, utc(2026, 9, 11), utc(2026, 9, 11, 23, 59, 59))
    assert len(pts) == 24
    assert pts[0].ts == utc(2026, 9, 11) and pts[-1].ts == utc(2026, 9, 11, 23)
    assert pts[0].lon == 105.0


async def test_nearest_positions_before_and_after(pool):
    async with pool.acquire() as conn:
        before, after = await repo.nearest_positions(conn, ALPHA, utc(2026, 9, 10, 12))
    assert before.ts == utc(2026, 9, 10, 10)
    assert after.ts == utc(2026, 9, 10, 15)


async def test_nearest_positions_outside_range(pool):
    async with pool.acquire() as conn:
        before, after = await repo.nearest_positions(conn, ALPHA, utc(2026, 9, 1))
    assert before is None and after.ts == utc(2026, 9, 10)


async def test_last_position_and_data_range(pool):
    async with pool.acquire() as conn:
        last = await repo.last_position(conn, BETA)
        first_ts, last_ts = await repo.data_time_range(conn)
    assert last.ts == utc(2026, 9, 12, 23)
    assert first_ts == utc(2026, 9, 10) and last_ts == utc(2026, 9, 12, 23)


async def test_positions_for_vessels(pool):
    async with pool.acquire() as conn:
        res = await repo.positions_for_vessels(conn, [ALPHA, BETA], utc(2026, 9, 11), utc(2026, 9, 11, 23, 59))
    assert set(res) == {ALPHA, BETA}
    assert len(res[BETA]) == 24


async def test_list_gaps_order_and_filters(pool):
    async with pool.acquire() as conn:
        longest = await gaps_repo.list_gaps(conn, order_by="duration", limit=1)
        for_beta = await gaps_repo.list_gaps(conn, vessel_id=BETA)
        in_window = await gaps_repo.list_gaps(conn, start=utc(2026, 9, 10, 9), end=utc(2026, 9, 10, 11))
    assert longest[0]["vessel_id"] == DELTA and longest[0]["gap_duration_seconds"] == 93600
    assert longest[0]["shipname"] == "DELTA FISH"
    assert len(for_beta) == 1 and for_beta[0]["start_lat"] == 12.0
    assert {g["vessel_id"] for g in in_window} == {ALPHA}
