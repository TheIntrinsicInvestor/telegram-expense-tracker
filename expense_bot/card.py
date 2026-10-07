"""Builds the report card: one self-contained HTML page (fonts embedded, charts as inline SVG).

Design: a private-bank statement. Ink-blue figures in a tabular serif, quiet slate labels,
one rule under the heading, and colour reserved for a single meaning (oxblood = over usual).
"""

import base64
import calendar
import math
from functools import cache
from html import escape
from pathlib import Path

from expense_bot.money import fmt_money, round2
from expense_bot.reports import ReportData, notably_above

FONTS = Path(__file__).parent / "assets" / "fonts"
MINUS = "−"

INK = "#1B2A4A"
SLATE = "#5D6778"
MIST = "#9AA3B2"
RULE = "#E3E7EE"
OVER = "#9B2C3B"

CHART_WIDTH = 632  # card inner width in CSS px


@cache
def _font_face() -> str:
    def face(family: str, file: str, weights: str) -> str:
        data = base64.b64encode((FONTS / file).read_bytes()).decode("ascii")
        return (f'@font-face{{font-family:"{family}";src:url(data:font/woff2;base64,{data}) format("woff2");'
                f"font-weight:{weights};font-display:block}}")
    return face("Source Serif 4", "SourceSerif4.woff2", "200 900") + face("Instrument Sans", "InstrumentSans.woff2",
                                                                            "400 700")


_CSS = f"""
:root{{--ink:{INK};--slate:{SLATE};--mist:{MIST};--rule:{RULE};--over:{OVER}}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#EEF0F4;color:var(--ink);font-family:"Instrument Sans",sans-serif;-webkit-font-smoothing:antialiased}}
.page{{width:752px;padding:16px;background:#EEF0F4}}
.card{{background:#fff;border:1px solid #DCE1E9;border-radius:14px;padding:38px 44px 34px}}
.num{{font-family:"Source Serif 4",serif;font-variant-numeric:tabular-nums lining-nums}}
.head{{display:flex;justify-content:space-between;align-items:baseline;padding-bottom:16px;border-bottom:1px solid var(--rule)}}
.title{{font-family:"Source Serif 4",serif;font-weight:600;font-size:26px;letter-spacing:-0.01em}}
.sub{{font-size:14px;color:var(--slate)}}
.hero{{margin-top:30px}}
.hero .num{{font-size:62px;line-height:1;letter-spacing:-0.025em}}
.label{{font-size:13.5px;color:var(--slate);margin-top:8px}}
.stats{{display:flex;gap:44px;margin-top:28px}}
.stats .num{{font-size:24px;line-height:1.1}}
.stats .over{{color:var(--over)}}
.note{{font-size:13.5px;color:var(--slate);margin-top:22px}}
section{{margin-top:36px}}
h2{{display:flex;justify-content:space-between;align-items:baseline;font-size:14.5px;font-weight:600;margin-bottom:12px}}
.legend{{font-size:12.5px;font-weight:400;color:var(--slate);display:flex;gap:18px;align-items:center}}
.legend i{{display:inline-block;width:18px;height:0;vertical-align:middle;margin-right:6px}}
.cat{{display:grid;grid-template-columns:128px 1fr 92px 48px 84px;gap:14px;align-items:center;height:34px}}
.cat .name{{font-size:14.5px}}
.track{{position:relative;height:10px}}
.bar{{position:absolute;left:0;top:0;bottom:0;min-width:3px;background:var(--ink);border-radius:0 2px 2px 0}}
.tick{{position:absolute;top:-5px;width:2px;height:20px;margin-left:-1px;background:var(--slate);border-radius:1px}}
.amt{{font-size:16.5px;text-align:right}}
.share,.chg{{font-size:13px;color:var(--slate);text-align:right}}
.chg.over{{color:var(--over)}}
.foot{{font-size:12.5px;color:var(--mist);margin-top:10px}}
.patterns{{display:grid;grid-template-columns:1fr 1.4fr;column-gap:44px;row-gap:12px;padding-top:26px;border-top:1px solid var(--rule)}}
.patterns .wide{{grid-column:1 / -1;margin-top:0}}
.avg{{font-size:14px;color:var(--slate);line-height:2}}
.avg .num{{font-size:18px;color:var(--ink);margin-right:4px}}
.largest{{list-style:none}}
.largest li{{display:grid;grid-template-columns:92px 1fr auto;gap:12px;align-items:baseline;font-size:14px;line-height:2}}
.largest .num{{font-size:16px;text-align:right}}
.largest .when{{color:var(--slate)}}
.empty{{margin-top:30px;font-size:16px;line-height:1.6}}
.empty p+p{{color:var(--slate)}}
"""


# --- small formatters ---

def _money(amount: float, currency: str) -> str:
    return fmt_money(amount, currency).replace("-", MINUS)


def _signed(amount: float, currency: str) -> str:
    value = round2(amount)
    sign = "+" if value > 0 else ""
    return sign + _money(value, currency)


def _short(amount: float, currency: str) -> str:
    """Chart-label money, rounded to whole units: labels should be glanceable, the table has the pence."""
    return _money(round(amount), currency)[:-3]


def _pct(change: float, base: float) -> str:
    return f"{change / base * 100:+.0f}%".replace("-", MINUS)


def _nice_step(raw: float) -> float:
    if raw <= 0:
        return 1.0
    power = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * power:
            return m * power
    return 10 * power


# --- charts (inline SVG) ---

def _pace_svg(r: ReportData) -> str:
    days = calendar.monthrange(r.start.year, r.start.month)[1]
    actual, usual = r.pace or [], r.baseline_pace or []
    width, height = CHART_WIDTH, 210
    left, right, top, bottom = 50, 96, 14, 28
    pw, ph = width - left - right, height - top - bottom
    vmax = max(actual + usual + [0.0])
    step = _nice_step(vmax / 3)
    ymax = step * max(1, math.ceil(vmax / step))

    def x(day: int) -> float:
        return left + (day - 1) / (days - 1) * pw

    def y(value: float) -> float:
        return top + ph - value / ymax * ph

    parts = [f'<svg class="pace" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
             f'xmlns="http://www.w3.org/2000/svg" font-family="Instrument Sans">']
    for k in range(int(round(ymax / step)) + 1):
        v = k * step
        parts.append(f'<line x1="{left}" x2="{left + pw}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{RULE}"/>')
        parts.append(f'<text x="{left - 10}" y="{y(v) + 4:.1f}" text-anchor="end" font-size="12" '
                     f'fill="{MIST}">{escape(_short(v, r.currency))}</text>')
    for day in (1, 8, 15, 22, 29):
        if day <= days:
            parts.append(f'<text x="{x(day):.1f}" y="{height - 6}" text-anchor="middle" font-size="12" '
                         f'fill="{MIST}">{day}</text>')

    def path(values: list[float]) -> str:
        return " ".join(f"{'M' if i == 0 else 'L'}{x(i + 1):.1f},{y(v):.1f}" for i, v in enumerate(values))

    if usual:
        parts.append(f'<path d="{path(usual)}" fill="none" stroke="{MIST}" stroke-width="2" '
                     f'stroke-dasharray="5 5" stroke-linecap="round"/>')
    if actual:
        parts.append(f'<path d="{path(actual)}" fill="none" stroke="{INK}" stroke-width="2.5" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
        parts.append(f'<circle cx="{x(len(actual)):.1f}" cy="{y(actual[-1]):.1f}" r="4.5" fill="{INK}" '
                     f'stroke="#fff" stroke-width="2"/>')

    # End labels. A finished month puts both in the right margin, so separate them vertically.
    full_month = len(actual) == days
    actual_y = usual_y = None
    if actual:
        ay = y(actual[-1])
        actual_y = ay + 4 if full_month else (ay - 12 if ay - 12 > top + 10 else ay + 22)
    if usual:
        usual_y = y(usual[-1]) + 4
    gap = 17
    if full_month and actual_y is not None and usual_y is not None and abs(actual_y - usual_y) < gap:
        mid = (actual_y + usual_y) / 2
        upper, lower = mid - gap / 2, mid + gap / 2
        actual_y, usual_y = (upper, lower) if actual[-1] >= usual[-1] else (lower, upper)
    if actual_y is not None:
        lx, anchor = (x(days) + 12, "start") if full_month else (x(len(actual)), "middle")
        parts.append(f'<text x="{lx:.1f}" y="{actual_y:.1f}" text-anchor="{anchor}" font-size="13" '
                     f'font-weight="600" fill="{INK}">{escape(_short(actual[-1], r.currency))}</text>')
    if usual_y is not None:
        parts.append(f'<text x="{left + pw + 12}" y="{usual_y:.1f}" font-size="12.5" fill="{SLATE}">'
                     f'Usual {escape(_short(usual[-1], r.currency))}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _months_svg(r: ReportData) -> str:
    width, height = CHART_WIDTH, 200
    left, top, bottom = 4, 22, 28
    ph = height - top - bottom
    slot = (width - left * 2) / 12
    values = dict(r.monthly_totals or [])
    vmax = max(list(values.values()) + [1.0])
    parts = [f'<svg class="months" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
             f'xmlns="http://www.w3.org/2000/svg" font-family="Instrument Sans">',
             f'<line x1="{left}" x2="{width - left}" y1="{top + ph}" y2="{top + ph}" stroke="{RULE}"/>']
    for i, name in enumerate(calendar.month_abbr[1:]):
        cx = left + slot * (i + 0.5)
        value = values.get(name, 0.0)
        color = INK if value > 0 else MIST
        parts.append(f'<text x="{cx:.1f}" y="{height - 8}" text-anchor="middle" font-size="12" '
                     f'fill="{color}">{name}</text>')
        if value > 0:
            h = value / vmax * ph
            bw = slot * 0.56
            parts.append(f'<rect x="{cx - bw / 2:.1f}" y="{top + ph - h:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                         f'rx="4" fill="{INK}"/>')
            parts.append(f'<text x="{cx:.1f}" y="{top + ph - h - 7:.1f}" text-anchor="middle" font-size="11.5" '
                         f'fill="{SLATE}">{escape(_short(value, r.currency))}</text>')
    parts.append("</svg>")
    return "".join(parts)


# --- blocks ---

def _stat(value: str, label: str, over: bool = False) -> str:
    cls = "num over" if over else "num"
    return f'<div><div class="{cls}">{escape(value)}</div><div class="label">{escape(label)}</div></div>'


def _categories(r: ReportData, limit: int | None = None) -> str:
    lines = r.categories[:limit] if limit else r.categories
    peak = max([c.amount for c in lines] + [c.usual or 0 for c in lines] + [0.01])
    rows = []
    for c in lines:
        tick = ""
        if c.usual:
            tick = f'<div class="tick" style="left:{min(c.usual / peak, 1) * 100:.2f}%"></div>'
        if c.change is None:
            change = '<span class="chg"></span>'
        elif abs(c.change) < 1:
            change = '<span class="chg">as usual</span>'
        else:
            # Colour only what the report itself would flag, not every penny over.
            notable = notably_above(c.amount, c.usual)
            change = (f'<span class="chg num{" over" if notable else ""}">'
                      f"{escape(_signed(c.change, r.currency))}</span>")
        rows.append(
            f'<div class="cat"><span class="name">{escape(c.category)}</span>'
            f'<div class="track"><div class="bar" style="width:{c.amount / peak * 100:.2f}%"></div>{tick}</div>'
            f'<span class="amt num">{escape(_money(c.amount, r.currency))}</span>'
            f'<span class="share num">{c.share * 100:.0f}%</span>{change}</div>'
        )
    return "".join(rows)


def _head(r: ReportData) -> tuple[str, str]:
    if r.kind == "month":
        return f"{r.start:%B %Y}", f"to {r.today.day} {r.today:%B}"
    if r.kind == "lastmonth":
        return f"{r.start:%B %Y}", "full month"
    if r.kind == "week":
        return "This week", f"{r.start.day} {r.start:%b} to {r.end.day} {r.end:%b}"
    return f"{r.start.year}", f"to {r.today.day} {r.today:%B}"


_PERIOD_WORD = {"month": "month", "lastmonth": "month", "week": "week", "year": "year"}


def _body(r: ReportData) -> str:
    cur = r.currency
    if not r.categories:
        return (f'<div class="empty"><p>Nothing logged yet this {_PERIOD_WORD[r.kind]}.</p>'
                f"<p>Type an amount and what it was, like 15 lunch.</p></div>")

    hero_label = {"month": "spent so far", "lastmonth": "spent", "week": "spent so far this week",
                  "year": "spent so far this year"}[r.kind]
    out = [f'<div class="hero"><div class="num">{escape(_money(r.total, cur))}</div>'
           f'<div class="label">{hero_label}</div></div>']

    stats = []
    if r.kind == "year":
        if r.worst_month:
            stats.append(_stat(_money(r.worst_month[1], cur), f"most, in {r.worst_month[0]}"))
        if r.best_month:
            stats.append(_stat(_money(r.best_month[1], cur), f"least, in {r.best_month[0]}"))
        stats.append(_stat(_money(r.recurring_annual, cur), "recurring a year"))
    else:
        if r.projected is not None:
            stats.append(_stat(_money(r.projected, cur), "projected month-end"))
        if r.compare_total is not None and r.compare_total > 0:
            change = r.total - r.compare_total
            stats.append(_stat(_pct(change, r.compare_total), f"vs {r.compare_label}", over=change > 0))
    stats.append(_stat(f"{r.no_spend_days} of {r.tracked_days}", "days with no spending"))
    out.append(f'<div class="stats">{"".join(stats)}</div>')
    if not r.has_history and r.kind != "year":
        out.append('<p class="note">Comparisons start once you have a full month of data.</p>')

    if r.kind in ("month", "lastmonth"):
        legend = f'<i style="border-top:2.5px solid {INK}"></i>This month'
        if r.baseline_pace:
            legend += f'</span><span><i style="border-top:2px dashed {MIST}"></i>Usual month'
        out.append(f'<section><h2>Spending pace<span class="legend"><span>{legend}</span></span></h2>'
                   f"{_pace_svg(r)}</section>")
    if r.kind == "year":
        out.append(f"<section><h2>By month</h2>{_months_svg(r)}</section>")

    title = "Top categories" if r.kind == "year" else "Where it went"
    out.append(f"<section><h2>{title}</h2>{_categories(r, 5 if r.kind == 'year' else None)}")
    if any(c.usual for c in r.categories):
        usual_phrase = {"month": "by this day of the month", "lastmonth": "for a whole month",
                        "week": "by this day of the week"}[r.kind]
        out.append(f'<p class="foot">The tick marks your usual spend {usual_phrase}.</p>')
    if r.kind == "year" and r.largest:
        e = r.largest[0]
        out.append(f'<p class="foot">Largest single expense: {escape(_money(e.amount, cur))}, '
                   f"{escape(e.note or e.category)}, {e.date.day} {e.date:%b}.</p>")
    out.append("</section>")
    if r.kind != "year":
        out.append(_patterns(r))
    return "".join(out)


def _patterns(r: ReportData) -> str:
    cur = r.currency
    largest = "".join(
        f'<li><span class="num">{escape(_money(e.amount, cur))}</span>'
        f"<span>{escape(e.note or e.category)}</span><span class=\"when\">{e.date.day} {e.date:%b}</span></li>"
        for e in r.largest
    )
    return (
        '<section class="patterns"><div>'
        "<h2>Daily average</h2>"
        f'<div class="avg"><span class="num">{escape(_money(r.weekday_avg, cur))}</span> on weekdays</div>'
        f'<div class="avg"><span class="num">{escape(_money(r.weekend_avg, cur))}</span> at weekends</div>'
        f'</div><div><h2>Largest expenses</h2><ol class="largest">{largest}</ol></div>'
        '<p class="foot wide">Leaves out housing, bills and subscriptions.</p></section>'
    )


def build_card_html(r: ReportData) -> str:
    title, sub = _head(r)
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{_font_face()}{_CSS}</style></head>'
            f'<body><div class="page"><div class="card"><div class="head"><span class="title">{escape(title)}</span>'
            f'<span class="sub">{escape(sub)}</span></div>{_body(r)}</div></div></body></html>')
