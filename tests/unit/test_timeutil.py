from datetime import datetime, timezone

import pytest

from vessel_chat.timeutil import iso, parse_ts


def test_parse_z_suffix():
    assert parse_ts("2026-09-11T21:00:00Z") == datetime(2026, 9, 11, 21, tzinfo=timezone.utc)


def test_parse_naive_is_utc():
    assert parse_ts("2026-09-11 21:00") == datetime(2026, 9, 11, 21, tzinfo=timezone.utc)


def test_parse_date_only():
    assert parse_ts("2026-09-11") == datetime(2026, 9, 11, tzinfo=timezone.utc)


def test_parse_offset_converted_to_utc():
    assert parse_ts("2026-09-12T04:00:00+07:00") == datetime(2026, 9, 11, 21, tzinfo=timezone.utc)


def test_parse_invalid():
    with pytest.raises(ValueError):
        parse_ts("hôm qua")


def test_iso_format():
    assert iso(datetime(2026, 9, 11, 21, 5, 3, 900000, tzinfo=timezone.utc)) == "2026-09-11T21:05:03Z"
    assert iso(None) is None
