from datetime import date

from expense_bot.formatting import (
    DELETE_WARNING,
    EXPORT_WARNING,
    HELP_TEXT,
    NO_HISTORY,
    PRIVACY_TEXT,
    date_label,
    export_csv,
    format_logged,
    format_report,
    format_weekly_summary,
)
from expense_bot.models import Entry

TODAY = date(2026, 10, 6)


def entry(amount, category, note, d, recurring_id=None):
    return Entry(1, 1, amount, category, note, d, recurring_id, True, "2026-10-06T10:00:00+00:00")


def test_date_label():
    assert date_label(TODAY, TODAY) == "today"
    assert date_label(date(2026, 10, 5), TODAY) == "yesterday"
    assert date_label(date(2026, 10, 3), TODAY) == "3 Oct 2026"


def test_logged():
    assert format_logged(entry(15, "Eating Out", "lunch", TODAY), "GBP", TODAY) == \
        "Logged £15.00 · Eating Out · lunch · today"


def test_planned():
    assert format_logged(entry(150, "Travel", "flights", date(2026, 12, 31)), "GBP", TODAY) == \
        "Planned £150.00 · Travel · flights · 31 Dec 2026"


def test_empty_note():
    assert format_logged(entry(5, "Other", "", TODAY), "GBP", TODAY) == "Logged £5.00 · Other · today"


def test_report_month_lines(month_report):
    t = format_report(month_report)
    for line in [
        "Spent: £150.00",
        "vs same point last month: -£150.00 (-50%)",
        "Projected month-end: £300.00",
        "No-spend days: 4 of 15",
        "Eating Out £100.00 (67%) £0.00 vs usual",
        "coffee ×10 (£30.00). Half as often saves about £365.00 a year.",
        "Weekdays £12.82/day · Weekends £2.25/day",
        "Coming up (30 days): £190.00",
    ]:
        assert line in t, line


def test_report_no_history_note(no_history_report):
    assert NO_HISTORY in format_report(no_history_report)


def test_report_year(year_report):
    t = format_report(year_report)
    assert "Spent: £1,050.00" in t and "Recurring payments: £144.00/year" in t


def test_report_empty(empty_report):
    assert "Nothing logged yet this period." in format_report(empty_report)


def test_weekly_summary(week_report):
    t = format_weekly_summary(week_report)
    assert t.startswith("This week so far: £")


def test_no_em_dashes(month_report, year_report):
    texts = [HELP_TEXT, PRIVACY_TEXT, EXPORT_WARNING, DELETE_WARNING, format_report(month_report),
             format_report(year_report)]
    assert all("—" not in s for s in texts)


def test_export_csv():
    data = export_csv([entry(15.5, "Eating Out", "lunch", TODAY)], "GBP", TODAY)
    assert data.startswith(b"\xef\xbb\xbf")
    assert data.decode("utf-8-sig").splitlines() == [
        "date,amount,currency,category,note,planned,recurring",
        "2026-10-06,15.50,GBP,Eating Out,lunch,no,no",
    ]


def test_export_csv_planned_and_recurring():
    data = export_csv([entry(12, "Subscriptions", "netflix, monthly", date(2026, 11, 1), recurring_id=3)],
                      "GBP", TODAY)
    assert data.decode("utf-8-sig").splitlines()[1] == '2026-11-01,12.00,GBP,Subscriptions,"netflix, monthly",yes,yes'
