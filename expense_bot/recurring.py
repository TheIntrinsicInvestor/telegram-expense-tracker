"""Date maths for recurring payments. anchor_day keeps a 31st payment on the 31st after a short month."""

import calendar
from datetime import date, timedelta

from expense_bot.money import round2

FREQUENCIES = ("weekly", "monthly", "yearly")
_PER_YEAR = {"weekly": 52, "monthly": 12, "yearly": 1}


def _clamped(year: int, month: int, anchor_day: int) -> date:
    return date(year, month, min(anchor_day, calendar.monthrange(year, month)[1]))


def next_occurrence(current: date, frequency: str, anchor_day: int) -> date:
    if frequency == "weekly":
        return current + timedelta(days=7)
    if frequency == "monthly":
        year, month = (current.year + 1, 1) if current.month == 12 else (current.year, current.month + 1)
        return _clamped(year, month, anchor_day)
    if frequency == "yearly":
        return _clamped(current.year + 1, current.month, anchor_day)
    raise ValueError(f"unknown frequency: {frequency}")


def annual_cost(amount: float, frequency: str) -> float:
    return round2(amount * _PER_YEAR[frequency])
