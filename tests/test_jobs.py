import sqlite3
from datetime import date, datetime, timezone

import pytest

from expense_bot import db
from expense_bot.jobs import backup, collect_hourly, mark_sent

JOINED = date(2026, 9, 1)  # so last_monthly_sent starts as "2026-08"


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def of_kind(out, kind):
    return [o for o in out if o.kind == kind]


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.ensure_user(c, 1, JOINED)
    db.ensure_user(c, 2, JOINED)
    return c


def test_recurring_catch_up_and_idempotent(conn):
    db.add_recurring(conn, 1, 12, "Subscriptions", "netflix", "monthly", date(2026, 8, 31))
    out = of_kind(collect_hourly(conn, utc(2026, 10, 15, 10)), "recurring")
    assert len(out) == 2 and all(o.undo_entry_id for o in out)
    assert out[0].text == "Recurring: £12.00 · Subscriptions · netflix · 31 Aug 2026"
    assert [e.date for e in db.all_entries(conn, 1)] == [date(2026, 8, 31), date(2026, 9, 30)]
    assert of_kind(collect_hourly(conn, utc(2026, 10, 15, 11)), "recurring") == []


def test_reminder_timing_and_retry(conn):
    db.add_entry(conn, 1, 150, "Travel", "flights", date(2026, 10, 15), date(2026, 10, 1))
    assert of_kind(collect_hourly(conn, utc(2026, 10, 15, 7, 30)), "reminder") == []  # 08:30 London
    r1 = of_kind(collect_hourly(conn, utc(2026, 10, 15, 8, 0)), "reminder")  # 09:00 London
    assert [o.text for o in r1] == ["Due today: £150.00 flights"]
    assert of_kind(collect_hourly(conn, utc(2026, 10, 15, 9, 0)), "reminder")  # not marked, so retried
    mark_sent(conn, r1[0])
    assert of_kind(collect_hourly(conn, utc(2026, 10, 15, 10, 0)), "reminder") == []


def test_weekly_once_and_notify_off(conn):
    db.add_entry(conn, 1, 20, "Eating Out", "lunch", date(2026, 10, 12), date(2026, 10, 12))
    assert of_kind(collect_hourly(conn, utc(2026, 10, 18, 17, 0)), "weekly") == []  # 18:00 London
    weekly = of_kind(collect_hourly(conn, utc(2026, 10, 18, 18, 0)), "weekly")  # Sunday 19:00 London
    assert [o.user_id for o in weekly] == [1]  # user 2 has never logged anything
    assert weekly[0].text.startswith("This week so far: £20.00")
    assert of_kind(collect_hourly(conn, utc(2026, 10, 18, 19, 0)), "weekly")  # unmarked, so retried
    mark_sent(conn, weekly[0])
    assert of_kind(collect_hourly(conn, utc(2026, 10, 18, 19, 0)), "weekly") == []


def test_weekly_respects_notify_off(conn):
    db.add_entry(conn, 1, 20, "Eating Out", "lunch", date(2026, 10, 12), date(2026, 10, 12))
    db.set_notify(conn, 1, False)
    assert of_kind(collect_hourly(conn, utc(2026, 10, 18, 18, 0)), "weekly") == []


def test_monthly_once(conn):
    db.add_entry(conn, 1, 30, "Groceries", "tesco", date(2026, 9, 10), date(2026, 9, 10))
    assert of_kind(collect_hourly(conn, utc(2026, 10, 1, 7, 0)), "monthly") == []  # 08:00 London
    monthly = of_kind(collect_hourly(conn, utc(2026, 10, 1, 8, 0)), "monthly")
    assert [o.user_id for o in monthly] == [1]  # user 2 logged nothing in September
    assert monthly[0].report.kind == "lastmonth" and monthly[0].report.start == date(2026, 9, 1)
    assert monthly[0].html is True
    mark_sent(conn, monthly[0])
    assert of_kind(collect_hourly(conn, utc(2026, 10, 1, 9, 0)), "monthly") == []


def test_backup_and_prune(tmp_path):
    live = tmp_path / "expenses.db"
    c = db.connect(live)
    db.ensure_user(c, 1, JOINED)
    db.add_entry(c, 1, 15, "Eating Out", "lunch", JOINED, JOINED)
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "expenses-2026-09-01.db").write_bytes(b"old")
    (backups / "expenses-2026-09-30.db").write_bytes(b"recent")
    path = backup(live, backups, date(2026, 10, 6))
    assert path == backups / "expenses-2026-10-06.db"
    copy = sqlite3.connect(path)
    assert copy.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 1
    copy.close()
    assert sorted(p.name for p in backups.iterdir()) == ["expenses-2026-09-30.db", "expenses-2026-10-06.db"]
