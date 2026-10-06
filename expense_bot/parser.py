"""Turns a message like '15 lunch 31/12/26' into amount, note and date. No I/O."""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from expense_bot.money import round2
from expense_bot.recurring import FREQUENCIES

HELP_EXAMPLE = "Try 15 lunch or 150 flights 31/12/26."
AMOUNT_RANGE_ERROR = "Amount must be more than 0 and at most 1,000,000."
BAD_DATE_ERROR = "That date doesn't exist."
RECURRING_HELP = "Try /recurring 12 netflix monthly or /recurring 950 rent monthly 01/11."

MAX_AMOUNT = 1_000_000
BACKFILL_DAYS = 7

_AMOUNT_RE = re.compile(r"^[£$€]?(\d{1,3}(?:,\d{3})+|\d+)(\.\d{1,2})?$")
_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?$")
# How many years to search for a valid day/month (covers 29/02 across leap years).
_YEAR_SEARCH = 8


@dataclass(frozen=True)
class ParsedEntry:
    amount: float
    note: str
    date: date


@dataclass(frozen=True)
class ParsedRecurring:
    amount: float
    note: str
    frequency: str
    start: date


@dataclass(frozen=True)
class ParseError:
    message: str


def parse_amount(token: str) -> float | ParseError | None:
    match = _AMOUNT_RE.match(token)
    if not match:
        return None
    value = round2(float(match.group(1).replace(",", "") + (match.group(2) or "")))
    if value <= 0 or value > MAX_AMOUNT:
        return ParseError(AMOUNT_RANGE_ERROR)
    return value


def _make_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def resolve_date(token: str, today: date) -> date | ParseError | None:
    word = token.lower()
    if word == "today":
        return today
    if word == "yesterday":
        return today - timedelta(days=1)
    match = _DATE_RE.match(token)
    if not match:
        return None
    day, month, year_text = int(match.group(1)), int(match.group(2)), match.group(3)
    if year_text:
        year = int(year_text) + (2000 if len(year_text) == 2 else 0)
        return _make_date(year, month, day) or ParseError(BAD_DATE_ERROR)

    # No year: backfill if it fell within the past week, otherwise the next occurrence.
    for year in range(today.year, today.year - _YEAR_SEARCH, -1):
        past = _make_date(year, month, day)
        if past and past <= today:
            if (today - past).days <= BACKFILL_DAYS:
                return past
            break
    for year in range(today.year, today.year + _YEAR_SEARCH):
        future = _make_date(year, month, day)
        if future and future > today:
            return future
    return ParseError(BAD_DATE_ERROR)


def parse_entry(text: str, today: date) -> ParsedEntry | ParseError:
    tokens = text.split()
    if not tokens:
        return ParseError(HELP_EXAMPLE)

    entry_date = today
    when = resolve_date(tokens[-1], today)
    if isinstance(when, ParseError):
        return when
    if when is not None:
        entry_date = when
        tokens = tokens[:-1]
    if not tokens:
        return ParseError(HELP_EXAMPLE)

    amount = parse_amount(tokens[0])
    if amount is not None:
        rest = tokens[1:]
    else:
        amount = parse_amount(tokens[-1])
        rest = tokens[:-1]
    if amount is None:
        return ParseError(HELP_EXAMPLE)
    if isinstance(amount, ParseError):
        return amount
    return ParsedEntry(amount, " ".join(rest), entry_date)


def parse_recurring(args: list[str], today: date) -> ParsedRecurring | ParseError:
    """Parses '/recurring <amount> <note...> <weekly|monthly|yearly> [start date]'. Start defaults to today."""
    tokens = list(args)
    start = today
    if tokens:
        when = resolve_date(tokens[-1], today)
        if isinstance(when, ParseError):
            return when
        if when is not None:
            start = when
            tokens = tokens[:-1]
    if len(tokens) < 2 or tokens[-1].lower() not in FREQUENCIES:
        return ParseError(RECURRING_HELP)
    amount = parse_amount(tokens[0])
    if amount is None:
        return ParseError(RECURRING_HELP)
    if isinstance(amount, ParseError):
        return amount
    return ParsedRecurring(amount, " ".join(tokens[1:-1]), tokens[-1].lower(), start)
