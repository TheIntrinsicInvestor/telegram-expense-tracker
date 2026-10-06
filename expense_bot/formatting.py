"""All user-facing text: replies, reports, fixed copy and the CSV export. Plain text, no em dashes."""

import csv
import io
from datetime import date, timedelta

from expense_bot.models import Entry, Recurring
from expense_bot.money import fmt_money, fmt_signed
from expense_bot.reports import ReportData

HELP_TEXT = """Log a spend by typing the amount and what it was:
15 lunch
lunch 15
4.20 coffee pret
12 taxi 03/10   (a past date)
150 flights 31/12/26   (a future date is a planned payment)
20 groceries yesterday

Commands
/undo  delete your latest entry
/recent  your last 10 entries, to edit or delete
/report  this month (also: /report week, /report lastmonth, /report year)
/upcoming  planned payments
/recurring 12 netflix monthly  a repeating payment (/recurring alone lists them)
/notify on|off  weekly and monthly summaries
/currency CHF  change your currency
/export  download your data as CSV
/deleteaccount  erase everything
/help  this message"""

PRIVACY_TEXT = """Privacy, in plain English:
- What's stored: the amounts, notes and dates you log, your settings, and your Telegram user ID.
- Where: on a private server run by the person who runs this bot. They can technically access it.
- Nothing is shared or sold.
- /export sends you all your data as a CSV file.
- /deleteaccount erases all of it straight away. Copies in backups are removed within 14 days."""

EXPORT_WARNING = ("Your CSV will be sent in this chat. Telegram stores normal chats on its servers "
                  "and they are not end-to-end encrypted. Send it?")
DELETE_WARNING = ("This permanently deletes all your entries, recurring payments and settings. "
                  "It cannot be undone. Delete everything?")
GENERIC_ERROR = "Something went wrong, that entry was not saved."
SAVED_UNCONFIRMED = "Your entry was saved, but I couldn't confirm it. Check /recent before sending it again."
COMMAND_ERROR = "Something went wrong, try again."
EDIT_NOT_TRACKED = "Edits to sent messages aren't tracked. Use /recent to change an entry."
STALE = "That entry no longer exists."
RATE_LIMITED = "You're sending messages too fast. Wait a minute and try again."
NO_HISTORY = "Comparisons start once you have a full month of data."
NOTHING_STANDS_OUT = "Nothing stands out this period."
EMPTY_PERIOD = "Nothing logged yet this period."


def _short(d: date) -> str:
    return f"{d.day} {d:%b}"


def date_label(d: date, today: date) -> str:
    if d == today:
        return "today"
    if d == today - timedelta(days=1):
        return "yesterday"
    return f"{d.day} {d:%b %Y}"


def format_entry_line(e: Entry, currency: str, today: date) -> str:
    parts = [fmt_money(e.amount, currency), e.category]
    if e.note:
        parts.append(e.note)
    parts.append(date_label(e.date, today))
    return " · ".join(parts)


def format_logged(e: Entry, currency: str, today: date) -> str:
    verb = "Planned" if e.date > today else "Logged"
    return f"{verb} {format_entry_line(e, currency, today)}"


def format_upcoming(entries: list[Entry], currency: str, today: date) -> str:
    if not entries:
        return "Nothing planned."
    total = sum(e.amount for e in entries)
    lines = [f"Planned payments: {fmt_money(total, currency)} in total"]
    lines += [format_entry_line(e, currency, today) for e in entries]
    return "\n".join(lines)


NO_RECURRING = "No recurring payments. Add one with /recurring 12 netflix monthly."


def format_recurring_line(r: Recurring, currency: str) -> str:
    return f"{fmt_money(r.amount, currency)} · {r.category} · {r.note} · {r.frequency}, next {_short(r.next_date)}"


def format_recurring_list(recs: list[Recurring], currency: str) -> str:
    if not recs:
        return NO_RECURRING
    return "\n".join(["Recurring payments:"] + [format_recurring_line(r, currency) for r in recs])


# --- reports ---

def _title(r: ReportData) -> str:
    if r.kind == "month":
        return f"{r.start:%B %Y} so far"
    if r.kind == "lastmonth":
        return f"{r.start:%B %Y}"
    if r.kind == "week":
        return f"This week ({_short(r.start)} to {_short(r.end)})"
    return f"{r.start.year} so far"


def _compare_line(r: ReportData) -> str | None:
    if r.compare_total is None:
        return None
    change = r.total - r.compare_total
    line = f"vs {r.compare_label}: {fmt_signed(change, r.currency)}"
    if r.compare_total > 0:
        line += f" ({change / r.compare_total * 100:+.0f}%)".replace("+-", "-")
    return line


def _category_line(c, currency: str) -> str:
    line = f"{c.category} {fmt_money(c.amount, currency)} ({c.share * 100:.0f}%)"
    if c.change is not None:
        line += f" {fmt_signed(c.change, currency)} vs usual"
    return line


def _coming_up(r: ReportData) -> list[str]:
    if not r.upcoming:
        return ["Coming up (30 days): nothing planned"]
    lines = [f"Coming up (30 days): {fmt_money(r.upcoming_total, r.currency)}"]
    lines += [f"{_short(e.date)}  {fmt_money(e.amount, r.currency)} {e.note}".rstrip() for e in r.upcoming]
    return lines


def _largest_line(r: ReportData) -> str:
    items = [f"{fmt_money(e.amount, r.currency)} {e.note} ({_short(e.date)})".replace("  ", " ") for e in r.largest]
    return "Biggest: " + ", ".join(items)


def _format_year(r: ReportData) -> str:
    lines = [_title(r), "", f"Spent: {fmt_money(r.total, r.currency)}",
             f"No-spend days: {r.no_spend_days} of {r.tracked_days}"]
    if r.categories:
        lines += ["", "Top categories"] + [_category_line(c, r.currency) for c in r.categories[:5]]
    lines.append("")
    if r.worst_month:
        lines.append(f"Most expensive month: {r.worst_month[0]} {fmt_money(r.worst_month[1], r.currency)}")
    if r.best_month:
        lines.append(f"Cheapest month: {r.best_month[0]} {fmt_money(r.best_month[1], r.currency)}")
    if r.largest:
        e = r.largest[0]
        lines.append(f"Largest expense: {fmt_money(e.amount, r.currency)} {e.note} ({_short(e.date)})".replace("  ", " "))
    lines.append(f"Recurring payments: {fmt_money(r.recurring_annual, r.currency)}/year")
    return "\n".join(lines)


def format_report(r: ReportData) -> str:
    if r.kind == "year":
        return _format_year(r)
    lines = [_title(r), ""]
    if not r.categories:
        lines.append(EMPTY_PERIOD)
        return "\n".join(lines + [""] + _coming_up(r))

    lines.append(f"Spent: {fmt_money(r.total, r.currency)}")
    compare = _compare_line(r)
    if compare:
        lines.append(compare)
    if r.projected is not None:
        lines.append(f"Projected month-end: {fmt_money(r.projected, r.currency)}")
    lines.append(f"No-spend days: {r.no_spend_days} of {r.tracked_days}")
    if not r.has_history:
        lines.append(NO_HISTORY)

    lines += ["", "By category"] + [_category_line(c, r.currency) for c in r.categories]
    lines += ["", "Where to save"] + ([t.text for t in r.tips] or [NOTHING_STANDS_OUT])
    lines += ["", "Patterns",
              f"Weekdays {fmt_money(r.weekday_avg, r.currency)}/day · Weekends {fmt_money(r.weekend_avg, r.currency)}/day",
              _largest_line(r)]
    lines += [""] + _coming_up(r)
    return "\n".join(lines)


def format_weekly_summary(r: ReportData) -> str:
    line = f"This week so far: {fmt_money(r.total, r.currency)}"
    if r.compare_total is not None:
        line += f" ({fmt_signed(r.total - r.compare_total, r.currency)} vs last week)"
    lines = [line]
    if r.categories:
        top = r.categories[0]
        lines.append(f"Top category: {top.category} {fmt_money(top.amount, r.currency)}")
    lines.append("Tip: " + (r.tips[0].text if r.tips else NOTHING_STANDS_OUT))
    lines.append("Full breakdown: /report week")
    return "\n".join(lines)


# --- export ---

def export_csv(entries: list[Entry], currency: str, today: date) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["date", "amount", "currency", "category", "note", "planned", "recurring"])
    for e in entries:
        writer.writerow([e.date.isoformat(), f"{e.amount:.2f}", currency, e.category, e.note,
                         "yes" if e.date > today else "no", "yes" if e.recurring_id is not None else "no"])
    return buf.getvalue().encode("utf-8-sig")
