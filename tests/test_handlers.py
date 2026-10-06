from datetime import datetime, timezone

from telegram import Chat, Message, Update, User
from telegram.ext import Application

from expense_bot import db, handlers
from expense_bot.formatting import COMMAND_ERROR, GENERIC_ERROR, SAVED_UNCONFIRMED

USER = User(id=1, first_name="T", is_bot=False)
CHAT = Chat(id=1, type="private")
NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


def message(text):
    return Message(message_id=1, date=NOW, chat=CHAT, from_user=USER, text=text)


def app():
    a = Application.builder().token("1:x").build()
    handlers.register(a, db.connect(":memory:"))
    return a


def matching(a, update):
    return [h for group in a.handlers.values() for h in group if h.check_update(update)]


def test_edited_text_message_only_hits_edit_notice():
    edited = Update(update_id=1, edited_message=message("16 lunch"))
    hits = matching(app(), edited)
    callbacks = [h.callback for h in hits]
    assert handlers.on_text not in callbacks
    assert handlers.on_edited in callbacks


def test_edited_command_is_ignored():
    edited = Update(update_id=1, edited_message=message("/report"))
    assert handlers.cmd_report not in [h.callback for h in matching(app(), edited)]


def test_new_text_still_logged():
    assert handlers.on_text in [h.callback for h in matching(app(), Update(update_id=1, message=message("15 lunch")))]


def test_error_text_after_save_says_saved():
    update = Update(update_id=7, message=message("15 lunch"))
    assert handlers.error_text(update, {"saved_update": 7}) == SAVED_UNCONFIRMED


def test_error_text_entry_not_saved():
    update = Update(update_id=7, message=message("15 lunch"))
    assert handlers.error_text(update, {"saved_update": 3}) == GENERIC_ERROR


def test_error_text_for_commands_is_neutral():
    update = Update(update_id=7, message=message("/report"))
    assert handlers.error_text(update, {}) == COMMAND_ERROR
