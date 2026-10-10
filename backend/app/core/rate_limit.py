import math
import time
from collections import deque
from threading import Lock

from app.core.errors import AppError


class RateLimiter:
    """Counts recent attempts per key, in memory.

    Enough for a single API process. Move the counters to Redis before running
    more than one process, or the limits apply per process.
    """

    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _recent(self, key: str, window_seconds: int, now: float) -> deque[float]:
        attempts = self._attempts.get(key)
        if attempts is None:
            return deque()
        while attempts and attempts[0] <= now - window_seconds:
            attempts.popleft()
        if not attempts:
            # Nothing recent: forget the key, or every address ever tried would stay in memory for good.
            del self._attempts[key]
        return attempts

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        """Raise 429 when the key has already used up its attempts."""
        now = time.monotonic()
        with self._lock:
            attempts = self._recent(key, window_seconds, now)
            if len(attempts) >= limit:
                retry_after = max(1, math.ceil(attempts[0] + window_seconds - now))
                raise AppError(
                    429,
                    "TOO_MANY_ATTEMPTS",
                    "Too many attempts. Please wait a few minutes and try again.",
                    headers={"Retry-After": str(retry_after)},
                )

    def record(self, key: str, *, window_seconds: int) -> None:
        now = time.monotonic()
        with self._lock:
            self._recent(key, window_seconds, now)
            self._attempts.setdefault(key, deque()).append(now)

    def clear(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._attempts.clear()
            else:
                self._attempts.pop(key, None)


limiter = RateLimiter()
