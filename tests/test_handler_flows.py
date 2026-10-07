"""Handlers driven with stand-in update/context objects: no network, real in-memory database."""

import asyncio
import time
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.ext import ApplicationHandlerStop

from expense_bot import db, handlers, jobs
from expense_bot.formatting import RATE_LIMITED
from expense_bot.ratelimit import RateLimiter

NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
TODAY = date(2026, 10, 6)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(handlers, "utc_now", lambda: NOW)


@pytest.fixture
def conn():
    return db.connect(":memory:")


def fake(conn, text=None, args=None, user_data=None, query=None):
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1), message=message, update_id=5,
                             effective_message=message, callback_query=query)
    context = SimpleNamespace(bot_data={"conn": conn, "limiter": RateLimiter(limit=1)},
                              user_data={} if user_data is None else user_data, args=args or [])
    return update, context


def run(handler, update, context):
    asyncio.run(handler(update, context))


def buttons(reply_mock):
    markup = reply_mock.call_args.kwargs["reply_markup"]
    return [b.text for row in markup.inline_keyboard for b in row]


def test_uncategorised_entry_offers_undo(conn):
    update, context = fake(conn, "15 zzqx")
    run(handlers.on_text, update, context)
    assert "Undo" in buttons(update.message.reply_text)


def test_update_reply_says_when_entry_is_planned(conn):
    db.ensure_user(conn, 1, TODAY)
    entry_id = db.add_entry(conn, 1, 15, "Travel", "Flights", TODAY, TODAY)
    update, context = fake(conn, "16 flights 20/10", user_data={"editing": entry_id, "editing_at": time.monotonic()})
    run(handlers.on_text, update, context)
    assert update.message.reply_text.call_args.args[0].startswith("Updated (planned) £16.00")


def test_edit_mode_expires(conn):
    db.ensure_user(conn, 1, TODAY)
    entry_id = db.add_entry(conn, 1, 15, "Travel", "Flights", TODAY, TODAY)
    stale = {"editing": entry_id, "editing_at": time.monotonic() - handlers.EDIT_TIMEOUT_SECONDS - 1}
    update, context = fake(conn, "4 coffee", user_data=stale)
    run(handlers.on_text, update, context)
    assert update.message.reply_text.call_args.args[0].startswith("Logged £4.00")
    assert len(db.all_entries(conn, 1)) == 2
    assert "editing" not in context.user_data


def test_rate_limited_button_tap_is_answered(conn):
    query = SimpleNamespace(answer=AsyncMock())
    update, context = fake(conn, query=query)
    run(handlers.gate, update, context)  # limit is 1: this tap is allowed
    for _ in range(2):  # over the limit: warned once, then dropped
        with pytest.raises(ApplicationHandlerStop):
            run(handlers.gate, update, context)
    assert [c.args for c in query.answer.call_args_list] == [(RATE_LIMITED,), ()]
    update.message.reply_text.assert_not_called()


def test_recurring_starting_today_is_logged_at_once(conn):
    update, context = fake(conn, args=["12", "netflix", "monthly"])
    run(handlers.cmd_recurring, update, context)
    [entry] = db.all_entries(conn, 1)
    assert entry.date == TODAY and entry.recurring_id is not None
    assert "Logged today's payment." in update.message.reply_text.call_args.args[0]
    # Already confirmed in the reply, so the hourly job doesn't announce it again.
    assert [o for o in jobs.collect_hourly(conn, NOW) if o.kind == "recurring"] == []
