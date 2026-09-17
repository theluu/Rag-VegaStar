from datetime import datetime, timezone


def parse_ts(value: str | datetime) -> datetime:
    """Đọc thời gian ISO-8601; không có múi giờ thì coi là UTC. Luôn trả về UTC."""
    if isinstance(value, datetime):
        dt = value
    else:
        text = value.strip().replace(" ", "T", 1)
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
