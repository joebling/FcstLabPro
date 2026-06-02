"""链上 Regime 判定 — Phase 3a (Case A: Regime Gating).

核心: 用 MVRV-Z 把市场分为 顶部/正常/底部 三个 regime, 供 gating 层使用.

设计铁律 (防未来函数, Layer 0):
  1. 阈值用 **expanding 滚动历史分位**, 只用 <=t 的数据, 严禁全样本分位.
  2. MVRV-Z 序列 shift(1): 当日收盘后才知, 次日才能用.
  3. **滞后缓冲带 (hysteresis)**: regime 切换需突破缓冲, 避免阈值附近横跳.

详见 docs/plans/phase3_onchain_regime_v0602.md §3.1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Regime 常量
REGIME_TOP = "top"        # 顶部区: 防御
REGIME_NORMAL = "normal"  # 正常区: 跑主模型
REGIME_BOTTOM = "bottom"  # 底部区: 进攻


def rolling_quantile_threshold(
    series: pd.Series,
    q: float,
    min_periods: int = 365,
) -> pd.Series:
    """expanding 滚动历史分位阈值 (只用过去数据, 防未来函数).

    每个时点 t 的阈值 = series[:t] (含 t) 的 q 分位.
    不足 min_periods 时返回 NaN (前期无足够历史不判定).
    """
    return series.expanding(min_periods=min_periods).quantile(q)


def _enter(val: float, t_top: float, t_bot: float) -> str:
    """无缓冲的纯阈值判定 (从 normal 进入, 或缓冲外切换)."""
    if val >= t_top:
        return REGIME_TOP
    if val <= t_bot:
        return REGIME_BOTTOM
    return REGIME_NORMAL


def classify_regime(
    mvrv_z: pd.Series,
    *,
    p_top: float = 0.90,
    p_bottom: float = 0.10,
    min_periods: int = 365,
    hysteresis: float = 0.05,
    shift: bool = True,
) -> pd.Series:
    """基于 MVRV-Z 分类市场 regime (防未来函数).

    Parameters
    ----------
    mvrv_z : pd.Series
        MVRV-Z 序列 (时间升序索引).
    p_top, p_bottom : float
        顶部/底部区分位阈值 (默认 p90 / p10).
    min_periods : int
        滚动分位最少样本 (默认 365 天 = 1 年历史).
    hysteresis : float
        滞后缓冲带 (相对阈值比例). regime 退出需额外突破 hysteresis,
        避免阈值附近反复横跳. 默认 5%.
    shift : bool
        是否 shift(1) (当日收盘后才知, 次日才能用). 默认 True.

    Returns
    -------
    pd.Series
        regime 标签 (top/normal/bottom), 前 min_periods 为 normal.
    """
    s = mvrv_z.shift(1) if shift else mvrv_z.copy()

    thr_top = rolling_quantile_threshold(s, p_top, min_periods)
    thr_bottom = rolling_quantile_threshold(s, p_bottom, min_periods)

    regimes: list[str] = []
    prev = REGIME_NORMAL
    for i in range(len(s)):
        val = s.iloc[i]
        t_top = thr_top.iloc[i]
        t_bot = thr_bottom.iloc[i]

        # 历史不足 → normal (不轻易判定)
        if np.isnan(val) or np.isnan(t_top) or np.isnan(t_bot):
            regimes.append(REGIME_NORMAL)
            prev = REGIME_NORMAL
            continue

        # 滞后缓冲: 进入用原阈值, 退出需多走 hysteresis
        if prev == REGIME_TOP:
            cur = REGIME_TOP if val >= t_top * (1 - hysteresis) else _enter(val, t_top, t_bot)
        elif prev == REGIME_BOTTOM:
            cur = REGIME_BOTTOM if val <= t_bot * (1 + hysteresis) else _enter(val, t_top, t_bot)
        else:
            cur = _enter(val, t_top, t_bot)

        regimes.append(cur)
        prev = cur

    return pd.Series(regimes, index=s.index, name="regime")


def regime_position_multiplier(
    regime: pd.Series,
    *,
    top_mult: float = 0.3,
    normal_mult: float = 1.0,
    bottom_mult: float = 1.0,
) -> pd.Series:
    """A2 软加权: regime → 仓位乘子.

    默认: 顶部区减仓到 30% (防御), 正常/底部满仓.
    (底部不加杠杆超过 1.0, 保守; 如需进攻可调 bottom_mult>1)

    Returns
    -------
    pd.Series
        仓位乘子序列 (与 regime 同索引).
    """
    mapping = {
        REGIME_TOP: top_mult,
        REGIME_NORMAL: normal_mult,
        REGIME_BOTTOM: bottom_mult,
    }
    return regime.map(mapping).astype(float)
