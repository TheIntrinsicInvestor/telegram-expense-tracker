"""Renders a report as one PNG for Telegram. Colours follow the dataviz reference palette (light surface)."""

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from expense_bot.money import fmt_money  # noqa: E402
from expense_bot.reports import ReportData  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e4e3df"
SERIES = "#2a78d6"  # categorical slot 1


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="x" if ax.get_label() == "bars" else "y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _pace(ax, data: ReportData) -> None:
    ax.set_label("pace")
    _style(ax)
    days = range(1, len(data.pace) + 1)
    ax.plot(days, data.pace, color=SERIES, linewidth=2, label="This month")
    if data.baseline_pace:
        ax.plot(range(1, len(data.baseline_pace) + 1), data.baseline_pace, color=MUTED, linewidth=1.5,
                linestyle=(0, (3, 3)), label="Usual month")
        ax.legend(frameon=False, fontsize=9, labelcolor=INK_SECONDARY, loc="lower right")
    ax.set_xlim(1, len(data.baseline_pace or data.pace) or 1)
    ax.set_ylim(bottom=0)
    ax.set_title("Spending pace (cumulative)", loc="left", color=INK, fontsize=11)
    ax.set_xlabel("Day of month", color=MUTED, fontsize=9)


def _categories(ax, data: ReportData) -> None:
    ax.set_label("bars")
    _style(ax)
    lines = list(reversed(data.categories))  # largest at the top
    ys = range(len(lines))
    ax.barh(ys, [c.amount for c in lines], color=SERIES, height=0.6)
    has_usual = False
    for y, c in zip(ys, lines):
        ax.annotate(fmt_money(c.amount, data.currency), (c.amount, y), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=9, color=INK_SECONDARY)
        if c.usual is not None and c.usual > 0:
            ax.plot([c.usual, c.usual], [y - 0.4, y + 0.4], color=INK, linewidth=2)
            has_usual = True
    ax.set_yticks(list(ys), [c.category for c in lines], color=INK_SECONDARY)
    peak = max([c.amount for c in lines] + [c.usual or 0 for c in lines])
    ax.set_xlim(0, peak * 1.25)
    title = "By category" + ("  (black tick = usual)" if has_usual else "")
    ax.set_title(title, loc="left", color=INK, fontsize=11)


def _year(ax, data: ReportData) -> None:
    ax.set_label("year")
    _style(ax)
    names = [name for name, _ in data.monthly_totals]
    values = [value for _, value in data.monthly_totals]
    ax.bar(names, values, color=SERIES, width=0.6)
    ax.set_title(f"Monthly spending {data.start.year}", loc="left", color=INK, fontsize=11)


def _empty(ax) -> None:
    ax.set_facecolor(SURFACE)
    ax.axis("off")
    ax.text(0.5, 0.5, "No spending yet", ha="center", va="center", fontsize=14, color=MUTED)


def render_report_chart(data: ReportData) -> bytes:
    if data.kind == "year" and any(v for _, v in data.monthly_totals):
        fig, axes = plt.subplots(1, 1, figsize=(8, 4.5))
        _year(axes, data)
    elif not data.categories:
        fig, axes = plt.subplots(1, 1, figsize=(8, 3))
        _empty(axes)
    elif data.kind in ("month", "lastmonth"):
        height = 1.2 + 0.45 * len(data.categories)
        fig, (top, bottom) = plt.subplots(2, 1, figsize=(8, 3.6 + height),
                                          gridspec_kw={"height_ratios": [3.6, height]})
        _pace(top, data)
        _categories(bottom, data)
    else:
        fig, axes = plt.subplots(1, 1, figsize=(8, 1.5 + 0.45 * len(data.categories)))
        _categories(axes, data)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, facecolor=SURFACE)
    plt.close(fig)
    return buf.getvalue()
