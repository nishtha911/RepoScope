import pytest
from reposcope.integrations.llm_cache import MemoryLLMCache


def test_ttl_expiration():
    now = [0.0]
    cache = MemoryLLMCache(ttl_seconds=5, clock=lambda: now[0])
    cache.set("key", {"answer":"one"})
    now[0] = 4
    assert cache.get("key") == {"answer":"one"}
    now[0] = 5
    assert cache.get("key") is None


def test_lru_eviction():
    cache = MemoryLLMCache(max_entries=2)
    cache.set("a", 1); cache.set("b", 2)
    assert cache.get("a") == 1
    cache.set("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1 and cache.get("c") == 3


def test_byte_limit_and_oversized_entry():
    cache = MemoryLLMCache(max_bytes=20)
    cache.set("a", "1234567890")
    cache.set("b", "1234567890")
    assert cache.get("a") is None
    assert cache.get("b") == "1234567890"
    cache.set("huge", "x"*100)
    assert cache.get("huge") is None


def test_mutation_isolation():
    cache = MemoryLLMCache()
    original = {"values":[1]}
    cache.set("key", original)
    original["values"].append(2)
    retrieved = cache.get("key")
    retrieved["values"].append(3)
    assert cache.get("key") == {"values":[1]}


def test_clear_and_replacement_accounting():
    cache = MemoryLLMCache()
    cache.set("a", 1); cache.set("a", 2)
    assert cache.get("a") == 2
    cache.clear()
    assert cache.get("a") is None and cache._bytes == 0


@pytest.mark.parametrize("options", [{"max_entries":0},{"max_entries":True},
    {"ttl_seconds":0},{"ttl_seconds":float("nan")},{"max_bytes":-1}])
def test_invalid_cache_options(options):
    with pytest.raises(ValueError):
        MemoryLLMCache(**options)
