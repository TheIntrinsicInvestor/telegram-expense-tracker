"""Scheduled work. collect_hourly() decides what to send; the caller sends, then calls mark_sent().

Marking only after a successful send means a failed send is retried on the next hourly run.
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from expense_bot import db
from expense_bot.clock import local_now
from expense_bot.formatting import date_label, format_entry_line, format_report, format_weekly_summary
from expense_bot.money import fmt_money
from expense_bot.models import Recurring, User
from expense_bot.reports import ReportData, build_report

log = logging.getLogger(__name__)

REMINDER_HOUR = 9
MONTHLY_HOUR = 9
WEEKLY_HOUR = 19
SUNDAY = 6


@dataclass(frozen=True)
class Outgoing:
    user_id: int
    text: str
    kind: str  # "recurring" | "reminder" | "weekly" | "monthly"
    ref: int | str | None = None
    report: ReportData | None = None  # rendered to a card image by the sender
    undo_entry_id: int | None = None
    html: bool = False  # text uses Telegram HTML formatting


def _previous_month(today: date) -> tuple[str, date, date]:
    last_day = today.replace(day=1) - timedelta(days=1)
    return f"{last_day:%Y-%m}", last_day.replace(day=1), last_day


def catch_up(conn: sqlite3.Connection, rec: Recurring | None, today: date, notified: bool = False) -> list[int]:
    """Log every missed occurrence, each on its own date; returns the new entry ids."""
    ids = []
    while rec and rec.active and rec.next_date <= today:
        entry_id = db.materialise_occurrence(conn, rec, today, notified)
        if entry_id is not None:
            ids.append(entry_id)
        rec = db.get_recurring(conn, rec.user_id, rec.id)
    return ids


def _recurring(conn: sqlite3.Connection, user: User, today: date) -> list[Outgoing]:
    for rec in db.active_recurring(conn, user.user_id):
        catch_up(conn, rec, today)
    # Every logged occurrence whose message hasn't gone out yet, including ones that failed to send before.
    return [Outgoing(user.user_id, "Recurring: " + format_entry_line(e, user.currency, today), "recurring", e.id,
                     undo_entry_id=e.id)
            for e in db.unnotified_recurring_entries(conn, user.user_id)]


def _reminders(conn: sqlite3.Connection, user: User, today: date) -> list[Outgoing]:
    out = []
    for e in db.due_reminders(conn, user.user_id, today):
        when = "Due today" if e.date == today else f"Was due {date_label(e.date, today)}"
        text = f"{when}: {fmt_money(e.amount, user.currency)} {e.note}".rstrip()
        out.append(Outgoing(user.user_id, text, "reminder", e.id))
    return out


def collect_hourly(conn: sqlite3.Connection, now_utc: datetime) -> list[Outgoing]:
    out: list[Outgoing] = []
    for user in db.all_users(conn):
        try:
            out += _collect_user(conn, user, now_utc)
        except Exception:
            # One user's bad data must not stop everyone else's messages; they are retried next hour.
            log.exception("hourly job failed for user %s", user.user_id)
    return out


def _collect_user(conn: sqlite3.Connection, user: User, now_utc: datetime) -> list[Outgoing]:
    out: list[Outgoing] = []
    now = local_now(user.timezone, now_utc)
    today = now.date()
    out += _recurring(conn, user, today)
    if now.hour >= REMINDER_HOUR:
        out += _reminders(conn, user, today)
    if not user.notify:
        return out
    entries = db.all_entries(conn, user.user_id)
    recurring = db.active_recurring(conn, user.user_id)

    week_key = today.isoformat()
    if (today.weekday() == SUNDAY and now.hour >= WEEKLY_HOUR and user.last_weekly_sent != week_key
            and entries):
        report = build_report("week", entries, recurring, today, user.currency)
        out.append(Outgoing(user.user_id, format_weekly_summary(report), "weekly", week_key))

    month_key, month_start, month_end = _previous_month(today)
    if (now.hour >= MONTHLY_HOUR and user.last_monthly_sent != month_key
            and any(month_start <= e.date <= month_end for e in entries)):
        report = build_report("lastmonth", entries, recurring, today, user.currency)
        out.append(Outgoing(user.user_id, format_report(report), "monthly", month_key, report=report, html=True))
    return out


def mark_sent(conn: sqlite3.Connection, out: Outgoing) -> None:
    if out.kind == "recurring":
        db.mark_notified(conn, out.user_id, out.ref)
    elif out.kind == "reminder":
        db.mark_reminded(conn, out.user_id, out.ref)
    elif out.kind == "weekly":
        db.set_last_weekly(conn, out.user_id, out.ref)
    elif out.kind == "monthly":
        db.set_last_monthly(conn, out.user_id, out.ref)


def backup(db_path: Path, backup_dir: Path, today: date, keep_days: int = 14) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"expenses-{today.isoformat()}.db"
    source = sqlite3.connect(str(db_path))
    dest = sqlite3.connect(str(target))
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    cutoff = today - timedelta(days=keep_days)
    for old in backup_dir.glob("expenses-*.db"):
        try:
            stamp = date.fromisoformat(old.stem.removeprefix("expenses-"))
        except ValueError:
            continue
        if stamp < cutoff:
            old.unlink()
    return target
