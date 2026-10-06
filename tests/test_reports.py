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
    assert (r.total, r.compare_total, r.projected, r.no_spend_days, r.days_elapsed) == (150.0, 300.0, 300.0, 4, 15)
    assert r.compare_label == "same point last month"


def test_month_categories(month_report):
    eo = next(c for c in month_report.categories if c.category == "Eating Out")
    assert (eo.amount, round2(eo.usual), round2(eo.change), round2(eo.share)) == (100.0, 100.0, 0.0, 0.67)
    assert [c.category for c in month_report.categories] == ["Eating Out", "Groceries"]


def test_month_tips(month_report):
    r = month_report
    assert [(t.kind, t.value) for t in r.tips] == [("repeated", 365.0), ("recurring", 144.0)]
    assert r.tips[0].text == "coffee ×10 (£30.00). Half as often saves about £365.00 a year."
    assert r.tips[1].text == "Recurring payments: £12.00/month, £144.00/year (netflix)."


def _rent_history():
    specs = []
    for m in (7, 8, 9):
        specs.append((950.0, "Housing", "rent", date(2026, m, 1)))
        specs.append((50.0, "Groceries", "tesco", date(2026, m, 15)))
    specs.append((950.0, "Housing", "rent", date(2026, 10, 1)))
    return specs


def test_rent_on_the_first_is_not_above_usual():
    r = build_report("month", make_entries(_rent_history()), [], date(2026, 10, 6), "GBP")
    housing = next(c for c in r.categories if c.category == "Housing")
    assert (housing.usual, housing.change) == (950.0, 0.0)
    assert "above_usual" not in kinds(r)
    assert r.projected == 1000.0  # 950 spent + 50 usually still to come


def test_one_off_spend_tip_is_the_excess_not_extrapolated():
    specs = _rent_history() + [(300.0, "Travel", "flight", date(2026, 10, 2))]
    r = build_report("month", make_entries(specs), [], date(2026, 10, 6), "GBP")
    tip = next(t for t in r.tips if t.kind == "above_usual")
    assert tip.value == 300.0
    assert tip.text == "Travel is £300.00 above usual. Getting back to usual saves about £300.00 this month."


def test_partial_first_month_is_not_a_baseline():
    specs = [(8.0, "Eating Out", "lunch", date(2026, 9, 30))]
    specs += [(12.0, "Eating Out", "lunch", date(2026, 10, d)) for d in range(1, 16)]
    r = build_report("month", make_entries(specs), [], TODAY, "GBP")
    assert not r.has_history and r.compare_total is None and "above_usual" not in kinds(r)


def test_lastmonth_tip_wording():
    specs = [(40.0, "Shopping", "clothes", date(2026, m, 5)) for m in (6, 7, 8)]
    specs.append((80.0, "Shopping", "clothes", date(2026, 9, 5)))
    r = build_report("lastmonth", make_entries(specs), [], TODAY, "GBP")
    assert r.tips[0].text == "Shopping is £40.00 above usual. Getting back to usual saves about £40.00 a month."


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
    entries = make_entries([(35.0, "Other", "x", date(2026, 10, 5)), (20.0, "Other", "y", date(2026, 10, 12))])
    r = build_report("week", entries, [], date(2026, 10, 14), "GBP")
    assert (r.start, r.end, r.total, r.compare_total, r.compare_label) == (
        date(2026, 10, 12), date(2026, 10, 18), 20.0, 35.0, "same point last week")
    assert r.days_elapsed == 3


def test_week_compares_same_days_of_last_week():
    entries = make_entries([(10.0, "Other", "x", date(2026, 10, 5)), (50.0, "Other", "y", date(2026, 10, 9)),
                            (20.0, "Other", "z", date(2026, 10, 12))])
    r = build_report("week", entries, [], date(2026, 10, 14), "GBP")
    assert r.compare_total == 10.0  # Mon-Wed last week only; Friday's 50 isn't comparable yet


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


def test_fixed_costs_left_out_of_patterns():
    # Thu 1 Oct rent, Fri 2 Oct lunch, Sat 3 Oct drinks, Mon 5 Oct phone bill and Spotify
    entries = make_entries([(850.0, "Housing", "Rent", date(2026, 10, 1)),
                            (20.0, "Eating Out", "Lunch", date(2026, 10, 2)),
                            (10.0, "Entertainment", "Drinks", date(2026, 10, 3)),
                            (15.0, "Bills", "Phone", date(2026, 10, 5)),
                            (11.99, "Subscriptions", "Spotify", date(2026, 10, 5))])
    r = build_report("month", entries, [], date(2026, 10, 6), "GBP")
    assert (r.weekday_avg, r.weekend_avg) == (5.0, 5.0)  # 20 over 4 weekdays, 10 over 2 weekend days
    assert [e.note for e in r.largest] == ["Lunch", "Drinks"]
    assert r.total == 906.99 and r.no_spend_days == 2  # fixed costs still count everywhere else
