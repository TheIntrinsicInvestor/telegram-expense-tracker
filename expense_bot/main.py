"""Entry point: python -m expense_bot.main (needs EXPENSE_BOT_ENV)."""

import logging
from datetime import time
from zoneinfo import ZoneInfo

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden
from telegram.ext import Application, ContextTypes

from expense_bot import db, jobs
from expense_bot.clock import local_today, utc_now
from expense_bot.config import load_config
from expense_bot.handlers import BOT_COMMANDS, register

log = logging.getLogger(__name__)

HOURLY_SECONDS = 3600
BACKUP_TIME = time(3, 0, tzinfo=ZoneInfo("Europe/London"))


async def hourly(context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    for out in jobs.collect_hourly(conn, utc_now()):
        try:
            if out.photo:
                await context.bot.send_photo(chat_id=out.user_id, photo=out.photo)
            markup = None
            if out.undo_entry_id:
                markup = InlineKeyboardMarkup([[InlineKeyboardButton("Undo", callback_data=f"undo:{out.undo_entry_id}")]])
            await context.bot.send_message(chat_id=out.user_id, text=out.text, reply_markup=markup)
        except Forbidden:
            # The user blocked the bot: retrying every hour would never succeed.
            log.info("user %s has blocked the bot; marking %s as sent", out.user_id, out.kind)
        except Exception:
            log.warning("send failed for user %s (%s); will retry next hour", out.user_id, out.kind, exc_info=True)
            continue
        jobs.mark_sent(conn, out)


async def nightly_backup(context: ContextTypes.DEFAULT_TYPE) -> None:
    config = context.bot_data["config"]
    path = jobs.backup(config.db_path, config.backup_dir, local_today("Europe/London", utc_now()))
    log.info("backup written: %s", path.name)


async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([BotCommand(name, description) for name, description in BOT_COMMANDS])


def main() -> None:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    # httpx logs request URLs at INFO, and those URLs contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config = load_config()
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(config.db_path)
    app = Application.builder().token(config.token).post_init(post_init).build()
    app.bot_data["config"] = config
    register(app, conn)
    app.job_queue.run_repeating(hourly, interval=HOURLY_SECONDS, first=10)
    app.job_queue.run_daily(nightly_backup, time=BACKUP_TIME)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
