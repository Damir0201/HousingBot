from datetime import UTC, datetime

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_local(dt: datetime) -> datetime:
    return dt.astimezone(get_settings().tz)


def fmt_dt(dt: datetime) -> str:
    return to_local(dt).strftime("%d.%m %H:%M")


def fmt_time(dt: datetime) -> str:
    return to_local(dt).strftime("%H:%M")
