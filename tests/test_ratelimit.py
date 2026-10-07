from expense_bot.ratelimit import RateLimiter


def test_limit_warn_then_drop_then_recover():
    rl = RateLimiter(limit=30, window=60.0)
    assert [rl.check(1, 0.0) for _ in range(30)] == ["ok"] * 30
    assert rl.check(1, 0.0) == "warn"
    assert rl.check(1, 0.0) == "drop"
    assert rl.check(1, 61.0) == "ok"


def test_users_independent():
    rl = RateLimiter(limit=2, window=60.0)
    rl.check(1, 0.0)
    rl.check(1, 0.0)
    assert rl.check(1, 0.0) == "warn"
    assert rl.check(2, 0.0) == "ok"


def test_quiet_users_are_forgotten():
    rl = RateLimiter(limit=1, window=60.0)
    rl.check(1, 0.0)
    rl.check(1, 0.0)  # warned
    rl.check(2, 100.0)  # user 1 has been quiet for a full window
    assert set(rl._hits) == {2} and rl._warned == set()
