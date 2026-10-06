"""Time helpers. All user-facing dates are in the user's own timezone."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def local_now(tz: str, now_utc: datetime) -> datetime:
    return now_utc.astimezone(ZoneInfo(tz))


def local_today(tz: str, now_utc: datetime) -> date:
    return local_now(tz, now_utc).date()
