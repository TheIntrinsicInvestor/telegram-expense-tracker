import pytest

from expense_bot.charts import render_report_chart


@pytest.mark.parametrize("report", ["month_report", "week_report", "year_report", "empty_report", "no_history_report"])
def test_renders_png(report, request):
    png = render_report_chart(request.getfixturevalue(report))
    assert png.startswith(b"\x89PNG") and len(png) > 1000
