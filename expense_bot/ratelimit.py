"""Per-user sliding-window rate limit, in memory (resets on restart, which is fine)."""

from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int = 30, window: float = 60.0):
        self.limit = limit
        self.window = window
        self._hits: dict[int, deque[float]] = defaultdict(deque)
        self._warned: set[int] = set()

    def check(self, user_id: int, now: float) -> str:
        """Returns "ok", "warn" (first message over the limit) or "drop"."""
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
