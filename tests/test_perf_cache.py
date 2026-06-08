"""TTL 缓存测试 — 验证缓存命中/过期/失效."""
from __future__ import annotations

import time

from src.performance.cache import cached, cached_with_meta, invalidate


def test_cache_hit_avoids_recompute():
    invalidate()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return calls["n"]

    assert cached("k1", fn) == 1
    assert cached("k1", fn) == 1   # 命中缓存, 不重算
    assert calls["n"] == 1


def test_cache_expires():
    invalidate()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return calls["n"]

    assert cached("k2", fn, ttl=1) == 1
    time.sleep(1.1)
    assert cached("k2", fn, ttl=1) == 2   # 过期, 重算
    assert calls["n"] == 2


def test_cached_with_meta_returns_timestamp():
    invalidate()
    val, filled_at = cached_with_meta("k3", lambda: 42)
    assert val == 42
    assert filled_at > 0


def test_invalidate_clears():
    invalidate()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return calls["n"]

    assert cached("k4", fn) == 1
    invalidate("k4")
    assert cached("k4", fn) == 2   # 已清, 重算
