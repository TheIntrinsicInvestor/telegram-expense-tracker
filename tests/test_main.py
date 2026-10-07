import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from expense_bot import jobs, main


def test_monthly_card_not_resent_when_only_its_text_failed(monkeypatch):
    out = jobs.Outgoing(1, "tips", "monthly", "2026-09", report=object(), html=True)
    monkeypatch.setattr(main.jobs, "collect_hourly", lambda conn, now: [out])
    monkeypatch.setattr(main.jobs, "mark_sent", lambda conn, o: None)
    monkeypatch.setattr(main, "build_card_html", lambda report: "<html>")
    bot = SimpleNamespace(send_photo=AsyncMock(), send_message=AsyncMock(side_effect=[RuntimeError("down"), None]))
    renderer = SimpleNamespace(render=AsyncMock(return_value=b"png"))
    context = SimpleNamespace(bot=bot, bot_data={"conn": None, "renderer": renderer})
    asyncio.run(main.hourly(context))
    asyncio.run(main.hourly(context))
    assert bot.send_photo.await_count == 1
    assert bot.send_message.await_count == 2
