"""测试 src/strategy/onchain_regime.py — 重点验证防未来函数 + hysteresis."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.strategy.onchain_regime import (
    REGIME_TOP,
    REGIME_NORMAL,
    REGIME_BOTTOM,
    rolling_quantile_threshold,
    classify_regime,
    regime_position_multiplier,
)


def _series(vals, start="2020-01-01"):
    idx = pd.date_range(start, periods=len(vals), freq="D")
    return pd.Series(vals, index=idx, dtype=float)


# ====== 防未来函数 ======

def test_rolling_quantile_only_uses_past():
    """滚动分位在每个点只用 <=t 数据; 不足 min_periods 返回 NaN."""
    s = _series(list(range(100)))
    thr = rolling_quantile_threshold(s, q=0.9, min_periods=10)
    assert thr.iloc[:9].isna().all()      # 前 9 个不足 10 → NaN
    assert not np.isnan(thr.iloc[9])      # 第 10 个起有值
    # 第 t 点的分位只反映 [0..t], 必单调不减 (序列递增时)
    valid = thr.dropna()
    assert (valid.diff().dropna() >= -1e-9).all()


def test_shift_prevents_lookahead():
    """shift=True 时, regime[t] 基于 mvrv_z[t-1], 不偷看当日."""
    rng = np.random.default_rng(0)
    # 有波动的正常历史 (非常数), 末日突然飙高
    hist = list(1.0 + rng.normal(0, 0.3, 400))
    s = _series(hist + [100.0])
    reg_shift = classify_regime(s, min_periods=200, shift=True)
    reg_noshift = classify_regime(s, min_periods=200, shift=False)
    # 不 shift: 末日看到 100 → top
    assert reg_noshift.iloc[-1] == REGIME_TOP
    # shift: 末日用前一日(正常值) → 不应 top (证明没偷看当日飙高)
    assert reg_shift.iloc[-1] != REGIME_TOP


# ====== regime 分类正确性 ======

def test_classify_top_and_bottom():
    """明显的高/低值应分到 top/bottom."""
    # 长期在 1.0, 然后持续高位 → top; 持续低位 → bottom
    vals = [1.0] * 400 + [50.0] * 30 + [1.0] * 30 + [-50.0] * 30
    s = _series(vals)
    reg = classify_regime(s, min_periods=200, shift=False, hysteresis=0.0)
    assert (reg.iloc[400:430] == REGIME_TOP).sum() > 20      # 高位段多数 top
    assert (reg.iloc[460:490] == REGIME_BOTTOM).sum() > 20   # 低位段多数 bottom


def test_hysteresis_reduces_flipflop():
    """hysteresis 应减少阈值附近的 regime 翻转次数."""
    rng = np.random.default_rng(42)
    base = [1.0] * 400
    # 在阈值附近抖动
    noisy = list(10 + rng.normal(0, 0.5, 100))
    s = _series(base + noisy)

    reg_no_h = classify_regime(s, min_periods=200, shift=False, hysteresis=0.0)
    reg_h = classify_regime(s, min_periods=200, shift=False, hysteresis=0.15)

    flips_no_h = (reg_no_h.iloc[400:] != reg_no_h.iloc[400:].shift()).sum()
    flips_h = (reg_h.iloc[400:] != reg_h.iloc[400:].shift()).sum()
    assert flips_h <= flips_no_h  # 缓冲带不增加翻转


def test_insufficient_history_is_normal():
    """历史不足 min_periods 时一律 normal (不轻易判定)."""
    s = _series([5.0] * 50)
    reg = classify_regime(s, min_periods=100, shift=False)
    assert (reg == REGIME_NORMAL).all()


# ====== 仓位乘子 ======

def test_position_multiplier_defensive_top():
    """默认顶部区减仓, 正常/底部满仓."""
    reg = pd.Series([REGIME_TOP, REGIME_NORMAL, REGIME_BOTTOM])
    mult = regime_position_multiplier(reg)
    assert mult.iloc[0] == 0.3
    assert mult.iloc[1] == 1.0
    assert mult.iloc[2] == 1.0
