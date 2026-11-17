"""Unit tests for IP-based API rate limiting (Day 17)."""
import asyncio
from unittest.mock import MagicMock
import pytest
from starlette.requests import Request

from reposcope.api.rate_limit import (
    SlidingWindowRateLimiter, RateLimitExceeded, get_client_ip, rate_limit,
)
from reposcope.main import rate_limit_handler


def test_sliding_window_rate_limiter_allows_under_limit():
    limiter = SlidingWindowRateLimiter()
    key = "test-ip:127.0.0.1"

    for _ in range(5):
        allowed, retry_after = limiter.is_allowed(key, max_requests=5, window_seconds=60)
        assert allowed is True
        assert retry_after == 0

    # 6th request exceeds limit
    allowed, retry_after = limiter.is_allowed(key, max_requests=5, window_seconds=60)
    assert allowed is False
    assert retry_after > 0


def test_rate_limit_handler_returns_429_envelope():
    request = MagicMock(spec=Request)
    exc = RateLimitExceeded(retry_after=45, detail="Too many requests. Please wait 45 seconds.")

    response = rate_limit_handler(request, exc)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "45"

    import json
    body = json.loads(response.body.decode("utf-8"))
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["error"]["status"] == 429
    assert body["error"]["details"]["retry_after"] == 45
    assert "Too many requests" in body["error"]["message"]


def test_get_client_ip_prefers_forwarded_headers():
    req_forwarded = MagicMock(spec=Request)
    req_forwarded.headers = {"x-forwarded-for": "203.0.113.195, 70.41.3.18"}
    assert get_client_ip(req_forwarded) == "203.0.113.195"

    req_real = MagicMock(spec=Request)
    req_real.headers = {"x-real-ip": "198.51.100.1"}
    assert get_client_ip(req_real) == "198.51.100.1"

    req_client = MagicMock(spec=Request)
    req_client.headers = {}
    req_client.client = MagicMock(host="192.168.1.50")
    assert get_client_ip(req_client) == "192.168.1.50"
