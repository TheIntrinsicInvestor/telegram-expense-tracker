from datetime import date

import pytest

from expense_bot.db import (
    active_recurring,
    add_entry,
    add_recurring,
    all_entries,
    connect,
    delete_entry,
    delete_user,
    due_reminders,
    ensure_user,
    get_entry,
    get_recurring,
    get_user,
    latest_entry,
    learn_word,
    learned_words,
    mark_reminded,
    materialise_occurrence,
    recent_entries,
    set_currency,
    set_entry_category,
    stop_recurring,
    upcoming_entries,
    update_entry,
)

TODAY = date(2026, 10, 6)


@pytest.fixture
def conn():
    c = connect(":memory:")
    ensure_user(c, 1, TODAY)
    ensure_user(c, 2, TODAY)
    return c


def test_schema_version(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1


def test_ensure_user_defaults(conn):
    u = get_user(conn, 1)
    assert (u.currency, u.timezone, u.notify, u.last_monthly_sent) == ("GBP", "Europe/London", True, "2026-09")


def test_ensure_user_keeps_currency(conn):
    set_currency(conn, 1, "EUR")
    ensure_user(conn, 1, TODAY)
    assert get_user(conn, 1).currency == "EUR"


def test_add_entry_rounds(conn):
    eid = add_entry(conn, 1, 15.499999, "Eating Out", "lunch", TODAY, TODAY)
    assert get_entry(conn, 1, eid).amount == 15.5


def test_reminded_flag(conn):
    past = add_entry(conn, 1, 5, "Other", "", TODAY, TODAY)
    fut = add_entry(conn, 1, 150, "Travel", "flights", date(2026, 12, 31), TODAY)
    assert get_entry(conn, 1, past).reminded and not get_entry(conn, 1, fut).reminded


def test_latest_is_highest_id_not_latest_date(conn):
    add_entry(conn, 1, 150, "Travel", "flights", date(2026, 12, 31), TODAY)
    b = add_entry(conn, 1, 5, "Other", "", TODAY, TODAY)
    assert latest_entry(conn, 1).id == b


def test_recent_newest_first(conn):
    a = add_entry(conn, 1, 1, "Other", "", TODAY, TODAY)
    b = add_entry(conn, 1, 2, "Other", "", TODAY, TODAY)
    assert [e.id for e in recent_entries(conn, 1)] == [b, a]


def test_isolation(conn):
    eid = add_entry(conn, 1, 15, "Eating Out", "lunch", TODAY, TODAY)
    assert get_entry(conn, 2, eid) is None
    assert delete_entry(conn, 2, eid) is False
    assert set_entry_category(conn, 2, eid, "Gifts") is False
    assert update_entry(conn, 2, eid, 1, "Gifts", "x", TODAY, TODAY) is False
    assert get_entry(conn, 1, eid).category == "Eating Out"
    assert all_entries(conn, 2) == []


def test_update_entry(conn):
    eid = add_entry(conn, 1, 15, "Eating Out", "lunch", TODAY, TODAY)
    assert update_entry(conn, 1, eid, 16, "Eating Out", "lunch", date(2026, 10, 5), TODAY)
    e = get_entry(conn, 1, eid)
    assert (e.amount, e.date) == (16.0, date(2026, 10, 5))


def test_delete_twice_returns_false(conn):
    eid = add_entry(conn, 1, 15, "Other", "", TODAY, TODAY)
    assert delete_entry(conn, 1, eid) is True
    assert delete_entry(conn, 1, eid) is False


def test_delete_user_cascades(conn):
    add_entry(conn, 1, 15, "Other", "", TODAY, TODAY)
    learn_word(conn, 1, "pret", "Eating Out")
    add_recurring(conn, 1, 12, "Subscriptions", "netflix", "monthly", TODAY)
    keep = add_entry(conn, 2, 9, "Other", "", TODAY, TODAY)
    delete_user(conn, 1)
    assert get_user(conn, 1) is None
    assert all_entries(conn, 1) == [] and learned_words(conn, 1) == {} and active_recurring(conn, 1) == []
    assert get_entry(conn, 2, keep) is not None


def test_upcoming_and_due_reminders(conn):
    fut = add_entry(conn, 1, 150, "Travel", "flights", date(2026, 10, 20), TODAY)
    assert [e.id for e in upcoming_entries(conn, 1, TODAY)] == [fut]
    assert [e.id for e in due_reminders(conn, 1, date(2026, 10, 20))] == [fut]
    mark_reminded(conn, 1, fut)
    assert due_reminders(conn, 1, date(2026, 10, 20)) == []


def test_learn_word_upsert(conn):
    learn_word(conn, 1, "pret", "Eating Out")
    learn_word(conn, 1, "pret", "Groceries")
    assert learned_words(conn, 1) == {"pret": "Groceries"}


def test_materialise_once(conn):
    rid = add_recurring(conn, 1, 12, "Subscriptions", "netflix", "monthly", date(2026, 10, 6))
    rec = get_recurring(conn, 1, rid)
    assert materialise_occurrence(conn, rec, TODAY) is not None
    assert materialise_occurrence(conn, rec, TODAY) is None
    assert get_recurring(conn, 1, rid).next_date == date(2026, 11, 6)
    entries = all_entries(conn, 1)
    assert len(entries) == 1 and entries[0].recurring_id == rid


def test_stop_recurring_twice(conn):
    rid = add_recurring(conn, 1, 12, "Subscriptions", "netflix", "monthly", TODAY)
    assert stop_recurring(conn, 2, rid) is False
    assert stop_recurring(conn, 1, rid) is True
    assert stop_recurring(conn, 1, rid) is False
    assert active_recurring(conn, 1) == []
