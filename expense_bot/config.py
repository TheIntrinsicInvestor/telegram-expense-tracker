"""Settings come from an env file outside the repo, named by EXPENSE_BOT_ENV."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class Config:
    token: str
    db_path: Path
    backup_dir: Path


def load_config() -> Config:
    env_path = os.environ.get("EXPENSE_BOT_ENV")
    if not env_path:
        raise RuntimeError("EXPENSE_BOT_ENV is not set; point it at the bot's env file")
    values = dotenv_values(env_path)
    for key in ("TELEGRAM_TOKEN", "DB_PATH", "BACKUP_DIR"):
        if not values.get(key):
            raise RuntimeError(f"{key} is missing from {env_path}")
    return Config(
        token=values["TELEGRAM_TOKEN"],
        db_path=Path(values["DB_PATH"]),
        backup_dir=Path(values["BACKUP_DIR"]),
    )
