"""Bounded process-local TTL/LRU response cache; no secrets or prompts as keys."""
import json
import math
from collections import OrderedDict
from threading import RLock
from time import monotonic


class MemoryLLMCache:
    def __init__(self, *, max_entries=256, ttl_seconds=300, max_bytes=16_000_000, clock=monotonic):
        for name, value in (("max_entries", max_entries), ("max_bytes", max_bytes)):
            if type(value) is not int or value < 1:
                raise ValueError(name + " must be a positive integer")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)) or not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive and finite")
        self.max_entries, self.ttl_seconds, self.max_bytes = max_entries, ttl_seconds, max_bytes
        self._clock, self._lock = clock, RLock()
        self._items, self._bytes = OrderedDict(), 0

    def _remove(self, key):
        item = self._items.pop(key)
        self._bytes -= item[2]

    def get(self, key):
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            if item[0] <= self._clock():
                self._remove(key)
                return None
            self._items.move_to_end(key)
            return json.loads(item[1])

    def set(self, key, value):
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        size = len(key.encode()) + len(raw.encode())
        with self._lock:
            if key in self._items:
                self._remove(key)
            now = self._clock()
            for expired in [k for k, v in self._items.items() if v[0] <= now]:
                self._remove(expired)
            if size > self.max_bytes:
                return
            while self._items and (len(self._items) >= self.max_entries or self._bytes + size > self.max_bytes):
                self._remove(next(iter(self._items)))
            self._items[key] = (now + self.ttl_seconds, raw, size)
            self._bytes += size

    def clear(self):
        with self._lock:
            self._items.clear()
            self._bytes = 0
