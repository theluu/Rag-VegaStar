from datetime import datetime, timedelta, timezone

import pytest

from vessel_chat.geo import (
    Point,
    bbox_of,
    downsample,
    filter_jumps,
    haversine_nm,
    interpolate,
    split_segments,
    track_stats,
)

T0 = datetime(2026, 9, 10, tzinfo=timezone.utc)


def pt(minutes, lat, lon, speed=10.0):
    return Point(ts=T0 + timedelta(minutes=minutes), lat=lat, lon=lon, speed=speed)


def test_haversine_one_degree_longitude_at_equator():
    assert haversine_nm(0, 0, 0, 1) == pytest.approx(60.04, abs=0.05)


def test_haversine_zero():
    assert haversine_nm(10, 110, 10, 110) == 0


def test_filter_jumps_removes_isolated_spike_only():
    # ~10 kn bình thường, điểm giữa nhảy 5 độ
    pts = [pt(0, 10.0, 110.0), pt(30, 10.08, 110.0), pt(60, 15.0, 110.0), pt(90, 10.25, 110.0), pt(120, 10.33, 110.0)]
    kept, removed = filter_jumps(pts, max_speed_kn=50)
    assert removed == 1
    assert [p.lat for p in kept] == [10.0, 10.08, 10.25, 10.33]


def test_filter_jumps_keeps_normal_track():
    pts = [pt(i * 30, 10 + i * 0.08, 110.0) for i in range(6)]
    kept, removed = filter_jumps(pts, max_speed_kn=50)
    assert removed == 0 and len(kept) == 6


def test_filter_jumps_removes_bad_last_point():
    pts = [pt(0, 10.0, 110.0), pt(30, 10.08, 110.0), pt(60, 10.16, 110.0), pt(70, 14.0, 110.0)]
    kept, removed = filter_jumps(pts, max_speed_kn=50)
    assert removed == 1 and kept[-1].lat == 10.16


def test_split_segments_on_gap():
    pts = [pt(0, 10, 110), pt(30, 10.1, 110), pt(30 + 5 * 60, 11, 110), pt(30 + 5 * 60 + 30, 11.1, 110)]
    segs = split_segments(pts, gap_hours=3)
    assert [len(s) for s in segs] == [2, 2]


def test_track_stats_reports_distance_speed_and_gaps():
    pts = [pt(0, 10, 110), pt(60, 10.1, 110), pt(60 + 4 * 60, 11.1, 110), pt(60 + 5 * 60, 11.2, 110)]
    s = track_stats(pts, gap_hours=3)
    assert s["point_count"] == 4
    assert s["distance_nm"] == pytest.approx(6.0 + 60.0 + 6.0, rel=0.01)
    assert s["gap_distance_nm"] == pytest.approx(60.0, rel=0.01)
    assert s["duration_hours"] == pytest.approx(6.0)
    assert s["avg_speed_knots"] == pytest.approx(72.0 / 6.0, rel=0.01)
    assert len(s["gaps"]) == 1 and s["gaps"][0]["hours"] == pytest.approx(4.0)


def test_track_stats_empty_and_single():
    assert track_stats([], gap_hours=3)["point_count"] == 0
    one = track_stats([pt(0, 10, 110)], gap_hours=3)
    assert one["distance_nm"] == 0 and one["avg_speed_knots"] is None


def test_interpolate_midpoint():
    lat, lon = interpolate(pt(0, 10, 110), pt(60, 11, 112), T0 + timedelta(minutes=30))
    assert (lat, lon) == pytest.approx((10.5, 111.0))


def test_bbox_and_downsample():
    pts = [pt(i, 10 + i, 110 - i) for i in range(10)]
    assert bbox_of(pts) == [101, 10, 110, 19]
    ds = downsample(pts, 4)
    assert len(ds) == 4 and ds[0] is pts[0] and ds[-1] is pts[-1]
    assert downsample(pts, 100) == pts
