"""Telegram glue: turns updates into calls on the logic modules. No business rules live here."""

import logging
import re
import sqlite3
import time
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

from expense_bot import db
from expense_bot.categories import CATEGORIES, first_word, resolve
from expense_bot.card import build_card_html
from expense_bot.clock import local_today, utc_now
from expense_bot.formatting import (
    COMMAND_ERROR,
    DELETE_WARNING,
    EDIT_NOT_TRACKED,
    EXPORT_WARNING,
    GENERIC_ERROR,
    HELP_TEXT,
    NO_RECURRING,
    PRIVACY_TEXT,
    RATE_LIMITED,
    SAVED_UNCONFIRMED,
    STALE,
    date_label,
    export_csv,
    format_entry_line,
    format_logged,
    format_recurring_line,
    format_report,
)
from expense_bot.models import User
from expense_bot.money import fmt_money
from expense_bot.parser import ParseError, parse_entry, parse_recurring
from expense_bot.ratelimit import RateLimiter
from expense_bot.render import CardRenderer
from expense_bot.reports import build_report

log = logging.getLogger(__name__)

CURRENCY_BUTTONS = ("GBP", "EUR", "USD", "SGD")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


# --- shared helpers ---

def _conn(context: ContextTypes.DEFAULT_TYPE) -> sqlite3.Connection:
    return context.bot_data["conn"]


def _user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[sqlite3.Connection, User, date]:
    conn = _conn(context)
    user_id = update.effective_user.id
    existing = db.get_user(conn, user_id)
    today = local_today(existing.timezone if existing else "Europe/London", utc_now())
    user = existing or db.ensure_user(conn, user_id, today)
    return conn, user, today


def logged_keyboard(entry_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Undo", callback_data=f"undo:{entry_id}"),
                                  InlineKeyboardButton("Change category", callback_data=f"chcat:{entry_id}")]])


def category_keyboard(entry_id: int) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(name, callback_data=f"cat:{entry_id}:{i}") for i, name in enumerate(CATEGORIES)]
    return InlineKeyboardMarkup([buttons[i:i + 3] for i in range(0, len(buttons), 3)])


def entry_keyboard(entry_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Edit", callback_data=f"edit:{entry_id}"),
                                  InlineKeyboardButton("Delete", callback_data=f"del:{entry_id}")]])


def _arg_id(data: str, position: int = 1) -> int:
    return int(data.split(":")[position])


# --- gate: rate limit every update ---

async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        raise ApplicationHandlerStop
    limiter: RateLimiter = context.bot_data["limiter"]
    verdict = limiter.check(update.effective_user.id, time.monotonic())
    if verdict == "ok":
        return
    if verdict == "warn" and update.effective_message:
        await update.effective_message.reply_text(RATE_LIMITED)
    raise ApplicationHandlerStop


# --- logging entries ---

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn, user, today = _user(update, context)
    parsed = parse_entry(update.message.text, today)
    if isinstance(parsed, ParseError):
        await update.message.reply_text(parsed.message)
        return

    category = resolve(parsed.note, db.learned_words(conn, user.user_id))
    editing = context.user_data.get("editing")
    if editing is not None:
        old = db.get_entry(conn, user.user_id, editing)
        context.user_data.pop("editing", None)
        if old is None:
            await update.message.reply_text(STALE)
            return
        db.update_entry(conn, user.user_id, editing, parsed.amount, category or old.category, parsed.note,
                        parsed.date, today)
        context.user_data["saved_update"] = update.update_id
        entry = db.get_entry(conn, user.user_id, editing)
        text = format_logged(entry, user.currency, today)
        await update.message.reply_text("Updated " + text.split(" ", 1)[1], reply_markup=logged_keyboard(entry.id))
        return

    entry_id = db.add_entry(conn, user.user_id, parsed.amount, category or "Other", parsed.note, parsed.date, today)
    context.user_data["saved_update"] = update.update_id
    entry = db.get_entry(conn, user.user_id, entry_id)
    text = format_logged(entry, user.currency, today)
    if category is None:
        await update.message.reply_text(text + "\nPick a category:", reply_markup=category_keyboard(entry_id))
    else:
        await update.message.reply_text(text, reply_markup=logged_keyboard(entry_id))


async def on_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    conn, user, today = _user(update, context)
    _, entry_id, index = query.data.split(":")
    entry_id, category = int(entry_id), CATEGORIES[int(index)]
    if not db.set_entry_category(conn, user.user_id, entry_id, category):
        await query.edit_message_text(STALE)
        return
    entry = db.get_entry(conn, user.user_id, entry_id)
    word = first_word(entry.note)
    if word:
        db.learn_word(conn, user.user_id, word, category)
    await query.edit_message_text(format_logged(entry, user.currency, today), reply_markup=logged_keyboard(entry_id))


async def on_change_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    conn, user, today = _user(update, context)
    entry = db.get_entry(conn, user.user_id, _arg_id(query.data))
    if entry is None:
        await query.edit_message_text(STALE)
        return
    await query.edit_message_text(format_logged(entry, user.currency, today) + "\nPick a category:",
                                  reply_markup=category_keyboard(entry.id))


# --- undo, delete, recent, edit ---

async def on_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles both the [Undo] button on a logged entry and [Delete] buttons."""
    query = update.callback_query
    await query.answer()
    conn, user, today = _user(update, context)
    entry = db.get_entry(conn, user.user_id, _arg_id(query.data))
    if entry is None or not db.delete_entry(conn, user.user_id, entry.id):
        await query.edit_message_text(STALE)
        return
    await query.edit_message_text("Deleted " + format_entry_line(entry, user.currency, today))


async def on_keep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Kept.")


async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn, user, today = _user(update, context)
    entry = db.latest_entry(conn, user.user_id)
    if entry is None:
        await update.message.reply_text("No entries yet.")
        return
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Delete", callback_data=f"del:{entry.id}"),
                                      InlineKeyboardButton("Keep", callback_data="keep")]])
    await update.message.reply_text("Delete your latest entry?\n" + format_entry_line(entry, user.currency, today),
                                    reply_markup=keyboard)


RECENT_DEFAULT = 5
RECENT_MAX = 20


def recent_limit(args: list[str]) -> int | None:
    """'/recent' → 5, '/recent 12' → 12; None for anything outside 1..20."""
    if not args:
        return RECENT_DEFAULT
    if args[0].isdigit() and 1 <= int(args[0]) <= RECENT_MAX:
        return int(args[0])
    return None


async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn, user, today = _user(update, context)
    limit = recent_limit(context.args)
    if limit is None:
        await update.message.reply_text(f"Use /recent, or /recent 10 for more (up to {RECENT_MAX}).")
        return
    entries = db.recent_entries(conn, user.user_id, limit)
    if not entries:
        await update.message.reply_text("No entries yet.")
        return
    for entry in entries:
        await update.message.reply_text(format_entry_line(entry, user.currency, today),
                                        reply_markup=entry_keyboard(entry.id))


async def on_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    conn, user, _ = _user(update, context)
    entry = db.get_entry(conn, user.user_id, _arg_id(query.data))
    if entry is None:
        await query.edit_message_text(STALE)
        return
    context.user_data["editing"] = entry.id
    await query.message.reply_text("Send the corrected entry, e.g. 16 lunch 05/10. /cancel to stop.")


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _user(update, context)
    stopped = context.user_data.pop("editing", None) is not None
    await update.message.reply_text("Edit cancelled." if stopped else "Nothing to cancel.")


# --- settings ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _, user, _ = _user(update, context)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(code, callback_data=f"cur:{code}")
                                      for code in CURRENCY_BUTTONS]])
    await update.message.reply_text(
        "Track spending by typing it, e.g. 15 lunch. /help shows everything.\n\n"
        f"{PRIVACY_TEXT}\n\n"
        f"Your currency is {user.currency}. Pick one below to change it.\n"
        "Other currency? Send /currency CODE, e.g. /currency CHF.",
        reply_markup=keyboard,
    )


async def _set_currency(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str) -> str:
    conn, user, _ = _user(update, context)
    db.set_currency(conn, user.user_id, code)
    return f"Currency set to {code}."


async def on_currency_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    code = query.data.split(":")[1]
    await query.message.reply_text(await _set_currency(update, context, code))


async def cmd_currency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    code = (context.args[0] if context.args else "").upper()
    if not _CURRENCY_RE.match(code):
        await update.message.reply_text("Use a 3-letter code like GBP or CHF.")
        return
    await update.message.reply_text(await _set_currency(update, context, code))


# --- reports and planning ---

REPORT_KINDS = {"": "month", "week": "week", "lastmonth": "lastmonth", "year": "year"}


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn, user, today = _user(update, context)
    kind = REPORT_KINDS.get((context.args[0] if context.args else "").lower())
    if kind is None:
        await update.message.reply_text("Use /report, /report week, /report lastmonth or /report year.")
        return
    report = build_report(kind, db.all_entries(conn, user.user_id), db.active_recurring(conn, user.user_id),
                          today, user.currency)
    renderer: CardRenderer = context.bot_data["renderer"]
    await update.message.reply_photo(photo=await renderer.render(build_card_html(report)))
    text = format_report(report)
    if text:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn, user, today = _user(update, context)
    entries = db.upcoming_entries(conn, user.user_id, today)
    if not entries:
        await update.message.reply_text("Nothing planned.")
        return
    total = sum(e.amount for e in entries)
    await update.message.reply_text(f"Planned payments: {fmt_money(total, user.currency)} in total")
    for entry in entries:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Delete", callback_data=f"del:{entry.id}")]])
        await update.message.reply_text(format_entry_line(entry, user.currency, today), reply_markup=keyboard)


async def cmd_recurring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn, user, today = _user(update, context)
    if not context.args:
        recs = db.active_recurring(conn, user.user_id)
        await update.message.reply_text("Recurring payments:" if recs else NO_RECURRING)
        for rec in recs:
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Stop", callback_data=f"stoprec:{rec.id}")]])
            await update.message.reply_text(format_recurring_line(rec, user.currency), reply_markup=keyboard)
        return
    parsed = parse_recurring(context.args, today)
    if isinstance(parsed, ParseError):
        await update.message.reply_text(parsed.message)
        return
    category = resolve(parsed.note, db.learned_words(conn, user.user_id)) or "Other"
    db.add_recurring(conn, user.user_id, parsed.amount, category, parsed.note, parsed.frequency, parsed.start)
    parts = [fmt_money(parsed.amount, user.currency), category, parsed.note,
             f"{parsed.frequency} from {date_label(parsed.start, today)}"]
    await update.message.reply_text("Recurring " + " · ".join(p for p in parts if p))


async def on_stop_recurring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    conn, user, _ = _user(update, context)
    rec = db.get_recurring(conn, user.user_id, _arg_id(query.data))
    if rec is None or not db.stop_recurring(conn, user.user_id, rec.id):
        await query.edit_message_text(STALE)
        return
    await query.edit_message_text(f"Stopped: {fmt_money(rec.amount, user.currency)} {rec.note} {rec.frequency}")


async def cmd_notify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn, user, _ = _user(update, context)
    choice = (context.args[0] if context.args else "").lower()
    if choice not in ("on", "off"):
        state = "on" if user.notify else "off"
        await update.message.reply_text(f"Weekly and monthly summaries are {state}. Use /notify on or /notify off.")
        return
    db.set_notify(conn, user.user_id, choice == "on")
    await update.message.reply_text(f"Weekly and monthly summaries {choice}.")


# --- data export and deletion ---

def _confirm_keyboard(prefix: str, yes_label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(yes_label, callback_data=f"{prefix}:yes"),
                                  InlineKeyboardButton("Cancel", callback_data=f"{prefix}:no")]])


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _user(update, context)
    await update.message.reply_text(EXPORT_WARNING, reply_markup=_confirm_keyboard("export", "Send CSV"))


async def on_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data.endswith(":no"):
        await query.edit_message_text("Export cancelled.")
        return
    conn, user, today = _user(update, context)
    await query.edit_message_text("Here's your data.")
    await query.message.reply_document(document=export_csv(db.all_entries(conn, user.user_id), user.currency, today),
                                       filename="expenses.csv")


async def cmd_deleteaccount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _user(update, context)
    await update.message.reply_text(DELETE_WARNING, reply_markup=_confirm_keyboard("delacct", "Delete everything"))


async def on_deleteaccount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data.endswith(":no"):
        await query.edit_message_text("Cancelled. Nothing was deleted.")
        return
    db.delete_user(_conn(context), update.effective_user.id)
    context.user_data.clear()
    await query.edit_message_text("All your data has been deleted.")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _user(update, context)
    await update.message.reply_text(HELP_TEXT)


BOT_COMMANDS = [
    ("report", "Spending report (week, lastmonth, year)"),
    ("recent", "Last 5 entries (/recent 20 for more)"),
    ("undo", "Delete your latest entry"),
    ("upcoming", "Planned payments"),
    ("recurring", "Repeating payments"),
    ("notify", "Weekly and monthly summaries on/off"),
    ("export", "Download your data"),
    ("currency", "Change currency"),
    ("deleteaccount", "Erase all your data"),
    ("help", "How to use the bot"),
]


# --- errors ---

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if isinstance(update, Update) and update.effective_user else None
    # Never log message text: exc_info carries the traceback only.
    log.error("handler error for user %s: %s", user_id, type(context.error).__name__, exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(error_text(update, context.user_data or {}))


def error_text(update: Update, user_data: dict) -> str:
    """Never claim an entry was lost when it was saved: the reply may fail after the commit."""
    text = update.message.text if update.message and update.message.text else ""
    if not text or text.startswith("/"):
        return COMMAND_ERROR
    return SAVED_UNCONFIRMED if user_data.get("saved_update") == update.update_id else GENERIC_ERROR


async def on_edited(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.edited_message.reply_text(EDIT_NOT_TRACKED)


COMMANDS = {
    "start": cmd_start, "currency": cmd_currency, "undo": cmd_undo, "recent": cmd_recent, "cancel": cmd_cancel,
    "report": cmd_report, "upcoming": cmd_upcoming, "recurring": cmd_recurring, "notify": cmd_notify,
    "export": cmd_export, "deleteaccount": cmd_deleteaccount, "help": cmd_help,
}


def register(app: Application, conn: sqlite3.Connection) -> None:
    app.bot_data["conn"] = conn
    app.bot_data["limiter"] = RateLimiter()
    app.bot_data["renderer"] = CardRenderer()
    app.add_handler(TypeHandler(Update, gate), group=-1)
    # New messages only: an edited message has update.message = None and must not re-run a command.
    for name, callback in COMMANDS.items():
        app.add_handler(CommandHandler(name, callback, filters=filters.UpdateType.MESSAGE))
    app.add_handler(CallbackQueryHandler(on_stop_recurring, pattern=r"^stoprec:\d+$"))
    app.add_handler(CallbackQueryHandler(on_export, pattern=r"^export:(yes|no)$"))
    app.add_handler(CallbackQueryHandler(on_deleteaccount, pattern=r"^delacct:(yes|no)$"))
    app.add_handler(CallbackQueryHandler(on_delete, pattern=r"^(undo|del):\d+$"))
    app.add_handler(CallbackQueryHandler(on_keep, pattern=r"^keep$"))
    app.add_handler(CallbackQueryHandler(on_change_category, pattern=r"^chcat:\d+$"))
    app.add_handler(CallbackQueryHandler(on_category, pattern=r"^cat:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(on_edit, pattern=r"^edit:\d+$"))
    app.add_handler(CallbackQueryHandler(on_currency_button, pattern=r"^cur:[A-Z]{3}$"))
    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE & filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT, on_edited))
    app.add_error_handler(on_error)
