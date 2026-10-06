from expense_bot.money import fmt_money, fmt_signed, round2


def test_round2_half_up():
    assert round2(2.675) == 2.68  # Python round() gives 2.67
    assert round2(0.1 + 0.2) == 0.3
    assert round2(15.5) == 15.5


def test_fmt_money():
    assert fmt_money(1200, "GBP") == "£1,200.00"
    assert fmt_money(4.2, "EUR") == "€4.20"
    assert fmt_money(3, "SGD") == "S$3.00"
    assert fmt_money(15, "CHF") == "CHF 15.00"
    assert fmt_money(-150, "GBP") == "-£150.00"


def test_fmt_signed():
    assert fmt_signed(51.613, "GBP") == "+£51.61"
    assert fmt_signed(-150, "GBP") == "-£150.00"
    assert fmt_signed(0, "GBP") == "£0.00"
