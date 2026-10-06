from pathlib import Path

import pytest

from expense_bot.config import load_config


def test_load_config_reads_env_file(tmp_path, monkeypatch):
    env = tmp_path / "bot.env"
    env.write_text("TELEGRAM_TOKEN=abc\nDB_PATH=/data/x.db\nBACKUP_DIR=/data/backups\n", encoding="utf-8")
    monkeypatch.setenv("EXPENSE_BOT_ENV", str(env))
    cfg = load_config()
    assert cfg.token == "abc"
    assert cfg.db_path == Path("/data/x.db")
    assert cfg.backup_dir == Path("/data/backups")


def test_load_config_missing_var_raises(monkeypatch):
    monkeypatch.delenv("EXPENSE_BOT_ENV", raising=False)
    with pytest.raises(RuntimeError, match="EXPENSE_BOT_ENV"):
        load_config()


def test_load_config_missing_key_raises(tmp_path, monkeypatch):
    env = tmp_path / "bot.env"
    env.write_text("DB_PATH=/data/x.db\nBACKUP_DIR=/data/backups\n", encoding="utf-8")
    monkeypatch.setenv("EXPENSE_BOT_ENV", str(env))
    with pytest.raises(RuntimeError, match="TELEGRAM_TOKEN"):
        load_config()
