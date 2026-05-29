"""进程内 TTL 缓存 — 对齐 RiskDetect perf/common.py 的 cached().

dashboard 请求时实时算 (回填+聚合), 用 TTL 缓存挡住重复请求, 避免每次
HTTP 都重读 archive + pandas 切片。信号日更, 默认 TTL 30 分钟足够。

两个时钟:
  monotonic — 算 TTL (不受系统时间调整影响, 可靠)
  wall      — 报"这份数据啥时候算的"(给页面显示新鲜度)
"""
from __future__ import annotations

import time
from typing import Callable

# key → (monotonic_filled_at, value, wall_filled_at_epoch)
_CACHE: dict[str, tuple[float, object, float]] = {}

DEFAULT_TTL_SECONDS = 1_800  # 30 分钟


def cached_with_meta(
    key: str, fn: Callable[[], object], *, ttl: int = DEFAULT_TTL_SECONDS
) -> tuple[object, float]:
    """新鲜则返回缓存值, 否则调 fn() 重算并缓存.

    Returns (value, filled_at_epoch) — filled_at 是真实 Unix 时间戳, 供页面
    显示"数据算于何时"。
    """
    mono = time.monotonic()
    hit = _CACHE.get(key)
    if hit and mono - hit[0] < ttl:
        return hit[1], hit[2]
    value = fn()
    wall = time.time()
    _CACHE[key] = (mono, value, wall)
    return value, wall


def cached(key: str, fn: Callable[[], object], *, ttl: int = DEFAULT_TTL_SECONDS) -> object:
    """同 cached_with_meta, 只要值."""
    value, _ = cached_with_meta(key, fn, ttl=ttl)
    return value


def invalidate(key: str | None = None) -> None:
    """清缓存 (测试 / 强制刷新用). key=None 清全部."""
    if key is None:
        _CACHE.clear()
    else:
        _CACHE.pop(key, None)
