"""Rule-based spending reports. Entries in, numbers and tips out; no formatting beyond tip text.

Planned entries (dated after today) never count as spending until their date arrives.
"""

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from expense_bot.categories import CATEGORIES, first_word
from expense_bot.models import Entry, Recurring
from expense_bot.money import fmt_money, round2
from expense_bot.recurring import annual_cost

KINDS = ("month", "week", "lastmonth", "year")
BASELINE_MONTHS = 3
BASELINE_WEEKS = 4
UPCOMING_DAYS = 30
MAX_TIPS = 3
# "Above usual" fires only when spend beats the usual level by more than both of these.
ABOVE_USUAL_MIN = 10.0
ABOVE_USUAL_RATIO = 1.2
# "Repeated small item" thresholds.
REPEAT_MIN_COUNT = 5
REPEAT_MAX_AVG = 15.0

_MONTH_ABBR = list(calendar.month_abbr)  # ["", "Jan", ...]


@dataclass(frozen=True)
class CategoryLine:
    category: str
    amount: float
    share: float
    usual: float | None
    change: float | None


@dataclass(frozen=True)
class Tip:
    kind: str
    value: float
    text: str


@dataclass(frozen=True)
class ReportData:
    kind: str
    start: date
    end: date
    today: date
    currency: str
    total: float
    compare_total: float | None
    compare_label: str
    projected: float | None
    no_spend_days: int
    tracked_days: int
    days_elapsed: int
    categories: list[CategoryLine]
    tips: list[Tip]
    weekday_avg: float
    weekend_avg: float
    largest: list[Entry]
    upcoming: list[Entry]
    upcoming_total: float
    pace: list[float] | None
    baseline_pace: list[float] | None
    monthly_totals: list[tuple[str, float]] | None
    best_month: tuple[str, float] | None
    worst_month: tuple[str, float] | None
    recurring_annual: float
    has_history: bool


# --- calendar helpers ---

def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _month_range(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, _days_in_month(year, month))


def _period(kind: str, today: date) -> tuple[date, date]:
    if kind == "month":
        return _month_range(today.year, today.month)
    if kind == "lastmonth":
        return _month_range(*_shift_month(today.year, today.month, -1))
    if kind == "week":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    if kind == "year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    raise ValueError(f"unknown report kind: {kind}")


def _between(entries: list[Entry], start: date, end: date) -> list[Entry]:
    return [e for e in entries if start <= e.date <= end]


def _total(entries: list[Entry]) -> float:
    return round2(sum(e.amount for e in entries))


def _by_category(entries: list[Entry]) -> dict[str, float]:
    sums: dict[str, float] = defaultdict(float)
    for e in entries:
        sums[e.category] += e.amount
    return sums


# --- baseline ("usual level") ---

def _baseline_ranges(kind: str, start: date, entries: list[Entry]) -> list[tuple[date, date]]:
    """Earlier periods that contain data, used to define the user's usual level."""
    if kind in ("month", "lastmonth"):
        candidates = [_month_range(*_shift_month(start.year, start.month, -k)) for k in range(1, BASELINE_MONTHS + 1)]
    elif kind == "week":
        candidates = [(start - timedelta(days=7 * k), start - timedelta(days=7 * k - 6))
                      for k in range(1, BASELINE_WEEKS + 1)]
    else:
        return []
    return [(s, e) for s, e in candidates if _between(entries, s, e)]


def _usual_by_category(entries: list[Entry], ranges: list[tuple[date, date]]) -> dict[str, float]:
    sums: dict[str, float] = defaultdict(float)
    for s, e in ranges:
        for cat, amount in _by_category(_between(entries, s, e)).items():
            sums[cat] += amount
    return {cat: amount / len(ranges) for cat, amount in sums.items()}


def _compare(kind: str, start: date, today: date, entries: list[Entry]) -> tuple[float, str]:
    if kind == "month":
        year, month = _shift_month(start.year, start.month, -1)
        end_day = min(today.day, _days_in_month(year, month))
        return _total(_between(entries, date(year, month, 1), date(year, month, end_day))), "same point last month"
    if kind == "week":
        return _total(_between(entries, start - timedelta(days=7), start - timedelta(days=1))), "last week"
    s, e = _month_range(*_shift_month(start.year, start.month, -1))
    return _total(_between(entries, s, e)), "the month before"


# --- tips ---

def _above_usual_tips(kind, categories, factor, currency) -> list[Tip]:
    tips = []
    period_word = "week" if kind == "week" else "month"
    for c in categories:
        if c.usual is None:
            continue
        excess = c.amount - c.usual
        if round2(excess) > ABOVE_USUAL_MIN and c.amount > c.usual * ABOVE_USUAL_RATIO:
            value = round2(excess / factor if kind in ("month", "week") else excess)
            text = (f"{c.category} is {fmt_money(excess, currency)} above usual. "
                    f"Getting back to usual saves about {fmt_money(value, currency)} this {period_word}.")
            tips.append(Tip("above_usual", value, text))
    return tips


def _repeated_tips(spent, days_elapsed, currency) -> list[Tip]:
    groups: dict[str, list[float]] = defaultdict(list)
    for e in spent:
        word = first_word(e.note)
        if word:
            groups[word].append(e.amount)
    tips = []
    for word, amounts in groups.items():
        total = sum(amounts)
        if len(amounts) >= REPEAT_MIN_COUNT and total / len(amounts) <= REPEAT_MAX_AVG:
            value = round2(total * 365 / days_elapsed / 2)
            text = (f"{word} ×{len(amounts)} ({fmt_money(total, currency)}). "
                    f"Half as often saves about {fmt_money(value, currency)} a year.")
            tips.append(Tip("repeated", value, text))
    return tips


def _recurring_tip(recurring, annual, currency) -> list[Tip]:
    if not recurring:
        return []
    names = ", ".join(r.note for r in recurring)
    text = (f"Recurring payments: {fmt_money(annual / 12, currency)}/month, "
            f"{fmt_money(annual, currency)}/year ({names}).")
    return [Tip("recurring", annual, text)]


# --- pace and year blocks ---

def _cumulative(entries: list[Entry], year: int, month: int, days: int) -> list[float]:
    per_day = [0.0] * (days + 1)
    for e in entries:
        if e.date.year == year and e.date.month == month and e.date.day <= days:
            per_day[e.date.day] += e.amount
    running, out = 0.0, []
    for d in range(1, days + 1):
        running += per_day[d]
        out.append(round2(running))
    return out


def _baseline_pace(entries, ranges, days_in_period_month) -> list[float]:
    curves = [_cumulative(entries, s.year, s.month, e.day) for s, e in ranges]
    return [round2(sum(curve[min(d, len(curve)) - 1] for curve in curves) / len(curves))
            for d in range(1, days_in_period_month + 1)]


def _year_blocks(spent, today):
    totals = [(_MONTH_ABBR[m], _total([e for e in spent if e.date.month == m])) for m in range(1, today.month + 1)]
    completed = [(i, name, value) for i, (name, value) in enumerate(totals) if i + 1 < today.month and value > 0]
    if not completed:
        return totals, None, None
    best = min(completed, key=lambda t: (t[2], t[0]))
    worst = max(completed, key=lambda t: (t[2], -t[0]))
    return totals, (best[1], best[2]), (worst[1], worst[2])


# --- entry point ---

def build_report(kind: str, entries: list[Entry], recurring: list[Recurring], today: date,
                 currency: str) -> ReportData:
    start, end = _period(kind, today)
    elapsed_end = min(end, today)
    days_elapsed = (elapsed_end - start).days + 1
    spent = _between(entries, start, elapsed_end)
    total = _total(spent)

    ranges = _baseline_ranges(kind, start, entries)
    if kind == "year":
        has_history = any(e.date < start for e in entries)
    else:
        has_history = bool(ranges)

    if kind == "month":
        factor = days_elapsed / _days_in_month(start.year, start.month)
    elif kind == "week":
        factor = days_elapsed / 7
    else:
        factor = 1.0
    usual = _usual_by_category(entries, ranges) if has_history and kind != "year" else None

    sums = _by_category(spent)
    ordered = sorted(sums, key=lambda c: (-sums[c], CATEGORIES.index(c) if c in CATEGORIES else len(CATEGORIES)))
    categories = []
    for cat in ordered:
        amount = round2(sums[cat])
        cat_usual = usual.get(cat, 0.0) * factor if usual is not None else None
        categories.append(CategoryLine(
            cat, amount, amount / total if total else 0.0, cat_usual,
            amount - cat_usual if cat_usual is not None else None,
        ))

    compare_total, compare_label = (None, "")
    if has_history and kind != "year":
        compare_total, compare_label = _compare(kind, start, today, entries)

    recurring_annual = round2(sum(annual_cost(r.amount, r.frequency) for r in recurring))
    tips = (_above_usual_tips(kind, categories, factor, currency)
            + _repeated_tips(spent, days_elapsed, currency)
            + _recurring_tip(recurring, recurring_annual, currency))
    tips = sorted(tips, key=lambda t: -t.value)[:MAX_TIPS]

    projected = None
    if kind == "month":
        planned_rest = _total([e for e in entries if today < e.date <= end])
        projected = round2(total / days_elapsed * _days_in_month(start.year, start.month) + planned_rest)

    spend_days = {e.date for e in spent}
    days = [start + timedelta(days=i) for i in range(days_elapsed)]
    # No-spend days only count from the user's first entry, so a new user doesn't look idle before joining.
    first = min((e.date for e in entries), default=start)
    tracked = [d for d in days if d >= first] if first <= elapsed_end else days
    weekend_days = [d for d in days if d.weekday() >= 5]
    weekday_days = [d for d in days if d.weekday() < 5]
    weekend_spend = sum(e.amount for e in spent if e.date.weekday() >= 5)
    weekday_spend = sum(e.amount for e in spent if e.date.weekday() < 5)

    upcoming = sorted((e for e in entries if today < e.date <= today + timedelta(days=UPCOMING_DAYS)),
                      key=lambda e: (e.date, e.id))

    pace = baseline_pace = None
    if kind in ("month", "lastmonth"):
        pace = _cumulative(spent, start.year, start.month, days_elapsed)
        if has_history:
            baseline_pace = _baseline_pace(entries, ranges, _days_in_month(start.year, start.month))

    monthly_totals = best_month = worst_month = None
    if kind == "year":
        monthly_totals, best_month, worst_month = _year_blocks(spent, today)

    return ReportData(
        kind=kind, start=start, end=end, today=today, currency=currency, total=total,
        compare_total=compare_total, compare_label=compare_label, projected=projected,
        no_spend_days=sum(1 for d in tracked if d not in spend_days), tracked_days=len(tracked),
        days_elapsed=days_elapsed,
        categories=categories, tips=tips,
        weekday_avg=round2(weekday_spend / len(weekday_days)) if weekday_days else 0.0,
        weekend_avg=round2(weekend_spend / len(weekend_days)) if weekend_days else 0.0,
        largest=sorted(spent, key=lambda e: (-e.amount, e.id))[:3],
        upcoming=upcoming, upcoming_total=_total(upcoming),
        pace=pace, baseline_pace=baseline_pace,
        monthly_totals=monthly_totals, best_month=best_month, worst_month=worst_month,
        recurring_annual=recurring_annual, has_history=has_history,
    )
