"""Performance 层闭环测试 — 用合成数据验证回填/聚合数值正确.

真实 archive 只有今天的信号 (全 PENDING), 无法验证 MATURE 路径,
故这里注入合成 OHLCV + 临时 archive 目录, 精确断言实现收益/命中/IC。
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from src.performance.maturity import is_mature, maturity_lag_days
from src.performance.backfill import backfill_outcomes
from src.performance.aggregate import build_batches, build_summary, _spearman


# ---------- maturity ----------

def test_maturity_lag_derives_from_T():
    assert maturity_lag_days({"label": {"T": 21}}) == 22   # 21 + 1 buffer
    assert maturity_lag_days({"label": {"T": 28}}) == 29


def test_is_mature_boundary():
    sd = "2026-01-01"
    assert not is_mature(sd, 22, today=date(2026, 1, 22))   # 21 天, 未到
    assert is_mature(sd, 22, today=date(2026, 1, 23))        # 22 天, 成熟


# ---------- 合成数据夹具 ----------

@pytest.fixture
def synthetic(tmp_path):
    """造 OHLCV (每天 open=close=100+i) + 两条历史信号."""
    dates = pd.date_range("2026-01-01", periods=60, freq="D")
    df = pd.DataFrame({
        "date": dates,
        "open": [100 + i for i in range(60)],
        "high": [100 + i for i in range(60)],
        "low": [100 + i for i in range(60)],
        "close": [100 + i for i in range(60)],
        "volume": [1.0] * 60,
    }).set_index("date")

    arch = tmp_path / "archive"
    mdir = arch / "testmodel"
    mdir.mkdir(parents=True)
    (mdir / "2026-01-01.json").write_text(json.dumps({
        "date": "2026-01-01", "signal": "BUY", "price": 100.0,
        "regime": "非熊市", "score_source": "live",
        "provenance": {"model_hash": "abc123", "strategy_variant": "conservative"},
    }))
    (mdir / "2026-01-05.json").write_text(json.dumps({
        "date": "2026-01-05", "signal": "SILENT", "price": 104.0,
        "regime": "非熊市", "score_source": "live",
        "provenance": {"model_hash": "abc123", "strategy_variant": "conservative"},
    }))
    return df, arch


# ---------- backfill 数值 ----------

def test_backfill_buy_hit(synthetic):
    df, arch = synthetic
    rows = backfill_outcomes("testmodel", label_T=21, ohlcv=df,
                             archive_dir=arch, today=date(2026, 3, 1))
    buy = next(r for r in rows if r["date"] == "2026-01-01")
    assert buy["status"] == "MATURE"
    # 进场 t+1 open = day1 = 101, 出场 t+21 close = day21 = 121
    assert buy["entry_price"] == 101.0
    assert buy["exit_price"] == 121.0
    assert buy["realized_return"] == pytest.approx(121 / 101 - 1, abs=1e-6)
    assert buy["hit"] == 1   # 涨了 = 命中


def test_backfill_silent_no_hit(synthetic):
    df, arch = synthetic
    rows = backfill_outcomes("testmodel", label_T=21, ohlcv=df,
                             archive_dir=arch, today=date(2026, 3, 1))
    silent = next(r for r in rows if r["date"] == "2026-01-05")
    assert silent["status"] == "MATURE"
    assert silent["hit"] is None    # SILENT 不下注 = 无命中概念


def test_backfill_pending_when_young(synthetic):
    df, arch = synthetic
    rows = backfill_outcomes("testmodel", label_T=21, ohlcv=df,
                             archive_dir=arch, today=date(2026, 1, 10))
    assert all(r["status"] == "PENDING" for r in rows)


# ---------- aggregate ----------

def test_build_batches_and_summary(synthetic):
    df, arch = synthetic
    import src.performance.backfill as bf
    orig = bf.ARCHIVE_DIR
    bf.ARCHIVE_DIR = arch
    try:
        batches = build_batches("testmodel", label_T=21, ohlcv=df, today=date(2026, 3, 1))
        summary = build_summary("testmodel", label_T=21, ohlcv=df, today=date(2026, 3, 1))
    finally:
        bf.ARCHIVE_DIR = orig

    assert len(batches) == 2
    assert batches[0]["score_date"] == "2026-01-05"   # 倒序, 最新在前
    assert summary["n_mature"] == 2
    assert summary["n_bets"] == 1
    assert summary["hit_rate"] == 100.0


def test_spearman_perfect_rank():
    assert _spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert _spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    assert _spearman([1, 2], [3, 4]) is None   # 样本太少