from pathlib import Path

import pytest

from expense_bot.config import load_config

PATHS = "DB_PATH=/data/x.db\nBACKUP_DIR=/data/backups\nINVITE_CODE=abc123\n"


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
    assert cfg.invite_code == "abc123"


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


def test_load_config_requires_invite_code(env_file):
    env_file.write_text("TEST_TELEGRAM_TOKEN=abc\nDB_PATH=/data/x.db\nBACKUP_DIR=/data/backups\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="INVITE_CODE"):
        load_config()


def test_owner_id_is_optional(env_file):
    env_file.write_text("TEST_TELEGRAM_TOKEN=abc\n" + PATHS, encoding="utf-8")
    assert load_config().owner_id is None
    env_file.write_text("TEST_TELEGRAM_TOKEN=abc\nOWNER_ID=2141\n" + PATHS, encoding="utf-8")
    assert load_config().owner_id == 2141


@pytest.mark.parametrize("code",["has space", "aB3+x/9=", "café", "x" * 65])
def test_load_config_rejects_codes_telegram_cannot_carry(env_file, code):
    env_file.write_text(f"TEST_TELEGRAM_TOKEN=abc\nDB_PATH=/d.db\nBACKUP_DIR=/b\nINVITE_CODE={code}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="INVITE_CODE"):
        load_config()
