"""Turns a message like '15 lunch 31/12/26' into amount, note and date. No I/O."""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from expense_bot.money import round2
from expense_bot.recurring import FREQUENCIES

HELP_EXAMPLE = (
    "Not quite! Send the amount and what it was, in any order:\n\n"
    "15 lunch  (today)\n"
    "12 taxi 03/10  (a past date)\n"
    "150 flights 31/12/26  (planned)"
)
AMOUNT_RANGE_ERROR = "Amount must be more than 0 and at most 1,000,000."
BAD_DATE_ERROR = "That date doesn't exist."
RECURRING_HELP = "Try /recurring 12 netflix monthly or /recurring 950 rent monthly 01/11."
DATE_RANGE_ERROR = "Use a date from last year up to 10 years ahead."
RECURRING_START_ERROR = "A recurring payment can start at most 31 days ago."
NOTE_TOO_LONG = "Keep the note under 200 characters."
AMBIGUOUS_AMOUNT = "Which number is the amount? Put it first, like: 15 train zone 2"
TWO_DATES_ERROR = "Use one date per entry."

MAX_AMOUNT = 1_000_000
BACKFILL_DAYS = 7
# Bounds on explicit years, so a typo like 2006 can't create years of entries.
YEARS_BACK = 1
YEARS_AHEAD = 10
RECURRING_MAX_DAYS_BACK = 31
# Keeps every message that quotes a note well under Telegram's 4096-character limit.
MAX_NOTE_LENGTH = 200

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


def tidy_note(words: list[str]) -> str:
    """Join note words and capitalise the first letter, leaving words like 'iPhone' as typed."""
    note = " ".join(words)
    if note[:1].islower() and not note[1:2].isupper():
        note = note[0].upper() + note[1:]
    return note


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
        if not today.year - YEARS_BACK <= year <= today.year + YEARS_AHEAD:
            return ParseError(DATE_RANGE_ERROR)
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


def _take_date(tokens: list[str], today: date) -> tuple[date | None, list[str]] | ParseError:
    """Finds the one date word anywhere in the message; returns it and the other words."""
    found, rest = None, []
    for token in tokens:
        when = resolve_date(token, today)
        if isinstance(when, ParseError):
            return when
        if when is None:
            rest.append(token)
        elif found is not None:
            return ParseError(TWO_DATES_ERROR)
        else:
            found = when
    return found, rest


def _take_amount(tokens: list[str], help_text: str) -> tuple[float, list[str]] | ParseError:
    """The amount is the first word if it is a number, else the last, else the only number anywhere."""
    if not tokens:
        return ParseError(help_text)
    for i in (0, len(tokens) - 1):
        amount = parse_amount(tokens[i])
        if amount is not None:
            break
    else:
        found = [(i, a) for i, t in enumerate(tokens) if (a := parse_amount(t)) is not None]
        if not found:
            return ParseError(help_text)
        if len(found) > 1:
            return ParseError(AMBIGUOUS_AMOUNT)
        i, amount = found[0]
    if isinstance(amount, ParseError):
        return amount
    return amount, tokens[:i] + tokens[i + 1:]


def parse_entry(text: str, today: date) -> ParsedEntry | ParseError:
    """Amount, note and an optional date, in any order."""
    taken = _take_date(text.split(), today)
    if isinstance(taken, ParseError):
        return taken
    when, tokens = taken
    taken = _take_amount(tokens, HELP_EXAMPLE)
    if isinstance(taken, ParseError):
        return taken
    amount, rest = taken
    entry_date = when or today
    note = tidy_note(rest)
    if len(note) > MAX_NOTE_LENGTH:
        return ParseError(NOTE_TOO_LONG)
    return ParsedEntry(amount, note, entry_date)


def parse_recurring(args: list[str], today: date) -> ParsedRecurring | ParseError:
    """Parses '/recurring' args: amount, note, weekly|monthly|yearly and an optional start date, in any order.
    Start defaults to today."""
    taken = _take_date(list(args), today)
    if isinstance(taken, ParseError):
        return taken
    when, tokens = taken
    start = when or today
    if (today - start).days > RECURRING_MAX_DAYS_BACK:
        return ParseError(RECURRING_START_ERROR)
    frequencies = [t for t in tokens if t.lower() in FREQUENCIES]
    if len(frequencies) != 1:
        return ParseError(RECURRING_HELP)
    tokens.remove(frequencies[0])
    taken = _take_amount(tokens, RECURRING_HELP)
    if isinstance(taken, ParseError):
        return taken
    amount, rest = taken
    note = tidy_note(rest)
    if len(note) > MAX_NOTE_LENGTH:
        return ParseError(NOTE_TOO_LONG)
    return ParsedRecurring(amount, note, frequencies[0].lower(), start)
