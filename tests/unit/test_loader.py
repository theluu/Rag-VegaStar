from conftest import FIXTURES
from vessel_chat.loader import load_all

ALPHA = "00000000-0000-7000-8000-000000000001"


async def _counts(conn):
    return {
        t: await conn.fetchval(f"SELECT count(*) FROM {t}")
        for t in ("vessels", "ais_positions", "dark_gaps", "ownership")
    }


async def test_load_is_idempotent(pool):
    async with pool.acquire() as conn:
        before = await _counts(conn)
        result = await load_all(conn, FIXTURES)
        after = await _counts(conn)
    assert before == after
    assert result == after
    assert after == {"vessels": 6, "ais_positions": 110, "dark_gaps": 3, "ownership": 8}


async def test_derived_columns_are_filled(pool):
    async with pool.acquire() as conn:
        v = await conn.fetchrow("SELECT * FROM vessels WHERE vessel_id = $1", ALPHA)
        assert v["shipname_norm"] == "ALPHA STAR"
        assert v["ship_type_group"] == "cargo"
        assert v["imo"] == 9000001
        assert v["year_built"] == 2010
        assert await conn.fetchval("SELECT count(*) FROM ais_positions WHERE geom IS NULL") == 0
        g = await conn.fetchrow("SELECT ST_AsText(path) AS p FROM dark_gaps WHERE vessel_id = $1", ALPHA)
        assert g["p"].startswith("LINESTRING")
        norms = await conn.fetch("SELECT DISTINCT company_norm FROM ownership WHERE company_name LIKE 'OCEAN LINE%'")
        assert {r["company_norm"] for r in norms} == {"OCEAN LINE", "OCEAN LINE ASIA"}


async def test_empty_values_become_null(pool):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT shipname, imo, length_m FROM vessels WHERE mmsi = 444444444")
    assert row["shipname"] is None and row["imo"] is None and row["length_m"] is None
