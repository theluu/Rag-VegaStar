from vessel_chat.repositories import vessels as repo

ALPHA = "00000000-0000-7000-8000-000000000001"
BETA = "00000000-0000-7000-8000-000000000003"


async def test_exact_name_ranks_first_case_insensitive(pool):
    async with pool.acquire() as conn:
        res = await repo.search_vessels(conn, "alpha star", limit=5, threshold=0.35)
    assert res[0]["shipname"] == "ALPHA STAR" and res[0]["score"] == 1.0
    assert "ALPHA STAR II" in [r["shipname"] for r in res]


async def test_typo_tolerant_name_search(pool):
    async with pool.acquire() as conn:
        res = await repo.search_vessels(conn, "Alpa Sta", limit=5, threshold=0.35)
    assert res and res[0]["shipname"].startswith("ALPHA STAR")


async def test_search_by_mmsi_imo_callsign_and_id(pool):
    async with pool.acquire() as conn:
        by_mmsi = await repo.search_vessels(conn, "222222222", limit=5, threshold=0.35)
        by_imo = await repo.search_vessels(conn, "IMO 9000001", limit=5, threshold=0.35)
        by_call = await repo.search_vessels(conn, "ddd6", limit=5, threshold=0.35)
        by_id = await repo.search_vessels(conn, ALPHA, limit=5, threshold=0.35)
    assert [r["shipname"] for r in by_mmsi] == ["BETA SEA"] and by_mmsi[0]["match"] == "mmsi"
    assert [r["shipname"] for r in by_imo] == ["ALPHA STAR"] and by_imo[0]["match"] == "imo"
    assert by_call[0]["shipname"] == "DELTA FISH"
    assert by_id[0]["vessel_id"] == ALPHA


async def test_search_nothing_found(pool):
    async with pool.acquire() as conn:
        assert await repo.search_vessels(conn, "ZZZZ QQQQ", limit=5, threshold=0.35) == []
        assert await repo.search_vessels(conn, "999999999", limit=5, threshold=0.35) == []
        assert await repo.search_vessels(conn, "  ", limit=5, threshold=0.35) == []


async def test_get_vessel_and_ownership(pool):
    async with pool.acquire() as conn:
        v = await repo.get_vessel(conn, ALPHA)
        owners = await repo.get_ownership(conn, ALPHA)
        assert await repo.get_vessel(conn, "00000000-0000-7000-8000-00000000ffff") is None
    assert v["mmsi"] == 111111111 and v["flag"].startswith("Panama")
    roles = {o["role"]: o["company_name"] for o in owners}
    assert roles["registered_owner"] == "OCEAN LINE CO LTD"
    assert roles["operator"] == "BLUE OPS PTE LTD"


async def test_match_companies_groups_variants(pool):
    async with pool.acquire() as conn:
        res = await repo.match_companies(conn, "Ocean Line Co., Ltd.", threshold=0.45)
    assert res[0]["company_norm"] == "OCEAN LINE"
    assert res[0]["exact"] is True
    assert set(res[0]["variants"]) == {"OCEAN LINE CO LTD", "OCEAN LINE CO"}
    # Pháp nhân khác vẫn được liệt kê nhưng không phải khớp chính xác
    others = [r for r in res if r["company_norm"] == "OCEAN LINE ASIA"]
    assert others and others[0]["exact"] is False


async def test_company_vessels_by_role_excluding_current(pool):
    async with pool.acquire() as conn:
        res = await repo.company_vessels(conn, ["OCEAN LINE"], role="registered_owner", exclude_vessel_id=ALPHA)
        all_roles = await repo.company_vessels(conn, ["BLUE OPS"], role=None)
    assert [r["shipname"] for r in res] == ["BETA SEA"]
    assert res[0]["roles"] == [{"role": "registered_owner", "company_name": "OCEAN LINE CO"}]
    assert {r["shipname"] for r in all_roles} == {"ALPHA STAR", "BETA SEA"}


async def test_vessels_by_filter(pool):
    async with pool.acquire() as conn:
        fishing = await repo.vessels_by_filter(conn, ship_type_group="fishing", limit=10)
        ops = await repo.vessels_by_filter(conn, company_norms=["BLUE OPS"], role="operator", ship_type_group="tanker", limit=10)
    assert {r["shipname"] for r in fishing} == {"GAMMA", "DELTA FISH"}
    assert [r["vessel_id"] for r in ops] == [BETA]
