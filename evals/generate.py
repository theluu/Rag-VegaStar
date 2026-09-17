"""Sinh ca kiểm thử từ dữ liệu thật (đáp án chuẩn tính bằng SQL), ghi evals/cases.generated.yaml.

    python evals/generate.py --per-category 3 --seed 7

Tàu/công ty được chọn ngẫu nhiên có seed nên bộ ca tái lập được; đổi seed để có câu hỏi mới —
cách kiểm tra rằng hệ thống không "học thuộc" kịch bản mẫu.
"""

import argparse
import asyncio
import random
from pathlib import Path

import asyncpg
import yaml

from vessel_chat.config import get_settings
from vessel_chat.normalize import norm_company

OUT = Path(__file__).parent / "cases.generated.yaml"
NM = 1852.0


FLAG_VI = {
    "China": "Trung Quốc", "Hong Kong": "Hồng Kông", "Viet Nam": "Việt Nam", "Korea": "Hàn Quốc",
    "Japan": "Nhật Bản", "Thailand": "Thái Lan", "Philippines": "Philippines", "Marshall Islands": "Marshall",
    "Greece": "Hy Lạp", "Cyprus": "Síp", "Portugal": "Bồ Đào Nha", "Denmark": "Đan Mạch", "Norway": "Na Uy",
    "United Kingdom": "Anh", "Germany": "Đức", "France": "Pháp", "Netherlands": "Hà Lan", "Italy": "Ý",
    "India": "Ấn Độ", "Taiwan": "Đài Loan", "Saudi Arabia": "Ả Rập", "Tuvalu": "Tuvalu", "Togo": "Togo",
    "Cameroon": "Cameroon", "Sierra Leone": "Sierra Leone", "Belize": "Belize", "Mongolia": "Mông Cổ",
    "Barbados": "Barbados", "Palau": "Palau", "Comoros": "Comoros", "Cook Islands": "Quần đảo Cook",
    "Antigua and Barbuda": "Antigua", "Saint Kitts and Nevis": "Saint Kitts", "Bangladesh": "Bangladesh",
}


def flag_names(flag: str) -> list[str]:
    """Các cách viết chấp nhận được của quốc gia treo cờ (tên gốc tiếng Anh hoặc tên tiếng Việt)."""
    base = "Hong Kong" if "Hong Kong" in flag else flag.split(" (")[0].strip()
    names = [base]
    for en, vi in FLAG_VI.items():
        if en in base:
            names.append(vi)
    return names


async def pick_vessels(conn, rng: random.Random, n: int) -> list[asyncpg.Record]:
    rows = await conn.fetch(
        """
        SELECT v.*, count(p.*) AS points
        FROM vessels v JOIN ais_positions p USING (vessel_id)
        WHERE v.shipname ~ '^[A-Z][A-Z .-]{3,}[A-Z0-9]$'
          AND v.flag IS NOT NULL AND v.length_m IS NOT NULL
          AND (SELECT count(*) FROM vessels w WHERE w.shipname_norm = v.shipname_norm) = 1
        GROUP BY v.vessel_id
        HAVING count(p.*) >= 60
        ORDER BY v.vessel_id
        """
    )
    return rng.sample(list(rows), n)


async def generate(conn, rng: random.Random, per: int) -> list[dict]:
    cases: list[dict] = []
    vessels = await pick_vessels(conn, rng, per * 4)
    groups = [vessels[i * per:(i + 1) * per] for i in range(4)]

    for i, v in enumerate(groups[0], 1):
        cases.append({
            "id": f"gen-vessel-info-{i}", "category": "vessel_info",
            "turns": [f"Tàu {v['shipname']} treo cờ nước nào và dài bao nhiêu mét?"],
            "expect": {"tools": ["get_vessel_details"], "contains_any": flag_names(v["flag"]),
                       "numbers": [{"value": v["length_m"], "tol": 0.5}], "citations": True},
        })
        cases.append({
            "id": f"gen-mmsi-{i}", "category": "identifier_lookup",
            "turns": [f"Tàu có MMSI {v['mmsi']} tên là gì, thuộc loại tàu nào?"],
            "expect": {"contains": [v["shipname"]], "citations": True},
        })

    for i, v in enumerate(groups[1], 1):
        owner = await conn.fetchval(
            "SELECT company_name FROM ownership WHERE vessel_id = $1 AND role = 'registered_owner' LIMIT 1",
            v["vessel_id"],
        )
        if owner:
            cases.append({
                "id": f"gen-owner-{i}", "category": "ownership",
                "turns": [f"Chủ sở hữu đăng ký của tàu {v['shipname']} là công ty nào?"],
                "expect": {"tools": ["get_vessel_details"], "contains": [owner], "citations": True},
            })
        else:
            cases.append({
                "id": f"gen-owner-missing-{i}", "category": "missing_data",
                "turns": [f"Chủ sở hữu đăng ký của tàu {v['shipname']} là ai?"],
                "expect": {"tools": ["get_vessel_details"], "contains_any": ["không có", "chưa có", "không tìm thấy"]},
            })
        point = await conn.fetchrow(
            "SELECT event_ts, lat, lon FROM ais_positions WHERE vessel_id = $1 ORDER BY event_ts OFFSET $2 LIMIT 1",
            v["vessel_id"], int(v["points"]) // 2,
        )
        ts = point["event_ts"].strftime("%H:%M:%S ngày %d/%m/%Y")
        cases.append({
            "id": f"gen-position-{i}", "category": "position_at",
            "turns": [f"Lúc {ts} (UTC) tàu {v['shipname']} ở đâu?"],
            "expect": {"tools": ["get_position_at"], "citations": True,
                       "numbers": [{"value": round(point["lat"], 4), "tol": 0.002},
                                   {"value": round(point["lon"], 4), "tol": 0.002}]},
        })

    for i, v in enumerate(groups[2], 1):
        day = await conn.fetchrow(
            """
            SELECT (event_ts AT TIME ZONE 'UTC')::date AS d, count(*) AS n,
                   ST_Length(ST_MakeLine(geom ORDER BY event_ts)::geography) / $2 AS nm
            FROM ais_positions WHERE vessel_id = $1
            GROUP BY 1 HAVING count(*) >= 20 ORDER BY 2 DESC, 1 LIMIT 1
            """,
            v["vessel_id"], NM,
        )
        if day:
            cases.append({
                "id": f"gen-track-{i}", "category": "track",
                "turns": [f"Trong ngày {day['d']:%d/%m/%Y} (UTC), tàu {v['shipname']} đi được bao nhiêu hải lý?"],
                "expect": {"tools": ["get_track"], "citations": True,
                           # dung sai 2% hoặc 0,1 hải lý (tool loại điểm nhiễu, SQL đo trắc địa trên điểm thô)
                           "numbers": [{"value": round(day["nm"], 2), "tol": max(0.1, day["nm"] * 0.02)}]},
            })
        last = await conn.fetchrow(
            "SELECT event_ts, lat, lon FROM ais_positions WHERE vessel_id = $1 ORDER BY event_ts DESC LIMIT 1",
            v["vessel_id"],
        )
        cases.append({
            "id": f"gen-last-{i}", "category": "last_position",
            "turns": [f"Vị trí cuối cùng có trong dữ liệu của tàu {v['shipname']} là ở đâu?"],
            "expect": {"tools": ["get_last_position"], "citations": True,
                       "numbers": [{"value": round(last["lat"], 4), "tol": 0.002}]},
        })

    for i, v in enumerate(groups[3], 1):
        gaps = await conn.fetchval("SELECT count(*) FROM dark_gaps WHERE vessel_id = $1", v["vessel_id"])
        expect = {"tools": ["get_dark_gaps"], "citations": gaps > 0}
        if gaps == 0:
            expect["contains_any"] = ["không có", "chưa có", "không ghi nhận", "không phát hiện", "không bị",
                                      "lần nào", "0 lần"]
        else:
            expect["integers"] = [gaps]
        cases.append({
            "id": f"gen-gaps-{i}", "category": "dark_gaps",
            "turns": [f"Tàu {v['shipname']} bị mất tín hiệu AIS bao nhiêu lần trong dữ liệu?"],
            "expect": expect,
        })

    companies = await conn.fetch(
        """
        SELECT company_norm, min(company_name) AS name, count(DISTINCT vessel_id) AS n
        FROM ownership WHERE role = 'operator'
        GROUP BY company_norm HAVING count(DISTINCT vessel_id) BETWEEN 3 AND 15
           AND count(DISTINCT company_name) = 1
        ORDER BY company_norm
        """
    )
    for i, c in enumerate(rng.sample(list(companies), per), 1):
        assert norm_company(c["name"]) == c["company_norm"]
        cases.append({
            "id": f"gen-fleet-{i}", "category": "company_fleet",
            "turns": [f"Công ty {c['name']} khai thác (operator) bao nhiêu tàu trong dữ liệu?"],
            "expect": {"tools": ["find_company_vessels"], "integers": [c["n"]], "citations": True},
        })

    longest = await conn.fetchrow(
        "SELECT v.shipname FROM dark_gaps g JOIN vessels v USING (vessel_id) ORDER BY gap_duration_seconds DESC LIMIT 1"
    )
    cases.append({
        "id": "gen-longest-gap", "category": "dark_gaps",
        "turns": ["Trong toàn bộ dữ liệu, tàu nào có lần tắt AIS dài nhất?"],
        "expect": {"tools": ["get_dark_gaps"], "contains": [longest["shipname"]], "citations": True},
    })

    tanker_day = await conn.fetchval(
        """
        SELECT count(DISTINCT p.vessel_id) FROM ais_positions p JOIN vessels v USING (vessel_id)
        WHERE v.ship_type_group = 'tanker' AND p.event_ts >= '2026-09-12' AND p.event_ts < '2026-09-13'
        """
    )
    cases.append({
        "id": "gen-type-day", "category": "multi_tracks",
        "turns": ["Vẽ hành trình của tất cả tàu chở dầu trong ngày 12/09/2026. Có bao nhiêu tàu có dữ liệu?"],
        "expect": {"tools": ["get_multi_tracks"], "integers": [tanker_day], "citations": True},
    })
    return cases


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-category", type=int, default=3)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        cases = await generate(conn, random.Random(args.seed), args.per_category)
    finally:
        await conn.close()
    header = f"# Sinh tự động bởi evals/generate.py (seed={args.seed}). Không sửa tay.\n"
    args.out.write_text(header + yaml.safe_dump(cases, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Đã ghi {len(cases)} ca vào {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
