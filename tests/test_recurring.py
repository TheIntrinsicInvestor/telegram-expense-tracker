from datetime import date

from expense_bot.recurring import annual_cost, next_occurrence


def test_weekly():
    assert next_occurrence(date(2026, 12, 28), "weekly", 28) == date(2027, 1, 4)


def test_monthly_clamps_and_recovers():
    d1 = next_occurrence(date(2027, 1, 31), "monthly", 31)
    assert d1 == date(2027, 2, 28)
    d2 = next_occurrence(d1, "monthly", 31)
    assert d2 == date(2027, 3, 31)


def test_monthly_december_rolls_year():
    assert next_occurrence(date(2026, 12, 15), "monthly", 15) == date(2027, 1, 15)


def test_monthly_leap():
    assert next_occurrence(date(2028, 1, 30), "monthly", 30) == date(2028, 2, 29)


def test_yearly_leap_day():
    d1 = next_occurrence(date(2028, 2, 29), "yearly", 29)
    assert d1 == date(2029, 2, 28)


def test_annual_cost():
    assert annual_cost(12, "monthly") == 144.0
    assert annual_cost(5, "weekly") == 260.0
    assert annual_cost(99.99, "yearly") == 99.99
