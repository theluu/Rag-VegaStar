"""Sinh bộ dữ liệu nhỏ, xác định cho test (tên tàu/công ty hư cấu).

Các tình huống được cài sẵn:
- ALPHA STAR / ALPHA STAR II: tên gần giống nhau (tìm kiếm mơ hồ)
- ALPHA STAR: một điểm GPS nhảy lúc 05:00 ngày 10/09 và khe 5 giờ (10:00 → 15:00)
- OCEAN LINE CO LTD / OCEAN LINE CO: biến thể tên của cùng chủ sở hữu đăng ký
- OCEAN LINE ASIA PTE LTD: pháp nhân khác, không được gộp
- GAMMA: không có thông tin chủ sở hữu, chỉ có 1 điểm vị trí
- Tàu tên rỗng
- BETA SEA: ngày 12/09 đi xa hơn ngày 11/09
- DELTA FISH: dark gap dài nhất

Chạy: python tests/fixtures/make_fixtures.py
"""

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).parent
T = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)  # noqa: E731
Z = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731

V = {
    "alpha": "00000000-0000-7000-8000-000000000001",
    "alpha2": "00000000-0000-7000-8000-000000000002",
    "beta": "00000000-0000-7000-8000-000000000003",
    "gamma": "00000000-0000-7000-8000-000000000004",
    "noname": "00000000-0000-7000-8000-000000000005",
    "delta": "00000000-0000-7000-8000-000000000006",
}
MMSI = {"alpha": 111111111, "alpha2": 111111112, "beta": 222222222, "gamma": 333333333, "noname": 444444444, "delta": 555555555}

VESSELS = [
    ("alpha", "9000001.0", "ALPHA STAR", "AAA1", "PA", "Panama (Republic of)", "Cargo ships, all ships of this type", "Container Ship", "200.0", "30.0", "30000.0", "25000.0", "2010.0"),
    ("alpha2", "", "ALPHA STAR II", "AAA2", "LR", "Liberia (Republic of)", "Cargo ships, carrying DG and/or MHB, HS, or MP, IMO hazard or pollutant category X", "Bulk Carrier", "150.0", "25.0", "", "", ""),
    ("beta", "9000003.0", "BETA SEA", "BBB3", "SG", "Singapore (Republic of)", "Tanker(s), all ships of this type", "Oil Products Tanker", "180.0", "32.0", "45000.0", "28000.0", "2015.0"),
    ("gamma", "", "GAMMA", "", "VN", "Viet Nam (Socialist Republic of)", "Fishing vessel", "Fishing", "", "", "", "", ""),
    ("noname", "", "", "", "", "", "Not available", "", "", "", "", "", ""),
    ("delta", "9000006.0", "DELTA FISH", "DDD6", "CN", "China (People's Republic of)", "Fishing vessel", "Fishing", "40.0", "8.0", "", "300.0", "2001.0"),
]

OWNERSHIP = [
    ("alpha", "registered_owner", "OCEAN LINE CO LTD", "SINGAPORE", "2015-01-01"),
    ("alpha", "beneficial_owner", "OCEAN HOLDINGS LTD", "SINGAPORE", ""),
    ("alpha", "operator", "BLUE OPS PTE LTD", "SINGAPORE", "2016-05-01"),
    ("alpha", "technical_manager", "TECH SHIP MGMT", "GREECE", ""),
    ("beta", "registered_owner", "OCEAN LINE CO", "SINGAPORE", ""),
    ("beta", "operator", "BLUE OPS LTD", "SINGAPORE", ""),
    ("alpha2", "registered_owner", "OTHER OWNER SA", "PANAMA", ""),
    ("delta", "operator", "OCEAN LINE ASIA PTE LTD", "CHINA", ""),
]


def positions():
    rows = []

    def add(key, ts, lat, lon, speed, status="Under way"):
        rows.append((V[key], MMSI[key], Z(ts), f"{lat:.5f}", f"{lon:.5f}", speed, 0.0, 511.0, status, "", 8.0))

    # ALPHA STAR: 10/09 00:00–10:00 mỗi 30 phút đi lên phía bắc, điểm nhảy lúc 05:00
    t0 = T("2026-09-10T00:00:00")
    for i in range(21):
        lat = 10.0 + i * 0.08
        if i == 10:
            lat += 5.0
        add("alpha", t0 + timedelta(minutes=30 * i), lat, 110.0, 9.6)
    # khe 10:00 → 15:00, sau đó mỗi giờ đi về phía đông đến 11/09 12:00
    t1 = T("2026-09-10T15:00:00")
    for i in range(22):
        add("alpha", t1 + timedelta(hours=i), 12.0, 110.0 + i * 0.15, 9.0)

    # BETA SEA: 10/09 20:00 (trước khe), 11/09 mỗi giờ +0.1°, 12/09 mỗi giờ +0.2°
    add("beta", T("2026-09-10T20:00:00"), 12.0, 104.5, 12.5)
    for i in range(24):
        add("beta", T("2026-09-11T00:00:00") + timedelta(hours=i), 12.0, 105.0 + i * 0.1, 6.0)
    for i in range(24):
        add("beta", T("2026-09-12T00:00:00") + timedelta(hours=i), 13.0, 105.0 + i * 0.2, 12.0)

    add("gamma", T("2026-09-10T06:00:00"), 9.5, 106.0, 0.0, "Engaged fishing")
    add("noname", T("2026-09-11T01:00:00"), 20.0, 115.0, 3.0)
    add("noname", T("2026-09-11T02:00:00"), 20.05, 115.0, 3.0)
    add("alpha2", T("2026-09-11T03:00:00"), 15.0, 112.0, 11.0)
    add("alpha2", T("2026-09-11T04:00:00"), 15.2, 112.0, 11.0)

    # DELTA FISH: 10/09 mỗi 2 giờ tới 22:00, khe dài tới 12/09 00:00
    for i in range(12):
        add("delta", T("2026-09-10T00:00:00") + timedelta(hours=2 * i), 8.0 + i * 0.01, 107.0, 4.0 + i * 0.1, "Engaged fishing")
    add("delta", T("2026-09-12T00:00:00"), 8.5, 107.5, 3.0, "Engaged fishing")
    return rows


GAPS = [
    ("10000000-0000-7000-8000-000000000001", "alpha", "2026-09-10T10:00:00Z", "2026-09-10T15:00:00Z", 18000, 56.4, 11.28, 11.6, 110.0, 12.0, 110.0),
    ("10000000-0000-7000-8000-000000000002", "beta", "2026-09-10T20:00:00Z", "2026-09-11T00:00:00Z", 14400, 29.3, 7.3, 12.0, 104.5, 12.0, 105.0),
    ("10000000-0000-7000-8000-000000000003", "delta", "2026-09-10T22:00:00Z", "2026-09-12T00:00:00Z", 93600, 30.1, 0.32, 8.11, 107.0, 8.5, 107.5),
]


def main():
    with open(OUT / "vessels.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["vessel_id", "mmsi", "imo", "shipname", "callsign", "flag_code", "flag", "ship_type_summary", "ship_type_detail_name", "length_m", "width_m", "dwt", "grt", "year_built"])
        for key, *rest in VESSELS:
            w.writerow([V[key], MMSI[key], *rest])
    with open(OUT / "ownership.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["vessel_id", "role", "company_name", "company_country", "start_date"])
        for key, *rest in OWNERSHIP:
            w.writerow([V[key], *rest])
    with open(OUT / "ais_positions.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["vessel_id", "mmsi", "event_ts", "lat", "lon", "speed_knots", "course_deg", "heading_deg", "nav_status", "reported_dest", "draught_m"])
        w.writerows(positions())
    with open(OUT / "dark_gaps.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["gap_id", "vessel_id", "mmsi", "gap_start_ts", "gap_end_ts", "gap_duration_seconds", "distance_nm", "implied_speed_knots", "start_lat", "start_lon", "end_lat", "end_lon"])
        for gid, key, *rest in GAPS:
            w.writerow([gid, V[key], MMSI[key], *rest])


if __name__ == "__main__":
    main()
