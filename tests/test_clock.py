from datetime import date, datetime, timezone

from expense_bot.clock import local_today


def test_local_today_after_midnight_bst():
    now = datetime(2026, 10, 14, 23, 30, tzinfo=timezone.utc)
    assert local_today("Europe/London", now) == date(2026, 10, 15)


def test_local_today_gmt_winter():
    now = datetime(2026, 12, 14, 23, 30, tzinfo=timezone.utc)
    assert local_today("Europe/London", now) == date(2026, 12, 14)
