"""Entry point: python -m expense_bot.main (needs EXPENSE_BOT_ENV)."""

import logging

from telegram import Update
from telegram.ext import Application

from expense_bot import db
from expense_bot.config import load_config
from expense_bot.handlers import register


def main() -> None:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    # httpx logs request URLs at INFO, and those URLs contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config = load_config()
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(config.db_path)
    app = Application.builder().token(config.token).build()
    register(app, conn)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
