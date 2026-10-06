from datetime import date
from decimal import Decimal

from conftest import TODAY, make_entries

from expense_bot import db
from expense_bot.money import round2
from expense_bot.reports import build_report


def kinds(r):
    return [t.kind for t in r.tips]


def test_month_headline(month_report):
    r = month_report
    assert (r.total, r.compare_total, r.projected, r.no_spend_days, r.days_elapsed) == (150.0, 300.0, 460.0, 4, 15)
    assert r.compare_label == "same point last month"


def test_month_categories(month_report):
    eo = next(c for c in month_report.categories if c.category == "Eating Out")
    assert (eo.amount, round2(eo.usual), round2(eo.change), round2(eo.share)) == (100.0, 48.39, 51.61, 0.67)
    assert [c.category for c in month_report.categories] == ["Eating Out", "Groceries"]


def test_month_tips(month_report):
    r = month_report
    assert [(t.kind, t.value) for t in r.tips] == [("repeated", 365.0), ("recurring", 144.0), ("above_usual", 106.67)]
    assert r.tips[0].text == "coffee ×10 (£30.00). Half as often saves about £365.00 a year."
    assert r.tips[1].text == "Recurring payments: £12.00/month, £144.00/year (netflix)."
    assert r.tips[2].text == "Eating Out is £51.61 above usual. Getting back to usual saves about £106.67 this month."


def test_month_patterns(month_report):
    r = month_report
    assert (r.weekday_avg, r.weekend_avg) == (12.82, 2.25)
    assert [e.amount for e in r.largest] == [70.0, 50.0, 3.0]
    assert (r.upcoming_total, [e.note for e in r.upcoming]) == (190.0, ["flights", "concert"])


def test_month_pace(month_report):
    r = month_report
    assert r.pace[0] == 3.0 and r.pace[1] == 56.0 and r.pace[-1] == 150.0 and len(r.pace) == 15
    assert r.baseline_pace[0] == 300.0 and len(r.baseline_pace) == 31


def test_planned_excluded_until_due(month_report):
    assert "Travel" not in [c.category for c in month_report.categories]


def test_no_history(no_history_report):
    r = no_history_report
    assert not r.has_history and r.compare_total is None and r.baseline_pace is None
    assert all(c.usual is None for c in r.categories)
    assert "above_usual" not in kinds(r)


def _shopping(sep_amount):
    specs = [(40.0, "Shopping", "clothes", date(2026, m, 5)) for m in (6, 7, 8)]
    specs.append((sep_amount, "Shopping", "clothes", date(2026, 9, 5)))
    return make_entries(specs)


def test_threshold_exactly_ten_is_not_a_tip():
    assert "above_usual" not in kinds(build_report("lastmonth", _shopping(50.0), [], TODAY, "GBP"))


def test_threshold_just_over_ten_is_a_tip():
    r = build_report("lastmonth", _shopping(50.01), [], TODAY, "GBP")
    assert "above_usual" in kinds(r)
    assert r.compare_total == 40.0 and r.compare_label == "the month before"


def test_empty_first_day(empty_report):
    r = empty_report
    assert (r.total, r.projected, r.no_spend_days, r.tips) == (0.0, 0.0, 1, [])


def test_no_spend_days_start_at_first_entry(year_report):
    # First entry is 1 Jul; 1 Jul..15 Oct is 107 days, spend on 3 baseline days + 11 October days.
    assert (year_report.tracked_days, year_report.no_spend_days) == (107, 93)


def test_new_user_mid_month_tracked_days():
    entries = make_entries([(5.0, "Other", "x", date(2026, 10, 10))])
    r = build_report("month", entries, [], TODAY, "GBP")
    assert (r.tracked_days, r.no_spend_days, r.days_elapsed) == (6, 5, 15)


def test_week():
    entries = make_entries([(35.0, "Other", "x", date(2026, 10, 7)), (20.0, "Other", "y", date(2026, 10, 12))])
    r = build_report("week", entries, [], date(2026, 10, 14), "GBP")
    assert (r.start, r.end, r.total, r.compare_total, r.compare_label) == (
        date(2026, 10, 12), date(2026, 10, 18), 20.0, 35.0, "last week")
    assert r.days_elapsed == 3


def test_year(year_report):
    r = year_report
    assert r.monthly_totals == [("Jan", 0.0), ("Feb", 0.0), ("Mar", 0.0), ("Apr", 0.0), ("May", 0.0), ("Jun", 0.0),
                                ("Jul", 300.0), ("Aug", 300.0), ("Sep", 300.0), ("Oct", 150.0)]
    assert r.best_month == ("Jul", 300.0) and r.worst_month == ("Jul", 300.0)
    assert r.total == 1050.0 and r.recurring_annual == 144.0 and r.compare_total is None


def test_money_precision():
    conn = db.connect(":memory:")
    db.ensure_user(conn, 1, TODAY)
    values = [0.10, 0.20, 19.99, 4.35]
    for i in range(10_000):
        db.add_entry(conn, 1, values[i % 4], "Other", "x", date(2026, 10, 1), TODAY)
    r = build_report("month", db.all_entries(conn, 1), [], TODAY, "GBP")
    exact = sum(Decimal(s) for s in ["0.10", "0.20", "19.99", "4.35"]) * 2500
    assert r.total == 61600.0 == float(exact)
