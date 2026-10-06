import asyncio
from datetime import date

from conftest import TODAY, make_entries

from expense_bot.card import build_card_html
from expense_bot.reports import build_report
from expense_bot.render import CardRenderer


def test_month_card_headline(month_report):
    html = build_card_html(month_report)
    for text in ["October 2026", "to 15 October", "£150.00", "spent so far", "£300.00", "projected month-end",
                 "−50%", "vs same point last month", "4 of 15", "days with no spending"]:
        assert text in html, text


def test_month_card_charts(month_report):
    html = build_card_html(month_report)
    assert 'class="pace"' in html and "Usual" in html
    assert "Eating Out" in html and "£100.00" in html and "Groceries" in html and "£50.00" in html


def test_month_card_patterns(month_report):
    html = build_card_html(month_report)
    for text in ["Daily average", "£12.82", "on weekdays", "£2.25", "at weekends", "Largest expenses", "£70.00",
                 "dinner", "12 Oct"]:
        assert text in html, text


def test_month_card_no_history_note(no_history_report):
    html = build_card_html(no_history_report)
    assert "Comparisons start once you have a full month of data." in html
    assert "vs same point last month" not in html


def test_week_card_has_no_pace(week_report):
    html = build_card_html(week_report)
    assert 'class="pace"' not in html and "This week" in html


def test_year_card(year_report):
    html = build_card_html(year_report)
    for text in ["2026", "£1,050.00", "Jul", "Oct", 'class="months"', "£144.00"]:
        assert text in html, text


def test_empty_card(empty_report):
    html = build_card_html(empty_report)
    assert "Nothing logged yet this month." in html and "15 lunch" in html


def test_notes_are_escaped():
    entries = make_entries([(500.0, "Shopping", "<script>x</script>", date(2026, 3, 1))])
    html = build_card_html(build_report("year", entries, [], TODAY, "GBP"))
    assert "<script>x" not in html and "&lt;script&gt;" in html


def test_renders_png(month_report):
    async def run():
        renderer = CardRenderer()
        try:
            return await renderer.render(build_card_html(month_report))
        finally:
            await renderer.close()

    png = asyncio.run(run())
    assert png.startswith(b"\x89PNG") and len(png) > 20_000


def test_patterns_say_what_they_leave_out(month_report):
    assert "Leaves out housing, bills and subscriptions." in build_card_html(month_report)
