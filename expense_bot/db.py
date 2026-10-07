"""All SQLite access. Every function that touches user data filters on user_id."""

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from expense_bot.models import Entry, Recurring, User
from expense_bot.money import round2
from expense_bot.recurring import next_occurrence

SCHEMA_VERSION = 2
REMINDER_GRACE_DAYS = 7  # a reminder missed while the bot was down is still sent this late

_SCHEMA = """
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    currency TEXT NOT NULL DEFAULT 'GBP',
    timezone TEXT NOT NULL DEFAULT 'Europe/London',
    notify INTEGER NOT NULL DEFAULT 1,
    last_weekly_sent TEXT,
    last_monthly_sent TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE recurring (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users ON DELETE CASCADE,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    note TEXT NOT NULL,
    frequency TEXT NOT NULL CHECK (frequency IN ('weekly', 'monthly', 'yearly')),
    anchor_day INTEGER NOT NULL,
    next_date TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users ON DELETE CASCADE,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL,
    recurring_id INTEGER REFERENCES recurring ON DELETE SET NULL,
    reminded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    notified INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE user_keywords (
    user_id INTEGER NOT NULL REFERENCES users ON DELETE CASCADE,
    word TEXT NOT NULL,
    category TEXT NOT NULL,
    PRIMARY KEY (user_id, word)
);
CREATE INDEX idx_entries_user_date ON entries (user_id, date);
CREATE INDEX idx_entries_user_id ON entries (user_id, id);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == 0:
        with conn:
            conn.executescript(_SCHEMA)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    elif version == 1:
        # v2: entries.notified, 0 while a recurring payment's "Recurring: ..." message is unsent.
        with conn:
            conn.execute("ALTER TABLE entries ADD COLUMN notified INTEGER NOT NULL DEFAULT 1")
            conn.execute("PRAGMA user_version = 2")
    return conn


# --- row conversion ---

def _user(row: sqlite3.Row) -> User:
    return User(row["user_id"], row["currency"], row["timezone"], bool(row["notify"]),
                row["last_weekly_sent"], row["last_monthly_sent"])


def _entry(row: sqlite3.Row) -> Entry:
    return Entry(row["id"], row["user_id"], row["amount"], row["category"], row["note"],
                 date.fromisoformat(row["date"]), row["recurring_id"], bool(row["reminded"]), row["created_at"])


def _recurring(row: sqlite3.Row) -> Recurring:
    return Recurring(row["id"], row["user_id"], row["amount"], row["category"], row["note"], row["frequency"],
                     row["anchor_day"], date.fromisoformat(row["next_date"]), bool(row["active"]))


def _write(conn: sqlite3.Connection, sql: str, params: tuple) -> int:
    """Run one write and commit; returns the number of rows changed."""
    with conn:
        return conn.execute(sql, params).rowcount


# --- users ---

def _previous_month(today: date) -> str:
    year, month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    return f"{year:04d}-{month:02d}"


def ensure_user(conn: sqlite3.Connection, user_id: int, today: date) -> User:
    _write(conn, "INSERT OR IGNORE INTO users (user_id, last_monthly_sent, created_at) VALUES (?, ?, ?)",
           (user_id, _previous_month(today), _now_iso()))
    return get_user(conn, user_id)


def get_user(conn: sqlite3.Connection, user_id: int) -> User | None:
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return _user(row) if row else None


def all_users(conn: sqlite3.Connection) -> list[User]:
    return [_user(r) for r in conn.execute("SELECT * FROM users ORDER BY user_id")]


@dataclass(frozen=True)
class UserStats:
    total: int
    joined_7d: int
    active_7d: int  # logged an entry themselves; automatic recurring entries don't count
    active_30d: int


def user_stats(conn: sqlite3.Connection, now_utc: datetime) -> UserStats:
    """Counts across all users, for the owner's /stats. Returns numbers only, never anyone's data."""
    since = {days: (now_utc - timedelta(days=days)).isoformat(timespec="seconds") for days in (7, 30)}
    active = "SELECT COUNT(DISTINCT user_id) FROM entries WHERE recurring_id IS NULL AND created_at >= ?"
    return UserStats(
        total=conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        joined_7d=conn.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (since[7],)).fetchone()[0],
        active_7d=conn.execute(active, (since[7],)).fetchone()[0],
        active_30d=conn.execute(active, (since[30],)).fetchone()[0],
    )


def set_currency(conn: sqlite3.Connection, user_id: int, code: str) -> None:
    _write(conn, "UPDATE users SET currency = ? WHERE user_id = ?", (code, user_id))


def set_notify(conn: sqlite3.Connection, user_id: int, on: bool) -> None:
    _write(conn, "UPDATE users SET notify = ? WHERE user_id = ?", (int(on), user_id))


def set_last_weekly(conn: sqlite3.Connection, user_id: int, value: str) -> None:
    _write(conn, "UPDATE users SET last_weekly_sent = ? WHERE user_id = ?", (value, user_id))


def set_last_monthly(conn: sqlite3.Connection, user_id: int, value: str) -> None:
    _write(conn, "UPDATE users SET last_monthly_sent = ? WHERE user_id = ?", (value, user_id))


def delete_user(conn: sqlite3.Connection, user_id: int) -> None:
    _write(conn, "DELETE FROM users WHERE user_id = ?", (user_id,))


# --- entries ---

def add_entry(conn: sqlite3.Connection, user_id: int, amount: float, category: str, note: str,
              entry_date: date, today: date, recurring_id: int | None = None) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO entries (user_id, amount, category, note, date, recurring_id, reminded, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, round2(amount), category, note, entry_date.isoformat(), recurring_id,
             int(entry_date <= today), _now_iso()),
        )
    return cur.lastrowid


def get_entry(conn: sqlite3.Connection, user_id: int, entry_id: int) -> Entry | None:
    row = conn.execute("SELECT * FROM entries WHERE id = ? AND user_id = ?", (entry_id, user_id)).fetchone()
    return _entry(row) if row else None


def latest_entry(conn: sqlite3.Connection, user_id: int) -> Entry | None:
    row = conn.execute("SELECT * FROM entries WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
    return _entry(row) if row else None


def recent_entries(conn: sqlite3.Connection, user_id: int, limit: int = 10) -> list[Entry]:
    rows = conn.execute("SELECT * FROM entries WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
    return [_entry(r) for r in rows]


def all_entries(conn: sqlite3.Connection, user_id: int) -> list[Entry]:
    rows = conn.execute("SELECT * FROM entries WHERE user_id = ? ORDER BY date, id", (user_id,))
    return [_entry(r) for r in rows]


def update_entry(conn: sqlite3.Connection, user_id: int, entry_id: int, amount: float, category: str,
                 note: str, entry_date: date, today: date) -> bool:
    return _write(
        conn,
        "UPDATE entries SET amount = ?, category = ?, note = ?, date = ?, reminded = ? WHERE id = ? AND user_id = ?",
        (round2(amount), category, note, entry_date.isoformat(), int(entry_date <= today), entry_id, user_id),
    ) == 1


def set_entry_category(conn: sqlite3.Connection, user_id: int, entry_id: int, category: str) -> bool:
    return _write(conn, "UPDATE entries SET category = ? WHERE id = ? AND user_id = ?",
                  (category, entry_id, user_id)) == 1


def delete_entry(conn: sqlite3.Connection, user_id: int, entry_id: int) -> bool:
    return _write(conn, "DELETE FROM entries WHERE id = ? AND user_id = ?", (entry_id, user_id)) == 1


def upcoming_entries(conn: sqlite3.Connection, user_id: int, today: date) -> list[Entry]:
    rows = conn.execute("SELECT * FROM entries WHERE user_id = ? AND date > ? ORDER BY date, id",
                        (user_id, today.isoformat()))
    return [_entry(r) for r in rows]


def due_reminders(conn: sqlite3.Connection, user_id: int, today: date) -> list[Entry]:
    earliest = today - timedelta(days=REMINDER_GRACE_DAYS)
    rows = conn.execute("SELECT * FROM entries WHERE user_id = ? AND date BETWEEN ? AND ? AND reminded = 0 "
                        "ORDER BY date, id", (user_id, earliest.isoformat(), today.isoformat()))
    return [_entry(r) for r in rows]


def mark_reminded(conn: sqlite3.Connection, user_id: int, entry_id: int) -> None:
    _write(conn, "UPDATE entries SET reminded = 1 WHERE id = ? AND user_id = ?", (entry_id, user_id))


# --- learned category words ---

def learn_word(conn: sqlite3.Connection, user_id: int, word: str, category: str) -> None:
    _write(conn, "INSERT INTO user_keywords (user_id, word, category) VALUES (?, ?, ?) "
                 "ON CONFLICT (user_id, word) DO UPDATE SET category = excluded.category",
           (user_id, word, category))


def learned_words(conn: sqlite3.Connection, user_id: int) -> dict[str, str]:
    rows = conn.execute("SELECT word, category FROM user_keywords WHERE user_id = ?", (user_id,))
    return {r["word"]: r["category"] for r in rows}


# --- recurring payments ---

def add_recurring(conn: sqlite3.Connection, user_id: int, amount: float, category: str, note: str,
                  frequency: str, start: date) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO recurring (user_id, amount, category, note, frequency, anchor_day, next_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, round2(amount), category, note, frequency, start.day, start.isoformat()),
        )
    return cur.lastrowid


def active_recurring(conn: sqlite3.Connection, user_id: int) -> list[Recurring]:
    rows = conn.execute("SELECT * FROM recurring WHERE user_id = ? AND active = 1 ORDER BY id", (user_id,))
    return [_recurring(r) for r in rows]


def get_recurring(conn: sqlite3.Connection, user_id: int, rid: int) -> Recurring | None:
    row = conn.execute("SELECT * FROM recurring WHERE id = ? AND user_id = ?", (rid, user_id)).fetchone()
    return _recurring(row) if row else None


def stop_recurring(conn: sqlite3.Connection, user_id: int, rid: int) -> bool:
    return _write(conn, "UPDATE recurring SET active = 0 WHERE id = ? AND user_id = ? AND active = 1",
                  (rid, user_id)) == 1


def materialise_occurrence(conn: sqlite3.Connection, rec: Recurring, today: date,
                           notified: bool = False) -> int | None:
    """Log one due occurrence and advance next_date atomically. A stale `rec` changes nothing."""
    following = next_occurrence(rec.next_date, rec.frequency, rec.anchor_day)
    with conn:
        moved = conn.execute(
            "UPDATE recurring SET next_date = ? WHERE id = ? AND user_id = ? AND next_date = ? AND active = 1",
            (following.isoformat(), rec.id, rec.user_id, rec.next_date.isoformat()),
        ).rowcount
        if moved != 1:
            return None
        cur = conn.execute(
            "INSERT INTO entries (user_id, amount, category, note, date, recurring_id, reminded, created_at, notified) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (rec.user_id, rec.amount, rec.category, rec.note, rec.next_date.isoformat(), rec.id, _now_iso(),
             int(notified)),
        )
    return cur.lastrowid


def unnotified_recurring_entries(conn: sqlite3.Connection, user_id: int) -> list[Entry]:
    rows = conn.execute("SELECT * FROM entries WHERE user_id = ? AND notified = 0 ORDER BY date, id", (user_id,))
    return [_entry(r) for r in rows]


def mark_notified(conn: sqlite3.Connection, user_id: int, entry_id: int) -> None:
    _write(conn, "UPDATE entries SET notified = 1 WHERE id = ? AND user_id = ?", (entry_id, user_id))
