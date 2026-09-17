"""Tính toán hình học trên chuỗi điểm AIS (thuần Python, không phụ thuộc DB).

Toạ độ: độ thập phân WGS84. Khoảng cách: hải lý (nm). Vùng dữ liệu 102–118°E nên không
cần xử lý kinh tuyến đổi ngày.
"""

import math
from dataclasses import dataclass
from datetime import datetime

from .timeutil import iso

EARTH_RADIUS_NM = 3440.065


@dataclass(frozen=True)
class Point:
    ts: datetime
    lat: float
    lon: float
    speed: float | None = None
    course: float | None = None
    nav_status: str | None = None


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_NM * math.asin(min(1.0, math.sqrt(a)))


def _dist(a: Point, b: Point) -> float:
    return haversine_nm(a.lat, a.lon, b.lat, b.lon)


def _hours(a: Point, b: Point) -> float:
    return (b.ts - a.ts).total_seconds() / 3600


def implied_speed(a: Point, b: Point) -> float:
    h = abs(_hours(a, b))
    d = _dist(a, b)
    if h == 0:
        return math.inf if d > 0.01 else 0.0
    return d / h


def filter_jumps(points: list[Point], max_speed_kn: float) -> tuple[list[Point], int]:
    """Loại điểm GPS nhảy bất thường.

    Điểm giữa bị loại khi tốc độ suy ra tới CẢ điểm trước và điểm sau đều vượt ngưỡng
    (một điểm lệch đơn lẻ). Điểm đầu/cuối chỉ có một hàng xóm: bị loại khi đoạn nối với hàng
    xóm vượt ngưỡng trong khi đoạn kế tiếp bình thường.
    """
    n = len(points)
    if n < 3:
        return list(points), 0
    fast = [implied_speed(points[i], points[i + 1]) > max_speed_kn for i in range(n - 1)]
    keep = []
    for i, p in enumerate(points):
        if i == 0:
            bad = fast[0] and not fast[1]
        elif i == n - 1:
            bad = fast[-1] and not fast[-2]
        else:
            bad = fast[i - 1] and fast[i]
        if not bad:
            keep.append(p)
    return keep, n - len(keep)


def split_segments(points: list[Point], gap_hours: float) -> list[list[Point]]:
    segments: list[list[Point]] = []
    for p in points:
        if segments and _hours(segments[-1][-1], p) <= gap_hours:
            segments[-1].append(p)
        else:
            segments.append([p])
    return segments


def track_stats(points: list[Point], gap_hours: float) -> dict:
    """Thống kê hành trình. distance_nm gồm cả khoảng cách thẳng qua các khe (báo riêng)."""
    stats = {
        "point_count": len(points),
        "distance_nm": 0.0,
        "gap_distance_nm": 0.0,
        "duration_hours": 0.0,
        "avg_speed_knots": None,
        "gaps": [],
    }
    if len(points) < 2:
        return stats
    total = gap_total = 0.0
    for a, b in zip(points, points[1:]):
        d = _dist(a, b)
        total += d
        h = _hours(a, b)
        if h > gap_hours:
            gap_total += d
            stats["gaps"].append(
                {"from": iso(a.ts), "to": iso(b.ts), "hours": round(h, 2), "distance_nm": round(d, 2)}
            )
    duration = _hours(points[0], points[-1])
    stats.update(
        distance_nm=round(total, 2),
        gap_distance_nm=round(gap_total, 2),
        duration_hours=round(duration, 2),
        avg_speed_knots=round(total / duration, 2) if duration > 0 else None,
    )
    return stats


def interpolate(p1: Point, p2: Point, ts: datetime) -> tuple[float, float]:
    span = (p2.ts - p1.ts).total_seconds()
    f = 0.0 if span == 0 else (ts - p1.ts).total_seconds() / span
    return p1.lat + (p2.lat - p1.lat) * f, p1.lon + (p2.lon - p1.lon) * f


def bbox_of(points: list[Point]) -> list[float] | None:
    """[min_lon, min_lat, max_lon, max_lat]"""
    if not points:
        return None
    lons = [p.lon for p in points]
    lats = [p.lat for p in points]
    return [min(lons), min(lats), max(lons), max(lats)]


def merge_bbox(boxes: list[list[float] | None]) -> list[float] | None:
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def downsample(points: list[Point], max_points: int) -> list[Point]:
    """Giảm mẫu đều, giữ điểm đầu và cuối."""
    n = len(points)
    if n <= max_points or max_points < 2:
        return list(points)
    step = (n - 1) / (max_points - 1)
    return [points[round(i * step)] for i in range(max_points)]


def track_geometry(points: list[Point], gap_hours: float) -> dict | None:
    """LineString, hoặc MultiLineString khi hành trình có khe (không vẽ nối qua khe)."""
    segs = [[[round(p.lon, 5), round(p.lat, 5)] for p in s] for s in split_segments(points, gap_hours)]
    segs = [s if len(s) > 1 else s * 2 for s in segs]  # đoạn 1 điểm vẫn hiển thị được
    if not segs:
        return None
    if len(segs) == 1:
        return {"type": "LineString", "coordinates": segs[0]}
    return {"type": "MultiLineString", "coordinates": segs}


def point_json(p: Point | None) -> dict | None:
    if p is None:
        return None
    return {
        "ts": iso(p.ts),
        "lat": round(p.lat, 5),
        "lon": round(p.lon, 5),
        "speed_knots": None if p.speed is None else round(p.speed, 1),
        "course_deg": p.course,
        "nav_status": p.nav_status or None,
    }
