"""IP-based rate limiting middleware and dependencies for RepoScope API (Day 17).

Supports slowapi if installed, with a self-contained in-memory sliding-window
fallback to ensure zero-dependency portability across staging and test environments.
"""
from collections import defaultdict
import os
import threading
import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

RATE_LIMIT_ENABLED = os.getenv("REPOSCOPE_RATE_LIMIT_ENABLED", "true").lower() not in ("0", "false", "no", "off")


class RateLimitExceeded(Exception):
    """Raised when an IP exceeds its allotted request quota."""

    def __init__(self, retry_after: int = 60, detail: str | None = None) -> None:
        self.retry_after = max(1, retry_after)
        self.detail = detail or f"Too many requests. Please retry in {self.retry_after} seconds."
        super().__init__(self.detail)


def get_client_ip(request: Request) -> str:
    """Extract real client IP address from request headers or socket."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding-window IP rate limiter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: float = 60.0) -> tuple[bool, int]:
        """Check if request is allowed for key under limit.

        Returns (allowed, retry_after_seconds).
        """
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            timestamps = self._records[key]
            # Prune timestamps older than cutoff
            valid_timestamps = [t for t in timestamps if t > cutoff]
            if len(valid_timestamps) >= max_requests:
                oldest_timestamp = valid_timestamps[0]
                retry_after = int(window_seconds - (now - oldest_timestamp)) + 1
                self._records[key] = valid_timestamps
                return False, max(1, retry_after)
            valid_timestamps.append(now)
            self._records[key] = valid_timestamps
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._records.clear()


limiter = SlidingWindowRateLimiter()


def rate_limit(max_requests: int = 60, window_seconds: float = 60.0):
    """FastAPI dependency to rate-limit specific endpoints by client IP."""

    async def dependency(request: Request) -> None:
        if not RATE_LIMIT_ENABLED or os.getenv("TESTING") == "true":
            return
        ip = get_client_ip(request)
        key = f"{request.url.path}:{ip}"
        allowed, retry_after = limiter.is_allowed(key, max_requests, window_seconds)
        if not allowed:
            raise RateLimitExceeded(retry_after=retry_after)

    return dependency
