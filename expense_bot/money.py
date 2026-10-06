"""Money rounding and display. Amounts are floats rounded to 2 dp at every boundary."""

from decimal import ROUND_HALF_UP, Decimal

_SYMBOLS = {"GBP": "£", "EUR": "€", "USD": "$", "SGD": "S$"}


def round2(x: float) -> float:
    # repr() gives the shortest string that round-trips, so 2.675 rounds as written, not as stored.
    return float(Decimal(repr(float(x))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fmt_money(amount: float, currency: str) -> str:
    value = round2(amount)
    sign = "-" if value < 0 else ""
    number = f"{abs(value):,.2f}"
    symbol = _SYMBOLS.get(currency)
    return f"{sign}{symbol}{number}" if symbol else f"{sign}{currency} {number}"


def fmt_signed(amount: float, currency: str) -> str:
    value = round2(amount)
    return ("+" if value > 0 else "") + fmt_money(value, currency)
