"""Per-user sliding-window rate limit, in memory (resets on restart, which is fine)."""

from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int = 30, window: float = 60.0):
        self.limit = limit
        self.window = window
        self._hits: dict[int, deque[float]] = defaultdict(deque)
        self._warned: set[int] = set()
        self._last_sweep = 0.0

    def _forget_quiet(self, now: float) -> None:
        """Drops users with no hits in the last window, so one-off strangers don't stay in memory."""
        for user_id in [u for u, hits in self._hits.items() if hits[-1] <= now - self.window]:
            del self._hits[user_id]
            self._warned.discard(user_id)
        self._last_sweep = now

    def check(self, user_id: int, now: float) -> str:
        """Returns "ok", "warn" (first message over the limit) or "drop"."""
        if now - self._last_sweep >= self.window:
            self._forget_quiet(now)
        hits = self._hits[user_id]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) < self.limit:
            hits.append(now)
            self._warned.discard(user_id)
            return "ok"
        if user_id in self._warned:
            return "drop"
        self._warned.add(user_id)
        return "warn"
