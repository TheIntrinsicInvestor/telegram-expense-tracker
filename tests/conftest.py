from datetime import date

import pytest

from expense_bot.models import Entry, Recurring
from expense_bot.reports import build_report

TODAY = date(2026, 10, 15)


def make_entries(specs: list[tuple[float, str, str, date]]) -> list[Entry]:
    """specs: (amount, category, note, date), ids assigned in list order."""
    return [Entry(i, 1, amount, cat, note, d, None, True, "2026-01-01T00:00:00+00:00")
            for i, (amount, cat, note, d) in enumerate(specs, start=1)]


def _baseline_specs() -> list:
    specs = []
    for month in (7, 8, 9):
        specs.append((100.0, "Eating Out", "dinner", date(2026, month, 1)))
        specs.append((200.0, "Groceries", "tesco", date(2026, month, 1)))
    return specs


def _october_specs() -> list:
    specs = [(3.0, "Eating Out", "coffee", date(2026, 10, day)) for day in range(1, 11)]
    specs.append((50.0, "Groceries", "tesco", date(2026, 10, 2)))
    specs.append((70.0, "Eating Out", "dinner", date(2026, 10, 12)))
    specs.append((150.0, "Travel", "flights", date(2026, 10, 31)))
    specs.append((40.0, "Entertainment", "concert", date(2026, 11, 1)))
    return specs


@pytest.fixture
def fixture_entries() -> list[Entry]:
    return make_entries(_baseline_specs() + _october_specs())


@pytest.fixture
def october_only() -> list[Entry]:
    return make_entries(_october_specs())


@pytest.fixture
def netflix() -> list[Recurring]:
    return [Recurring(1, 1, 12.0, "Subscriptions", "netflix", "monthly", 6, date(2026, 11, 6), True)]


@pytest.fixture
def month_report(fixture_entries, netflix):
    return build_report("month", fixture_entries, netflix, TODAY, "GBP")


@pytest.fixture
def week_report(fixture_entries, netflix):
    return build_report("week", fixture_entries, netflix, TODAY, "GBP")


@pytest.fixture
def year_report(fixture_entries, netflix):
    return build_report("year", fixture_entries, netflix, TODAY, "GBP")


@pytest.fixture
def no_history_report(october_only):
    return build_report("month", october_only, [], TODAY, "GBP")


@pytest.fixture
def empty_report():
    return build_report("month", [], [], date(2026, 10, 1), "GBP")
