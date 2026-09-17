"""Dựng nhiều hành trình thành GeoJSON FeatureCollection (dùng cho tool và REST /tracks).

Mỗi tàu: lọc điểm nhiễu → thống kê trên điểm đã lọc → giảm mẫu theo ngân sách điểm chung
để bản đồ vẽ mượt → hình học tách tại khe.
"""

from .config import Settings
from .geo import Point, bbox_of, downsample, filter_jumps, merge_bbox, track_geometry, track_stats


def build_multi_tracks(
    vessels: list[dict],
    positions: dict[str, list[Point]],
    settings: Settings,
    max_points: int,
) -> tuple[dict, list[dict], dict]:
    """Trả (feature_collection, thống kê từng tàu sắp theo quãng đường giảm dần, tổng hợp)."""
    cleaned: list[tuple[dict, list[Point], int]] = []
    for v in vessels:
        pts = positions.get(v["vessel_id"], [])
        if not pts:
            continue
        kept, removed = filter_jumps(pts, settings.max_plausible_speed_knots)
        cleaned.append((v, kept, removed))

    total_points = sum(len(k) for _, k, _ in cleaned)
    over_budget = total_points > max_points

    features, per_vessel, boxes = [], [], []
    rendered = removed_total = 0
    for v, kept, removed in cleaned:
        stats = track_stats(kept, settings.track_gap_split_hours)
        budget = max(2, int(max_points * len(kept) / total_points)) if over_budget else len(kept)
        drawn = downsample(kept, budget)
        rendered += len(drawn)
        removed_total += removed
        box = bbox_of(kept)
        boxes.append(box)
        info = {
            "vessel_id": v["vessel_id"],
            "name": v.get("shipname") or "(không tên)",
            "mmsi": v.get("mmsi"),
            "ship_type_group": v.get("ship_type_group"),
            "point_count": stats["point_count"],
            "distance_nm": stats["distance_nm"],
            "avg_speed_knots": stats["avg_speed_knots"],
            "gap_count": len(stats["gaps"]),
        }
        per_vessel.append(info)
        geometry = track_geometry(drawn, settings.track_gap_split_hours)
        if geometry:
            features.append({"type": "Feature", "geometry": geometry, "properties": {**info, "kind": "track"}})

    per_vessel.sort(key=lambda x: x["distance_nm"], reverse=True)
    rank = {p["vessel_id"]: i for i, p in enumerate(per_vessel)}
    features.sort(key=lambda f: rank[f["properties"]["vessel_id"]])
    for i, f in enumerate(features):
        f["properties"]["color_index"] = i

    totals = {
        "vessels_with_data": len(cleaned),
        "total_points": total_points,
        "rendered_points": rendered,
        "removed_noise_points": removed_total,
        "downsampled": over_budget,
        "bbox": merge_bbox(boxes),
        "total_distance_nm": round(sum(p["distance_nm"] for p in per_vessel), 2),
    }
    return {"type": "FeatureCollection", "features": features}, per_vessel, totals
