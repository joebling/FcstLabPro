"""市场数据同步任务测试 — best-effort 隔离 / 退出码 / OI-LS 列名回归.

全部 mock, 不碰网络。
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts import sync_market_data as smd


# ---------- _is_fresh: 识破 "API失败→回退旧缓存" 的假成功 ----------

def _df_ending(day: str) -> pd.DataFrame:
    idx = pd.to_datetime(["2026-01-01", day])
    return pd.DataFrame({"v": [1.0, 2.0]}, index=idx)


def test_is_fresh_recent_true():
    assert smd._is_fresh(_df_ending(str(pd.Timestamp.today().date()))) is True


def test_is_fresh_stale_false():
    # 陈旧缓存(如 451 后回退的 3 月旧数据) → 不算成功
    assert smd._is_fresh(_df_ending("2026-03-08")) is False


def test_is_fresh_empty_or_none_false():
    assert smd._is_fresh(pd.DataFrame()) is False
    assert smd._is_fresh(None) is False


# ---------- best-effort 隔离 ----------

def test_one_source_failure_isolated(monkeypatch):
    """单源抛异常 → 不传染, 其他源照常, 结果含全部 key。"""
    def boom():
        raise RuntimeError("yfinance 抽风")

    monkeypatch.setattr(smd, "SOURCES", {
        "funding": lambda: True,
        "oi_ls": lambda: True,
        "macro": boom,
    })
    res = smd.sync_market_data()
    assert res == {"funding": True, "oi_ls": True, "macro": False}


def test_empty_data_marked_failed(monkeypatch):
    """源返回 False (空数据) 也算失败, 但不抛。"""
    monkeypatch.setattr(smd, "SOURCES", {
        "funding": lambda: True,
        "oi_ls": lambda: False,
    })
    res = smd.sync_market_data()
    assert res == {"funding": True, "oi_ls": False}


# ---------- 退出码语义 ----------

def test_exit_code_all_ok(monkeypatch):
    monkeypatch.setattr(smd, "SOURCES", {"a": lambda: True, "b": lambda: True})
    assert smd.main() == 0


def test_exit_code_any_fail(monkeypatch):
    monkeypatch.setattr(smd, "SOURCES", {"a": lambda: True, "b": lambda: False})
    assert smd.main() == 1


# ---------- OI/LS 列名回归 (防回到 oi_usdt/ls_ratio 的错列名) ----------

def test_oi_ls_column_names(monkeypatch, tmp_path):
    """sync_oi_ls 落盘的列名必须是市场页要的 long_short_ratio / open_interest_usd。"""
    import scripts.sync_binance_oi_ls as sync

    ls = pd.DataFrame(
        {"long_account": [0.6], "short_account": [0.4], "long_short_ratio": [1.5]},
        index=pd.to_datetime(["2026-06-08"]),
    )
    ls.index.name = "date"
    oi = pd.DataFrame(
        {"open_interest": [1000.0], "open_interest_usd": [5.0e8]},
        index=pd.to_datetime(["2026-06-08"]),
    )
    oi.index.name = "date"

    monkeypatch.setattr(sync, "download_long_short_ratio", lambda *a, **k: ls)
    monkeypatch.setattr(sync, "download_open_interest", lambda *a, **k: oi)
    monkeypatch.setattr(sync, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sync, "CACHE_DIR", tmp_path)

    result = sync.sync_oi_ls()
    assert result == {"long_short": True, "open_interest": True}

    ls_csv = pd.read_csv(tmp_path / "long_short_ratio_BTCUSDT.csv")
    oi_csv = pd.read_csv(tmp_path / "open_interest_BTCUSDT.csv")
    assert "long_short_ratio" in ls_csv.columns
    assert "open_interest_usd" in oi_csv.columns


def test_oi_ls_empty_source(monkeypatch, tmp_path):
    """某子源空 DataFrame → 该源 False, 不抛。"""
    import scripts.sync_binance_oi_ls as sync
    monkeypatch.setattr(sync, "download_long_short_ratio", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(sync, "download_open_interest", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(sync, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sync, "CACHE_DIR", tmp_path)
    assert sync.sync_oi_ls() == {"long_short": False, "open_interest": False}
