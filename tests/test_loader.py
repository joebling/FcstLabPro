"""测试 src/data/loader.py::load_csv —— 含根因3修复 (start/end 过滤).

覆盖:
  1. 无 start/end → 全量返回 (向后兼容)
  2. end 过滤 (含边界)
  3. start 过滤 (含边界)
  4. start+end 同时
  5. 过滤后空 → ValueError
  6. 必需列校验 / 去重 / 排序仍正常
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.data.loader import load_csv


def _write_csv(tmp_path, rows):
    p = tmp_path / "ohlcv.csv"
    df = pd.DataFrame(rows).set_index("date")
    df.to_csv(p)
    return p


def _sample(tmp_path):
    rows = [
        {"date": "2025-12-30", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
        {"date": "2025-12-31", "open": 2, "high": 3, "low": 1.5, "close": 2.5, "volume": 200},
        {"date": "2026-01-01", "open": 3, "high": 4, "low": 2.5, "close": 3.5, "volume": 300},
        {"date": "2026-01-02", "open": 4, "high": 5, "low": 3.5, "close": 4.5, "volume": 400},
    ]
    return _write_csv(tmp_path, rows)


def test_no_filter_returns_all(tmp_path):
    df = load_csv(_sample(tmp_path))
    assert len(df) == 4


def test_end_filter_inclusive(tmp_path):
    df = load_csv(_sample(tmp_path), end="2025-12-31")
    assert len(df) == 2
    assert str(df.index[-1].date()) == "2025-12-31"


def test_start_filter_inclusive(tmp_path):
    df = load_csv(_sample(tmp_path), start="2026-01-01")
    assert len(df) == 2
    assert str(df.index[0].date()) == "2026-01-01"


def test_start_and_end(tmp_path):
    df = load_csv(_sample(tmp_path), start="2025-12-31", end="2026-01-01")
    assert len(df) == 2


def test_empty_after_filter_raises(tmp_path):
    with pytest.raises(ValueError, match="日期过滤后无数据"):
        load_csv(_sample(tmp_path), start="2030-01-01")


def test_missing_columns_raises(tmp_path):
    p = tmp_path / "bad.csv"
    pd.DataFrame({"date": ["2025-01-01"], "open": [1]}).set_index("date").to_csv(p)
    with pytest.raises(ValueError, match="缺少必需列"):
        load_csv(p)


def test_dedup_and_sort(tmp_path):
    rows = [
        {"date": "2026-01-02", "open": 4, "high": 5, "low": 3, "close": 4, "volume": 1},
        {"date": "2026-01-01", "open": 3, "high": 4, "low": 2, "close": 3, "volume": 1},
        {"date": "2026-01-01", "open": 9, "high": 9, "low": 9, "close": 9, "volume": 9},  # dup
    ]
    df = load_csv(_write_csv(tmp_path, rows))
    assert len(df) == 2  # 去重
    assert list(df.index) == sorted(df.index)  # 排序
    # keep=last → 2026-01-01 取后者
    assert df.loc["2026-01-01", "close"] == 9
