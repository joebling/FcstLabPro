"""测试 src/data/downloader.py::_guard_raw_overwrite —— lesson_0602 写保护.

只测纯函数守卫逻辑, 不触网 (不调真正的 download_binance_klines).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.data.downloader import _guard_raw_overwrite


def _make_raw(tmp_path: Path) -> Path:
    """构造 .../data/raw/x.csv 并写入内容 (模拟已存在的基准)."""
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    p = raw / "btc.csv"
    p.write_text("baseline")
    return p


def test_guard_blocks_existing_raw_overwrite(tmp_path):
    """data/raw/ 下已存在文件 + 未授权 → PermissionError."""
    p = _make_raw(tmp_path)
    with pytest.raises(PermissionError, match="拒绝覆盖训练基准"):
        _guard_raw_overwrite(p, allow_overwrite_raw=False)


def test_guard_allows_with_explicit_flag(tmp_path):
    """显式 allow_overwrite_raw=True → 放行 (重建基准场景)."""
    p = _make_raw(tmp_path)
    _guard_raw_overwrite(p, allow_overwrite_raw=True)  # 不抛即通过


def test_guard_allows_new_raw_file(tmp_path):
    """data/raw/ 下文件不存在 → 放行 (首次创建基准)."""
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    p = raw / "new.csv"  # 不存在
    _guard_raw_overwrite(p, allow_overwrite_raw=False)  # 不抛即通过


def test_guard_allows_live_path(tmp_path):
    """data/live/ 路径即使已存在也放行 (可变区)."""
    live = tmp_path / "data" / "live"
    live.mkdir(parents=True)
    p = live / "btc.csv"
    p.write_text("realtime")
    _guard_raw_overwrite(p, allow_overwrite_raw=False)  # 不抛即通过
