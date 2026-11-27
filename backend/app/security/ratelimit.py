"""In-process rate limiting.

A single-node deployment does not need Redis to protect its write endpoints.
This is a fixed-window counter keyed by client identity + route bucket, with a
bounded dictionary so a hostile client cannot grow memory without limit.

Limitations are stated rather than hidden: the counters live in one process, so
they do not coordinate across workers. That is acceptable for the SQLite
single-node deployment this project targets; a multi-worker deployment would
need a shared store.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict

# Route prefixes that mutate state and therefore get a stricter budget.
WRITE_BUCKETS = {
    "/api/ingestion/run": 6,
    "/api/events/seed": 2,
    "/api/reports": 12,
    "/api/alerts": 60,
    "/api/alert-rules": 60,
}

MAX_TRACKED_KEYS = 10_000


class FixedWindowLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self.limit = max(1, int(limit_per_minute))
        self._hits: OrderedDict[tuple[str, str], list] = OrderedDict()
        self._lock = threading.Lock()

    def _bucket_for(self, path: str) -> tuple[str, int]:
        for prefix, limit in WRITE_BUCKETS.items():
            if path.startswith(prefix):
                return prefix, limit
        return "read", self.limit

    def check(self, identity: str, path: str) -> tuple[bool, int, int]:
        """Return ``(allowed, remaining, retry_after_seconds)``."""
        bucket, limit = self._bucket_for(path)
        now = time.monotonic()
        window = int(now // 60)
        key = (identity, f"{bucket}:{window}")

        with self._lock:
            count = self._hits.get(key, 0)
            if isinstance(count, int):
                count += 1
            else:  # pragma: no cover - defensive
                count = 1
            self._hits[key] = count
            self._hits.move_to_end(key)

            while len(self._hits) > MAX_TRACKED_KEYS:
                self._hits.popitem(last=False)

        remaining = max(0, limit - count)
        retry_after = max(1, 60 - int(now % 60))
        return count <= limit, remaining, retry_after

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_limiter: FixedWindowLimiter | None = None


def get_limiter(limit_per_minute: int) -> FixedWindowLimiter:
    global _limiter
    if _limiter is None or _limiter.limit != limit_per_minute:
        _limiter = FixedWindowLimiter(limit_per_minute)
    return _limiter
