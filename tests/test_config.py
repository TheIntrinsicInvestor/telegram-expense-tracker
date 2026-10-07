from pathlib import Path

import pytest

from expense_bot.config import load_config

PATHS = "DB_PATH=/data/x.db\nBACKUP_DIR=/data/backups\n"


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    env = tmp_path / "bot.env"
    monkeypatch.setenv("EXPENSE_BOT_ENV", str(env))
    monkeypatch.delenv("EXPENSE_BOT_MODE", raising=False)
    return env


def test_load_config_defaults_to_test_token(env_file):
    env_file.write_text("TEST_TELEGRAM_TOKEN=abc\nLIVE_TELEGRAM_TOKEN=xyz\n" + PATHS, encoding="utf-8")
    cfg = load_config()
    assert cfg.token == "abc"
    assert cfg.db_path == Path("/data/x.db")
    assert cfg.backup_dir == Path("/data/backups")


def test_load_config_live_mode_uses_live_token(env_file, monkeypatch):
    env_file.write_text("LIVE_TELEGRAM_TOKEN=xyz\n" + PATHS, encoding="utf-8")
    monkeypatch.setenv("EXPENSE_BOT_MODE", "live")
    assert load_config().token == "xyz"


def test_load_config_unknown_mode_raises(env_file, monkeypatch):
    env_file.write_text("LIVE_TELEGRAM_TOKEN=xyz\n" + PATHS, encoding="utf-8")
    monkeypatch.setenv("EXPENSE_BOT_MODE", "prod")
    with pytest.raises(RuntimeError, match="EXPENSE_BOT_MODE"):
        load_config()


def test_load_config_missing_var_raises(monkeypatch):
    monkeypatch.delenv("EXPENSE_BOT_ENV", raising=False)
    with pytest.raises(RuntimeError, match="EXPENSE_BOT_ENV"):
        load_config()


def test_load_config_missing_key_raises(env_file, monkeypatch):
    env_file.write_text("TEST_TELEGRAM_TOKEN=abc\n" + PATHS, encoding="utf-8")
    monkeypatch.setenv("EXPENSE_BOT_MODE", "live")
    with pytest.raises(RuntimeError, match="LIVE_TELEGRAM_TOKEN"):
        load_config()
