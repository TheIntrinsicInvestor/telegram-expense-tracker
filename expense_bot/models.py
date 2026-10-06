"""Plain data records shared by the database, reports and formatting layers."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class User:
    user_id: int
    currency: str
    timezone: str
    notify: bool
    last_weekly_sent: str | None
    last_monthly_sent: str | None


@dataclass(frozen=True)
class Entry:
    id: int
    user_id: int
    amount: float
    category: str
    note: str
    date: date
    recurring_id: int | None
    reminded: bool
    created_at: str


@dataclass(frozen=True)
class Recurring:
    id: int
    user_id: int
    amount: float
    category: str
    note: str
    frequency: str
    anchor_day: int
    next_date: date
    active: bool
