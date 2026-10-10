"""Simple in-memory per-IP sliding-window rate limiter (single process)."""

import os
import threading
import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import HTTPException, Request

WINDOW_SECONDS = 60.0


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float = WINDOW_SECONDS,
                 clock: Callable[[], float] = time.monotonic):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window_seconds:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return False
            hits.append(now)
            return True


def limiter_from_env() -> RateLimiter:
    raw = os.getenv("CHECK_RATE_LIMIT_PER_MINUTE")
    if not raw:
        raise RuntimeError("CHECK_RATE_LIMIT_PER_MINUTE is not set in .env")
    return RateLimiter(max_requests=int(raw))


def rate_limit_dependency(limiter: RateLimiter):
    """FastAPI dependency that rejects a client IP over the limit with HTTP 429."""
    def check(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        if not limiter.allow(ip):
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: at most {limiter.max_requests} checks per "
                       f"{int(limiter.window_seconds)} seconds per IP. Try again later.",
            )
    return check
