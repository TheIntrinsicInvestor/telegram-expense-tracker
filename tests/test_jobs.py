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
    # Unsent notices are retried without logging the payment again.
    again = of_kind(collect_hourly(conn, utc(2026, 10, 15, 11)), "recurring")
    assert [o.ref for o in again] == [o.ref for o in out]
    assert len(db.all_entries(conn, 1)) == 2
    for o in again:
        mark_sent(conn, o)
    assert of_kind(collect_hourly(conn, utc(2026, 10, 15, 12)), "recurring") == []


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


def test_missed_reminder_sent_late_within_a_week(conn):
    db.add_entry(conn, 1, 150, "Travel", "flights", date(2026, 10, 15), date(2026, 10, 1))
    db.add_entry(conn, 1, 40, "Travel", "train", date(2026, 10, 9), date(2026, 10, 1))
    late = of_kind(collect_hourly(conn, utc(2026, 10, 17, 9)), "reminder")
    assert [o.text for o in late] == ["Was due 15 Oct 2026: £150.00 flights"]


def test_one_user_failing_does_not_stop_others(conn, monkeypatch, caplog):
    from expense_bot import jobs
    real = jobs._reminders

    def flaky(c, user, today):
        if user.user_id == 1:
            raise RuntimeError("boom")
        return real(c, user, today)

    monkeypatch.setattr(jobs, "_reminders", flaky)
    db.add_entry(conn, 2, 150, "Travel", "flights", date(2026, 10, 15), date(2026, 10, 1))
    out = of_kind(collect_hourly(conn, utc(2026, 10, 15, 9)), "reminder")
    assert [o.user_id for o in out] == [2]
    assert "user 1" in caplog.text


def test_catch_up_now_logs_due_occurrences_as_notified(conn):
    from expense_bot.jobs import catch_up
    rid = db.add_recurring(conn, 1, 12, "Subscriptions", "netflix", "monthly", date(2026, 9, 15))
    ids = catch_up(conn, db.get_recurring(conn, 1, rid), date(2026, 10, 15), notified=True)
    assert len(ids) == 2
    assert of_kind(collect_hourly(conn, utc(2026, 10, 15, 10)), "recurring") == []
