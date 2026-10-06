from datetime import date

import pytest

from expense_bot.parser import (
    AMOUNT_RANGE_ERROR,
    BAD_DATE_ERROR,
    HELP_EXAMPLE,
    ParsedEntry,
    ParseError,
    parse_entry,
)

TODAY = date(2026, 10, 6)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("15 lunch", ParsedEntry(15.0, "lunch", TODAY)),
        ("lunch 15", ParsedEntry(15.0, "lunch", TODAY)),
        ("  15   lunch  ", ParsedEntry(15.0, "lunch", TODAY)),
        ("4.20 coffee pret", ParsedEntry(4.2, "coffee pret", TODAY)),
        ("15.5 LUNCH", ParsedEntry(15.5, "LUNCH", TODAY)),
        ("£1,200 rent", ParsedEntry(1200.0, "rent", TODAY)),
        ("€3.5 snack", ParsedEntry(3.5, "snack", TODAY)),
        ("15", ParsedEntry(15.0, "", TODAY)),
        ("1000000 car", ParsedEntry(1000000.0, "car", TODAY)),
        ("12 taxi 03/10", ParsedEntry(12.0, "taxi", date(2026, 10, 3))),
        ("10 x 06/10", ParsedEntry(10.0, "x", TODAY)),
        ("10 x 29/09", ParsedEntry(10.0, "x", date(2026, 9, 29))),
        ("10 x 28/09", ParsedEntry(10.0, "x", date(2027, 9, 28))),
        ("150 flights 31/12/26", ParsedEntry(150.0, "flights", date(2026, 12, 31))),
        ("150 flights 31/12/2026", ParsedEntry(150.0, "flights", date(2026, 12, 31))),
        ("5 x 1/2/27", ParsedEntry(5.0, "x", date(2027, 2, 1))),
        ("20 groceries yesterday", ParsedEntry(20.0, "groceries", date(2026, 10, 5))),
        ("20 groceries Today", ParsedEntry(20.0, "groceries", TODAY)),
        ("10 x 29/02/28", ParsedEntry(10.0, "x", date(2028, 2, 29))),
        ("10 x 29/02", ParsedEntry(10.0, "x", date(2028, 2, 29))),
        ("10 x 31/02", ParseError(BAD_DATE_ERROR)),
        ("10 x 29/02/27", ParseError(BAD_DATE_ERROR)),
        ("0 lunch", ParseError(AMOUNT_RANGE_ERROR)),
        ("1000000.01 x", ParseError(AMOUNT_RANGE_ERROR)),
        ("15,50 lunch", ParseError(HELP_EXAMPLE)),
        ("15.999 lunch", ParseError(HELP_EXAMPLE)),
        ("-5 lunch", ParseError(HELP_EXAMPLE)),
        ("lunch", ParseError(HELP_EXAMPLE)),
        ("hello there", ParseError(HELP_EXAMPLE)),
        ("", ParseError(HELP_EXAMPLE)),
    ],
)
def test_parse_entry(text, expected):
    assert parse_entry(text, TODAY) == expected


def test_year_rollover_forward():
    assert parse_entry("10 x 02/01", date(2026, 12, 30)) == ParsedEntry(10.0, "x", date(2027, 1, 2))


def test_year_rollover_backfill():
    assert parse_entry("10 x 30/12", date(2027, 1, 3)) == ParsedEntry(10.0, "x", date(2026, 12, 30))
