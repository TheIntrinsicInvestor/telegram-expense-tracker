"""Settings come from an env file outside the repo, named by EXPENSE_BOT_ENV.

EXPENSE_BOT_MODE (test or live, default test) picks TEST_TELEGRAM_TOKEN or LIVE_TELEGRAM_TOKEN,
so a local run never takes over the live bot by accident.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

MODES = ("test", "live")
# Telegram only passes a deep-link start parameter made of these characters, at most 64 of them.
_INVITE_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True)
class Config:
    token: str
    db_path: Path
    backup_dir: Path
    invite_code: str  # new users join only via t.me/<bot>?start=<invite_code>


def load_config() -> Config:
    env_path = os.environ.get("EXPENSE_BOT_ENV")
    if not env_path:
        raise RuntimeError("EXPENSE_BOT_ENV is not set; point it at the bot's env file")
    mode = os.environ.get("EXPENSE_BOT_MODE", "test")
    if mode not in MODES:
        raise RuntimeError(f"EXPENSE_BOT_MODE must be test or live, not {mode!r}")
    token_key = f"{mode.upper()}_TELEGRAM_TOKEN"
    values = dotenv_values(env_path)
    for key in (token_key, "DB_PATH", "BACKUP_DIR", "INVITE_CODE"):
        if not values.get(key):
            raise RuntimeError(f"{key} is missing from {env_path}")
    if not _INVITE_CODE_RE.match(values["INVITE_CODE"]):
        raise RuntimeError("INVITE_CODE must be 1 to 64 letters, digits, _ or -, or Telegram drops it from the link")
    return Config(
        token=values[token_key],
        db_path=Path(values["DB_PATH"]),
        backup_dir=Path(values["BACKUP_DIR"]),
        invite_code=values["INVITE_CODE"],
    )
