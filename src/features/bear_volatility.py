"""Bear 专用波动率特征集 — 波动率标准化."""

import pandas as pd
import numpy as np
from src.features.registry import register_feature_set


@register_feature_set("bear_volatility")
def build_bear_volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    """构建 Bear 模型专用波动率特征.

    核心思想：熊市中价格波动极大，需要波动率标准化才能有效预测。
    - ATR 标准化价格变化
    - 实现的波动率
    - 距离历史高点的回撤
    """
    df = df.copy()

    # ========== ATR (Average True Range) ==========
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR (14-period)
    for period in [7, 14, 28]:
        atr = tr.rolling(period).mean()
        df[f"bear_atr_{period}"] = atr

        # ATR 标准化价格变化
        price_change = close.diff()
        df[f"bear_atr_norm_change_{period}"] = price_change / (atr + 1e-10)

    # ========== 实现波动率 (Realized Volatility) ==========
    returns = close.pct_change()

    for window in [5, 10, 21]:
        # 标准差波动率
        rv = returns.rolling(window).std()
        df[f"bear_rv_{window}"] = rv

        # 波动率比率 (短期/长期)
        if window == 5:
            rv_5 = rv
        elif window == 10:
            rv_10 = rv
        elif window == 21:
            rv_21 = rv

    # 波动率比率
    df["bear_rv_ratio_5_21"] = rv_5 / (rv_21 + 1e-10)
    df["bear_rv_ratio_10_21"] = rv_10 / (rv_21 + 1e-10)

    # ========== 距离历史高点的回撤 (Drawdown) ==========
    rolling_max = close.rolling(365).max()  # 1年最高
    df["bear_dist_from_ath"] = (close - rolling_max) / (rolling_max + 1e-10)

    # 最大回撤
    running_max = close.cummax()
    drawdown = (close - running_max) / (running_max + 1e-10)
    df["bear_max_drawdown"] = drawdown

    # ========== 成交量加权波动率 ==========
    if "volume" in df.columns:
        volume = df["volume"]
        for window in [7, 14]:
            vol_rv = (returns * np.sqrt(volume / volume.rolling(window).mean())).rolling(window).std()
            df[f"bear_vol_weighted_rv_{window}"] = vol_rv

    # ========== 波动率 regime ==========
    # 高波动 vs 低波动
    rv_21_val = returns.rolling(21).std()
    rv_median = rv_21_val.rolling(60).median()

    df["bear_vol_high"] = (rv_21_val > rv_median * 1.5).astype(int)
    df["bear_vol_low"] = (rv_21_val < rv_median * 0.5).astype(int)

    return df
